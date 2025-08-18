BOT_TOKEN = ""

import os
import asyncio
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import discord
from discord.ext import commands
from discord.errors import LoginFailure

# -----------------------
# Config
# -----------------------
COGS_DIR = Path("cogs")
POLL_INTERVAL = 2.0  # seconds
SYNC_RETRY_COUNT = 5
SYNC_RETRY_DELAY = 1.0  # seconds

# -----------------------
# Helpers
# -----------------------
def get_token() -> Optional[str]:
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
    if not tok:
        return "<no token>"
    if len(tok) <= 10:
        return tok[0:2] + "..." + tok[-2:]
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

# Keep track of app commands added per cog: cog_name -> list of (command_name, guild_id_or_None)
_registered_app_cmds: Dict[str, List[Tuple[str, Optional[int]]]] = {}

# -----------------------
# Bot setup
# -----------------------
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None, application_id=1406727860630061086)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id: {bot.user.id})")
    print("------")

# -----------------------
# App command helpers (DEFERRED until bot is ready)
# -----------------------
async def _safe_tree_sync(guild: Optional[discord.Object] = None) -> None:
    """
    Try to sync the tree with retries. This avoids the '_MissingSentinel' issues
    when called too early or during transient state.
    """
    last_exc = None
    for i in range(SYNC_RETRY_COUNT):
        try:
            if guild:
                await bot.tree.sync(guild=guild)
            else:
                await bot.tree.sync()
            return
        except Exception as e:
            last_exc = e
            # small backoff and retry
            await asyncio.sleep(SYNC_RETRY_DELAY)
    # If we get here, all retries failed; raise the last exception for visibility
    raise last_exc

async def register_app_commands_for_cog(cog_name: str):
    """
    After an extension cogs.<cog_name> has been loaded, look for:
      - module.APP_COMMANDS -> iterable of app_commands.Command / Group
      - module.APP_COMMAND_GUILD_ID -> optional int for guild-level registration
    Register them with bot.tree and sync. This waits for bot readiness first.
    """
    await bot.wait_until_ready()  # ensure client and HTTP are ready

    module_name = f"cogs.{cog_name}"
    module = bot.extensions.get(module_name)
    if not module:
        return

    app_cmds = getattr(module, "APP_COMMANDS", None)
    guild_id = getattr(module, "APP_COMMAND_GUILD_ID", None)

    if not app_cmds:
        return

    registered = []
    for cmd in app_cmds:
        try:
            if guild_id:
                bot.tree.add_command(cmd, guild=discord.Object(id=int(guild_id)))
            else:
                bot.tree.add_command(cmd)
            registered.append((cmd.name, int(guild_id) if guild_id else None))
            print(f"Registered app command '{cmd.name}' (cog: {cog_name})")
        except Exception as e:
            print(f"Failed to add app command {getattr(cmd,'name',repr(cmd))} from {cog_name}: {e}")
            traceback.print_exc()

    # sync the tree (guild if provided for faster local dev), with retries
    try:
        if guild_id:
            await _safe_tree_sync(guild=discord.Object(id=int(guild_id)))
        else:
            await _safe_tree_sync()
    except Exception as e:
        print("Warning: failed to sync command tree after retries:", e)
        traceback.print_exc()

    if registered:
        _registered_app_cmds[cog_name] = registered

async def unregister_app_commands_for_cog(cog_name: str):
    """
    Remove any previously-registered app commands that were added for this cog.
    Uses _registered_app_cmds tracking to find what to remove. Waits until ready.
    """
    await bot.wait_until_ready()

    entries = _registered_app_cmds.get(cog_name)
    if not entries:
        return

    for name, guild_id in entries:
        try:
            if guild_id:
                bot.tree.remove_command(name, guild=discord.Object(id=guild_id))
            else:
                bot.tree.remove_command(name)
            print(f"Unregistered app command '{name}' (cog: {cog_name})")
        except Exception as e:
            print(f"Failed to remove app command '{name}' (cog: {cog_name}): {e}")
            traceback.print_exc()

    # sync after removal (best-effort with retries)
    try:
        await _safe_tree_sync()
    except Exception:
        pass

    _registered_app_cmds.pop(cog_name, None)

# -----------------------
# Cog loader/watcher (the same logic, but actual load/register happens AFTER ready)
# -----------------------
async def load_extension_and_register(name: str):
    try:
        await bot.load_extension(f"cogs.{name}")
        print(f"Loaded cog: {name}")
    except Exception as e:
        print(f"Failed to load cog {name}: {e}")
        traceback.print_exc()
        return

    # Register app commands (will wait until ready inside)
    try:
        await register_app_commands_for_cog(name)
    except Exception as e:
        print(f"Error registering app commands for {name}: {e}")
        traceback.print_exc()

async def reload_extension_and_register(name: str):
    try:
        # Unregister previous app commands (if any)
        await unregister_app_commands_for_cog(name)
        if f"cogs.{name}" in bot.extensions:
            await bot.reload_extension(f"cogs.{name}")
            print(f"Reloaded cog: {name}")
        else:
            # If it wasn't loaded, load it
            await load_extension_and_register(name)
            return
    except Exception as e:
        print(f"Failed to reload cog {name}: {e}")
        traceback.print_exc()
        return

    try:
        await register_app_commands_for_cog(name)
    except Exception as e:
        print(f"Error registering app commands after reload for {name}: {e}")
        traceback.print_exc()

async def unload_extension_and_unregister(name: str):
    try:
        await unregister_app_commands_for_cog(name)
        if f"cogs.{name}" in bot.extensions:
            await bot.unload_extension(f"cogs.{name}")
            print(f"Unloaded cog: {name}")
    except Exception as e:
        print(f"Failed to unload cog {name}: {e}")
        traceback.print_exc()

async def load_initial_cogs(state: Dict[str, float]):
    # called once after bot is ready
    for name, mtime in state.items():
        await load_extension_and_register(name)

async def watch_cogs(state: Dict[str, float]):
    """
    Continuously watch the cogs directory for new/removed/modified .py files.
    """
    print("Starting cogs watcher (poll interval:", POLL_INTERVAL, "s)")
    while not bot.is_closed():
        try:
            current = _list_cog_files()
            # New files
            for name, mtime in current.items():
                if name not in state:
                    await load_extension_and_register(name)
                    state[name] = mtime

            # Removed files
            for name in list(state.keys()):
                if name not in current:
                    await unload_extension_and_unregister(name)
                    state.pop(name, None)

            # Modified files
            for name, mtime in list(current.items()):
                old_mtime = state.get(name)
                if old_mtime is not None and mtime != old_mtime:
                    await reload_extension_and_register(name)
                    state[name] = mtime

        except Exception as outer:
            print("Watcher loop encountered an error:", outer)
            traceback.print_exc()

        await asyncio.sleep(POLL_INTERVAL)

# -----------------------
# Background manager task
# -----------------------
async def cogs_manager_task(state: Dict[str, float]):
    """
    This background task waits for the bot to be ready and then loads initial cogs
    and starts the watcher. We create this task before bot.start() so it runs
    concurrently but only proceeds after readiness.
    """
    # Wait until the bot is fully connected and ready
    await bot.wait_until_ready()
    print("Bot ready — loading initial cogs and starting watcher...")
    await load_initial_cogs(state)
    # start watcher (this will run until bot closes)
    await watch_cogs(state)

# -----------------------
# Main
# -----------------------
async def main():
    token = get_token()
    if not token:
        raise RuntimeError(
            "No Discord token found. Put it in BOT_TOKEN at the top of this file,\n"
            "or set DISCORD_TOKEN env var, or create token.txt with the token."
        )

    print("Using token:", mask_token(token))

    # build initial state (filesystem mtimes)
    state = _list_cog_files()

    try:
        async with bot:
            # create manager task BEFORE starting the bot; manager will wait for readiness
            bot.loop.create_task(cogs_manager_task(state))
            # now start the bot (manager task will proceed once ready)
            await bot.start(token)
    except LoginFailure as e:
        raise RuntimeError(
            "Login failed: Discord rejected the token. Make sure you pasted the BOT token (not OAuth client secret),\n"
            "and that the token is current (not regenerated)."
        ) from e

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print("ERROR:", exc)
        traceback.print_exc()
        print("\nQuick checks:")
        print("  • Did you paste the bot token into BOT_TOKEN at the top of this file?")
        print("  • Make sure it's the Bot Token from the Developer Portal (not the client secret).")
        print("  • If you regenerated the token, update it here and restart.")
