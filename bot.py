import discord
import os
from discord.ext import commands
from discord import app_commands
from github import Github
import os # Ensure os is imported if not already
from aiohttp import web # Re-import aiohttp for the dummy server

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = "arwin030/Arwin" # Format: username/repo
CATEGORY_NAME = "Member Channels" 
DATA_FILE = "users.json"

# --- DUMMY WEB SERVER (For Render Free Tier) ---
async def health_check(request):
    return web.Response(text="Bot is ALIVE!")

async def start_dummy_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render provides the PORT environment variable
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🌍 Dummy server started on port {port}")

# Helper function to auto-push to GitHub via API
def sync_to_github(data):
    if not GITHUB_TOKEN:
        print("⚠️ GITHUB_TOKEN not found. Skipping sync.")
        return
# ... (rest of sync_to_github and load_data/save_data) ...

    # 1. Generate the content
    codes = []
    for user_id, info in data.items():
        if info.get('friend_code') and info.get('status') == 'online':
            codes.append(info['friend_code'])
    file_content = "\n".join(codes)

    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        
        # 2. Try to get the existing file (we need its 'sha' to update it)
        try:
            contents = repo.get_contents("ids.txt")
            repo.update_file(contents.path, "Bot: Update active IDs", file_content, contents.sha)
            print("🚀 Pushed to GitHub (Updated)!")
        except Exception:
            # File doesn't exist, create it
            repo.create_file("ids.txt", "Bot: Create IDs file", file_content)
            print("🚀 Pushed to GitHub (Created)!")
            
    except Exception as e:
        print(f"❌ GitHub API Error: {e}")

# ... (load_data / save_data stay same) ...

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("Synced slash commands!")
        # Start dummy server for Render health checks
        self.loop.create_task(start_dummy_server())

# ... (on_member_join stays same) ...

# ... (on_member_join stays same) ...

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("------")

    # Helper command to force sync to the current guild
    async def on_message(self, message):
        if message.content == "!sync":
            await self.tree.sync()
            await message.channel.send("Synced commands globally!")
        await super().on_message(message)

bot = MyBot()

# ... (on_member_join stays same, skipping to keep context short) ...

# --- SLASH COMMANDS ---

@bot.tree.command(name="rg_add_user", description="Register your reroll instance details")
@app_commands.describe(friend_code="Your In-Game Player ID", instances="Number of instances (excluding main)", prefix="Username prefix")
async def rg_add_user(interaction: discord.Interaction, friend_code: str, instances: int, prefix: str):
    # Validation
    if not friend_code.isdigit() or len(friend_code) != 16:
        await interaction.response.send_message(
            f"❌ **Error**: Friend Code must be exactly 16 digits. You entered `{len(friend_code)}` characters.",
            ephemeral=True
        )
        return

    # Save to file
    user_id = str(interaction.user.id)
    data = load_data()
    data[user_id] = {
        "username": interaction.user.name,
        "friend_code": friend_code,
        "instances": instances,
        "prefix": prefix,
        "status": "offline" # Default status is offline
    }
    save_data(data)

    await interaction.response.send_message(
        f"✅ **Registered & Saved!**\n"
        f"• Friend Code: `{friend_code}`\n"
        f"• Instances: `{instances}`\n"
        f"• Prefix: `{prefix}`\n\n"
        f"You are currently **Offline**. Run `/rg_online` to join the queue.",
        ephemeral=False
    )

@bot.tree.command(name="rg_online", description="Set your status to ONLINE and start accepting requests")
async def rg_online(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    data = load_data()
    
    if user_id not in data:
        await interaction.response.send_message("❌ You are not registered! proper use: `/rg_add_user` first.", ephemeral=True)
        return

    data[user_id]['status'] = 'online'
    save_data(data)
    sync_to_github(data) # Trigger GitHub Sync

    await interaction.response.send_message(
        f"🟢 **Online!** {interaction.user.mention} is now accepting friend requests.\n"
        f"Your ID has been added to the global list.",
        ephemeral=False
    )

@bot.tree.command(name="rg_offline", description="Set your status to OFFLINE")
async def rg_offline(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    data = load_data()
    
    if user_id in data:
        data[user_id]['status'] = 'offline'
        save_data(data)
        sync_to_github(data) # Trigger GitHub Sync
    
    await interaction.response.send_message(
        f"🔴 **Offline.** {interaction.user.mention} has stopped accepting requests.\n"
        f"Your ID has been removed from the global list.",
        ephemeral=False
    )

# --- RUN ---
if __name__ == "__main__":
    if TOKEN == "PASTE_YOUR_TOKEN_HERE":
        print("ERROR: Please put your bot token in the bot.py file on line 6.")
    else:
        bot.run(TOKEN)
