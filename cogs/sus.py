# cogs/sus_cog.py
import discord
from discord.ext import commands
from discord import app_commands

# --- Imports ---
import random
import io
import asyncio
import typing
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from functools import partial

# --- Helper function (unchanged) ---
def mask_image_to_circle(image: Image.Image) -> Image.Image:
    """Crops an image to a circle."""
    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0) + image.size, fill=255)
    output = ImageOps.fit(image, mask.size, centering=(0.5, 0.5))
    output.putalpha(mask)
    return output

# --- Main Cog Class ---
class SusCog(commands.Cog, name="sus"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = bot.session
        
        print("Loading 'sus' cog assets into memory...")
        assets_path = Path(__file__).parent.parent / "assets"
        self.font_path_str = str(assets_path / "font.ttf") # Store path as string
        bg_path = assets_path / "IMG_0574.webp"
        crewmate_path = assets_path / "crewmates"

        # --- MODIFICATION: Store background and its dimensions ---
        self.background_image = Image.open(bg_path).convert("RGBA")
        self.image_width, self.image_height = self.background_image.size
        
        # We no longer load fixed-size fonts here. They will be generated on the fly.
        
        self.crewmate_images = {}
        for crewmate_file in crewmate_path.glob("*.png"):
            color = crewmate_file.stem
            image = Image.open(crewmate_file).convert("RGBA")
            self.crewmate_images[color] = image.resize((image.width // 2, image.height // 2))
        print(f"Loaded {len(self.crewmate_images)} crewmates.")

    # --- NEW HELPER FUNCTION ---
    def _get_fitting_font(self, text: str, max_width: int, initial_size: int) -> ImageFont.FreeTypeFont:
        """
        Calculates the largest possible font size for a given text that fits
        within a max_width. Starts with an initial proportional size.
        """
        font_size = initial_size
        font = ImageFont.truetype(self.font_path_str, font_size)
        
        # Shrink the font size until the text fits the bounding box
        while font.getbbox(text)[2] > max_width:
            font_size -= 2 # Decrease by 2 for speed
            if font_size <= 10: # Set a minimum font size
                font_size = 10
                break
            font = ImageFont.truetype(self.font_path_str, font_size)
            
        return font

    def _blocking_generate_image(self, text: str, subject_image: Image.Image) -> io.BytesIO:
        """
        Synchronous function for image manipulation, now with dynamic font sizing.
        """
        # --- CUSTOMIZATION PARAMETERS ---
        # The factor to determine the initial font size based on image height.
        # Smaller number = bigger font (e.g., / 10 is bigger than / 12)
        PROPORTIONAL_HEIGHT_FACTOR_LARGE = 10 
        PROPORTIONAL_HEIGHT_FACTOR_SMALL = 13
        # The maximum width the text can occupy, as a percentage of image width.
        MAX_TEXT_WIDTH_PERCENT = 0.90 

        # --- DYNAMIC FONT SIZING LOGIC ---
        background = self.background_image.copy()
        draw = ImageDraw.Draw(background)
        
        # 1. Calculate the maximum allowed width for text
        max_text_width = int(self.image_width * MAX_TEXT_WIDTH_PERCENT)
        
        # 2. Calculate the initial proportional font sizes
        initial_large_size = self.image_height // PROPORTIONAL_HEIGHT_FACTOR_LARGE
        initial_small_size = self.image_height // PROPORTIONAL_HEIGHT_FACTOR_SMALL

        # 3. Get the final, fitted fonts for both lines of text
        was_impostor = random.choice([True, False])
        line2_text = "was The Impostor." if was_impostor else "was not The Impostor."

        font_large = self._get_fitting_font(text, max_text_width, initial_large_size)
        font_small = self._get_fitting_font(line2_text, max_text_width, initial_small_size)

        # --- DRAWING LOGIC (uses the new dynamic fonts) ---
        # Get the final width of the text with the new font to center it properly
        line1_width = font_large.getbbox(text)[2]
        draw.text(
            ((self.image_width - line1_width) / 2, self.image_height / 2 - 150), 
            text, font=font_large, fill="white"
        )

        line2_width = font_small.getbbox(line2_text)[2]
        draw.text(
            ((self.image_width - line2_width) / 2, self.image_height / 2 - 20),
            line2_text, font=font_small, fill="white"
        )
        
        # Paste subject image (unchanged)
        img_x = (self.image_width - subject_image.width) // 2
        img_y = self.image_height // 2 + 100
        background.paste(subject_image, (img_x, img_y), subject_image)

        final_buffer = io.BytesIO()
        background.save(final_buffer, format="PNG")
        final_buffer.seek(0)
        return final_buffer

    # The rest of the file (async helpers and command definitions) remains the same.
    # ... (no changes needed for _create_and_send_ejection, sus_prefix, sus_slash, setup) ...
    async def _create_and_send_ejection(
        self, 
        interaction_or_ctx,
        text: str, 
        user: typing.Optional[discord.Member] = None
    ):
        subject_image = None
        if user:
            try:
                async with self.session.get(str(user.display_avatar.with_size(256))) as resp:
                    if resp.status == 200:
                        avatar_data = await resp.read()
                        avatar_image = Image.open(io.BytesIO(avatar_data)).convert("RGBA")
                        subject_image = mask_image_to_circle(avatar_image)
            except Exception as e:
                print(f"Could not fetch or process avatar: {e}")
                user = None 
        if not user:
            color = random.choice(list(self.crewmate_images.keys()))
            subject_image = self.crewmate_images[color]

        loop = asyncio.get_running_loop()
        func = partial(self._blocking_generate_image, text, subject_image)
        image_buffer = await loop.run_in_executor(None, func)
        picture = discord.File(image_buffer, filename="sus.png")
        if isinstance(interaction_or_ctx, discord.Interaction):
            await interaction_or_ctx.followup.send(file=picture)
        else:
            await interaction_or_ctx.send(file=picture)
    @commands.command(name="sus", help="Ejects a user or text from the ship.")
    async def sus_prefix(self, ctx: commands.Context, user: typing.Optional[discord.Member] = None, *, text: str = None):
        if user and not text:
            display_text = user.display_name
        elif not text:
            await ctx.send("You need to provide text or a user to eject!")
            return
        else:
            display_text = text
        async with ctx.typing():
            await self._create_and_send_ejection(ctx, display_text, user)
    @app_commands.command(name="sus", description="Generates an Among Us ejection screen.")
    @app_commands.describe(text="The text to display on the screen.", user="[Optional] The user whose avatar to eject.")
    async def sus_slash(self, interaction: discord.Interaction, text: str, user: typing.Optional[discord.Member] = None):
        await interaction.response.defer(thinking=True)
        await self._create_and_send_ejection(interaction, text, user)

async def setup(bot: commands.Bot):
    await bot.add_cog(SusCog(bot))