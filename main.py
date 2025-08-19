BOT_TOKEN = ""  # <-- paste token between the quotes
# main.py
import os
import asyncio
import traceback
from pathlib import Path
from typing import Dict, List, Optional
import aiohttp

import discord
from discord.ext import commands
from discord.errors import LoginFailure

# -----------------------
# Config
# -----------------------

COGS_DIR = Path("cogs")
POLL_INTERVAL = 2.0  # seconds

# -----------------------
# Helpers
# -----------------------
def get_token() -> Optional[str]:
    # This function is well-written and safely checks for the token.
    if isinstance(BOT_TOKEN, str) and BOT_TOKEN and BOT_TOKEN != "YOUR_BOT_TOKEN_HERE":
        return BOT_TOKEN.strip()
    env = os.environ.get("DISCORD_TOKEN")
    if env:
        return env.strip()
    token_file = Path("token.txt")
    if token_file.exists():
        tok = token_file.read_text().splitlines()
        if tok:
            return tok[0].strip()
    return None

def mask_token(tok: str) -> str:
    if not tok: return "<no token>"
    return tok[:4] + "..." + tok[-4:]

def _list_cog_files() -> Dict[str, float]:
    files = {}
    if not COGS_DIR.exists():
        COGS_DIR.mkdir(parents=True, exist_ok=True)
    for p in sorted(COGS_DIR.glob("*.py")):
        try:
            files[p.stem] = p.stat().st_mtime
        except FileNotFoundError:
            continue
    return files

# -----------------------
# Custom Bot Class Setup
# -----------------------
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.session: Optional[aiohttp.ClientSession] = None
        self.cog_watcher_task: Optional[asyncio.Task] = None
        self.initial_cogs = _list_cog_files()

    async def setup_hook(self):
        """This is called once when the bot is setting up, before login."""
        print("Running setup hook...")
        # Create the aiohttp client session
        self.session = aiohttp.ClientSession()
        print("AIOHTTP session created.")

        # Load initial cogs
        for cog_name in self.initial_cogs.keys():
            try:
                await self.load_extension(f"cogs.{cog_name}")
                print(f"Loaded initial cog: {cog_name}")
            except Exception as e:
                print(f"Failed to load initial cog {cog_name}: {e}")
                traceback.print_exc()

        # Sync the command tree
        # This is more reliable than the complex per-cog registration system
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} application commands.")
        except Exception as e:
            print(f"Failed to sync command tree: {e}")

        # Start the cog watcher task
        self.cog_watcher_task = self.loop.create_task(self.watch_cogs())
        print("Cog watcher task created.")

    async def on_ready(self):
        print(f"Logged in as {self.user} (id: {self.user.id})")
        print("------")

    async def close(self):
        """Ensure resources are closed on shutdown."""
        if self.cog_watcher_task:
            self.cog_watcher_task.cancel()
        if self.session:
            await self.session.close()
        await super().close()

    async def watch_cogs(self):
        """Continuously watch the cogs directory for changes."""
        await self.wait_until_ready()
        print("Starting cogs watcher...")
        
        state = self.initial_cogs.copy()

        while not self.is_closed():
            try:
                current = _list_cog_files()
                
                # Handle modifications and new files
                for name, mtime in current.items():
                    if name not in state or state[name] != mtime:
                        try:
                            # Reloading handles both new and modified cogs
                            await self.reload_extension(f"cogs.{name}")
                            print(f"Reloaded cog: {name}")
                            await self.tree.sync() # Re-sync after reload
                        except commands.ExtensionNotLoaded:
                            await self.load_extension(f"cogs.{name}")
                            print(f"Loaded new cog: {name}")
                            await self.tree.sync() # Re-sync after new load
                        except Exception as e:
                            print(f"Failed to reload/load cog {name}: {e}")
                            traceback.print_exc()
                        state[name] = mtime

                # Handle removed files
                for name in list(state.keys()):
                    if name not in current:
                        try:
                            await self.unload_extension(f"cogs.{name}")
                            print(f"Unloaded cog: {name}")
                            state.pop(name)
                            await self.tree.sync() # Re-sync after unload
                        except Exception as e:
                            print(f"Failed to unload cog {name}: {e}")
                
            except Exception as outer:
                print(f"Watcher loop encountered an error: {outer}")
                traceback.print_exc()

            await asyncio.sleep(POLL_INTERVAL)

# -----------------------
# Main
# -----------------------
async def main():
    token = get_token()
    if not token:
        raise RuntimeError("No Discord token found.")

    print("Using token:", mask_token(token))
    
    bot = MyBot()
    
    try:
        await bot.start(token)
    except LoginFailure:
        raise RuntimeError("Login failed: Discord rejected the token.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"ERROR: {exc}")
        traceback.print_exc()