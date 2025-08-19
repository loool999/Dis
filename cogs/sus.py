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
import secrets

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
        self.gif_rotation_speed_range = (-8, 8)
        
        print("Loading 'sus' cog assets into memory...")
        assets_path = Path(__file__).parent.parent / "assets"
        
        try:
            ImageFont.truetype("arial.ttf", 10)
            self.font_path_str = "arial.ttf"
            print("Using system font 'arial.ttf' for Unicode support.")
        except IOError:
            self.font_path_str = str(assets_path / "font.ttf")
            print("System font 'arial.ttf' not found, falling back to bundled 'font.ttf'.")
            print("For better Unicode support, consider replacing 'assets/font.ttf' with a font like 'Noto Sans'.")

        bg_path = assets_path / "IMG_0574.webp"
        crewmate_path = assets_path / "crewmates"

        self.background_image = Image.open(bg_path).convert("RGBA")
        self.image_width, self.image_height = self.background_image.size
        
        self.crewmate_images = {}
        for crewmate_file in crewmate_path.glob("*.png"):
            color = crewmate_file.stem
            self.crewmate_images[color] = Image.open(crewmate_file).convert("RGBA")
        print(f"Loaded {len(self.crewmate_images)} crewmates.")

    def _get_fitting_font(self, text: str, max_width: int, initial_size: int) -> ImageFont.FreeTypeFont:
        font_size = initial_size
        font = ImageFont.truetype(self.font_path_str, font_size)
        
        while font.getbbox(text)[2] > max_width:
            font_size -= 2
            if font_size <= 10:
                font_size = 10
                break
            font = ImageFont.truetype(self.font_path_str, font_size)
            
        return font

    def _blocking_generate_gif(self, text: str, subject_image: Image.Image, custom_text_provided: bool = False) -> io.BytesIO:
        frame_duration = 50
        num_frames = 50
        PROPORTIONAL_HEIGHT_FACTOR_SMALL = 13
        MAX_TEXT_WIDTH_PERCENT = 0.90

        max_text_width = int(self.image_width * MAX_TEXT_WIDTH_PERCENT)
        initial_small_size = self.image_height // PROPORTIONAL_HEIGHT_FACTOR_SMALL
        
        if custom_text_provided:
            line_text = text
        else:
            was_impostor = secrets.choice([True, False])
            line_text = f"{text} was The Impostor." if was_impostor else f"{text} was not The Impostor."

        font_small = self._get_fitting_font(line_text, max_text_width, initial_small_size)
        
        bbox = font_small.getbbox(line_text)
        line_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = (self.image_width - line_width) / 2
        text_y = (self.image_height - text_height) / 2

        frames = []
        start_x = -subject_image.width
        end_x = self.image_width
        avatar_y = text_y + text_height / 2 - subject_image.height / 2
        
        rotation_speed = random.uniform(*self.gif_rotation_speed_range)
        current_angle = 0

        for i in range(num_frames):
            frame = self.background_image.copy()
            current_angle += rotation_speed
            rotated_avatar = subject_image.rotate(current_angle, expand=True, resample=Image.BICUBIC)

            progress = i / (num_frames - 1)
            avatar_x = int(start_x + (end_x - start_x) * progress) - (rotated_avatar.width - subject_image.width) // 2
            avatar_y_adjusted = int(avatar_y) - (rotated_avatar.height - subject_image.height) // 2
            
            frame.paste(rotated_avatar, (avatar_x, avatar_y_adjusted), rotated_avatar)
            
            draw = ImageDraw.Draw(frame)
            draw.text((text_x, text_y), line_text, font=font_small, fill="white")
            
            frames.append(frame)

        final_buffer = io.BytesIO()
        # To prevent looping, we append a final frame that is identical to the last
        # and give it a very long duration. We also set loop=0 (infinite) so the
        # animation effectively 'pauses' on the last frame.
        last_frame = frames[-1].copy()
        frames.append(last_frame)
        
        durations = [frame_duration] * (num_frames) + [60000]

        frames[0].save(
            final_buffer,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=0,
        )
        final_buffer.seek(0)
        return final_buffer

    def _blocking_generate_image(self, text: str, subject_image: Image.Image, custom_text_provided: bool = False) -> io.BytesIO:
        PROPORTIONAL_HEIGHT_FACTOR_SMALL = 13
        MAX_TEXT_WIDTH_PERCENT = 0.90

        max_text_width = int(self.image_width * MAX_TEXT_WIDTH_PERCENT)
        initial_small_size = self.image_height // PROPORTIONAL_HEIGHT_FACTOR_SMALL
        
        if custom_text_provided:
            line_text = text
        else:
            was_impostor = secrets.choice([True, False])
            line_text = f"{text} was The Impostor." if was_impostor else f"{text} was not The Impostor."

        font_small = self._get_fitting_font(line_text, max_text_width, initial_small_size)

        bbox = font_small.getbbox(line_text)
        line_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_y = (self.image_height - text_height) / 2

        angle = random.uniform(0, 360)
        rotated_avatar = subject_image.rotate(angle, expand=True, resample=Image.BICUBIC)
        
        img_x = random.randint(0, self.image_width - rotated_avatar.width)
        avatar_y = text_y + text_height / 2 - rotated_avatar.height / 2

        background = self.background_image.copy()
        background.paste(rotated_avatar, (img_x, int(avatar_y)), rotated_avatar)
        
        draw = ImageDraw.Draw(background)
        draw.text(
            ((self.image_width - line_width) / 2, text_y),
            line_text, font=font_small, fill="white"
        )

        final_buffer = io.BytesIO()
        background.save(final_buffer, format="PNG")
        final_buffer.seek(0)
        return final_buffer

    async def _create_and_send_ejection(
        self, 
        interaction_or_ctx,
        text: str, 
        user: typing.Optional[discord.Member] = None,
        gif_mode: bool = True,
        custom_text_provided: bool = False
    ):
        subject_image = None
        if user:
            try:
                async with self.session.get(str(user.display_avatar.with_size(128))) as resp:
                    if resp.status == 200:
                        avatar_data = await resp.read()
                        avatar_image = Image.open(io.BytesIO(avatar_data)).convert("RGBA")
                        subject_image = avatar_image.resize((64, 64), Image.LANCZOS)
            except Exception as e:
                print(f"Could not fetch or process avatar: {e}")
                user = None 
        if not user:
            color = random.choice(list(self.crewmate_images.keys()))
            subject_image = self.crewmate_images[color].resize((64, 64), Image.LANCZOS)

        loop = asyncio.get_running_loop()
        if gif_mode:
            func = partial(self._blocking_generate_gif, text, subject_image, custom_text_provided=custom_text_provided)
            filename = "sus.gif"
        else:
            func = partial(self._blocking_generate_image, text, subject_image, custom_text_provided=custom_text_provided)
            filename = "sus.png"

        image_buffer = await loop.run_in_executor(None, func)
        picture = discord.File(image_buffer, filename=filename)
        if isinstance(interaction_or_ctx, discord.Interaction):
            await interaction_or_ctx.followup.send(file=picture)
        else:
            await interaction_or_ctx.send(file=picture)

    @commands.command(name="sus", help="Ejects a user or text from the ship.")
    async def sus_prefix(self, ctx: commands.Context, user: typing.Optional[discord.Member] = None, *, text: str = None):
        custom_text_provided = text is not None
        if user and not text:
            display_text = user.display_name
        elif text:
            display_text = text
        else: # No user, no text
            await ctx.send("You need to provide text or a user to eject!")
            return

        async with ctx.typing():
            await self._create_and_send_ejection(ctx, display_text, user, gif_mode=True, custom_text_provided=custom_text_provided)

    @app_commands.command(name="sus", description="Generates an Among Us ejection screen.")
    @app_commands.describe(
        user="The user to eject.",
        text="[Optional] The text to display. Defaults to the user's name.",
        gif_mode="[Optional] Generate a GIF instead of a static image. Defaults to True."
    )
    async def sus_slash(self, interaction: discord.Interaction, user: discord.Member, text: typing.Optional[str] = None, gif_mode: bool = True):
        await interaction.response.defer(thinking=True)
        display_text = text or user.display_name
        custom_text_provided = text is not None
        await self._create_and_send_ejection(interaction, display_text, user, gif_mode=gif_mode, custom_text_provided=custom_text_provided)

async def setup(bot: commands.Bot):
    await bot.add_cog(SusCog(bot))