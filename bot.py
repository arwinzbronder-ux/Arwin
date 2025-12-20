import discord
import os
from discord.ext import commands, tasks
from discord import app_commands
from github import Github, Auth # Updated import
import json 
from aiohttp import web 
from datetime import datetime, timedelta # Added for bans

# ... (Configuration and other functions stay the same) ...

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Restore DB from Cloud first!
        download_users_from_github()
        
        # Sync globally (still useful for future)
        await self.tree.sync()
        print("Synced slash commands globally!", flush=True)
        self.loop.create_task(start_dummy_server())
        self.check_bans.start() # Start the ban checker

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})", flush=True)
        print("------", flush=True)
       
    # Background task to check for expired bans every 10 minutes
    @tasks.loop(minutes=10)
    async def check_bans(self):
        data = load_data()
        changed = False
        current_time = datetime.now()
        
        # We need to iterate a copy because we might modify the dictionary
        for user_id, info in list(data.items()):
            ban_expiry_str = info.get("ban_expiry")
            if ban_expiry_str:
                try:
                    ban_expiry = datetime.fromisoformat(ban_expiry_str)
                    if current_time > ban_expiry:
                        # Ban expired!
                        del data[user_id]["ban_expiry"]
                        changed = True
                        
                        # Find the guild and user to restore permissions
                        # Note: This simple logic assumes 1 guild for now, or finds the first one
                        if self.guilds:
                            guild = self.guilds[0]
                            member = guild.get_member(int(user_id))
                            channel = discord.utils.get(guild.text_channels, name=CHECKIN_CHANNEL_NAME)
                            if member and channel:
                                # Reset their permissions in the check-in channel
                                await channel.set_permissions(member, overwrite=None)
                                print(f"🔓 Unbanned {member.name}")
                except Exception as e:
                    print(f"Error checking ban for {user_id}: {e}")

        if changed:
            save_data(data)

    async def on_message(self, message):
        if message.content == "!sync":
            await self.tree.sync()
            await message.channel.send("Synced commands globally!")
        await super().on_message(message)

bot = MyBot()

# ... (on_member_join and existing commands stay same) ...

# --- MODERATION COMMANDS ---

@bot.tree.command(name="rg_remove_id", description="[Admin] Remove a Friend Code from the database")
@app_commands.describe(friend_code="The 16-digit ID to remove")
@app_commands.checks.has_permissions(manage_messages=True)
async def rg_remove_id(interaction: discord.Interaction, friend_code: str):
    await interaction.response.defer(ephemeral=False) # Defer immediately

    data = load_data()
    found_user_id = None
    
    # Find the user owning this code
    for user_id, info in data.items():
        if info.get('friend_code') == friend_code:
            found_user_id = user_id
            break
    
    if found_user_id:
        # Clear their code and set offline
        data[found_user_id]['friend_code'] = None
        data[found_user_id]['status'] = 'offline'
        save_data(data)
        sync_to_github(data)
        await interaction.followup.send(f"🗑️ Removed ID `{friend_code}` from the list and set user to Offline.")
    else:
        await interaction.followup.send(f"❌ ID `{friend_code}` not found in database.", ephemeral=True)

@bot.tree.command(name="rg_tempban", description="[Admin] Ban a user from the check-in channel for 48h")
@app_commands.describe(member="The user to ban")
@app_commands.checks.has_permissions(manage_messages=True)
async def rg_tempban(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=False) # Defer immediately

    # Calculate expiry
    expiry_time = datetime.now() + timedelta(hours=48)
    
    # Update Data
    data = load_data()
    user_id = str(member.id)
    if user_id not in data:
         data[user_id] = {} # Create entry if doesn't exist
    
    data[user_id]["ban_expiry"] = expiry_time.isoformat()
    # Also force them offline if they were online
    if data[user_id].get('status') == 'online':
        data[user_id]['status'] = 'offline'
        sync_to_github(data)
    
    save_data(data)
    
    # Apply Discord Permission Override
    channel = discord.utils.get(member.guild.text_channels, name=CHECKIN_CHANNEL_NAME)
    if channel:
        await channel.set_permissions(member, send_messages=False, read_messages=False)
        await interaction.followup.send(f"🚫 Banned {member.mention} from {channel.mention} for 48 hours.")
    else:
        await interaction.followup.send(f"⚠️ Could not find channel `{CHECKIN_CHANNEL_NAME}` to apply ban.", ephemeral=True)

# Error handler for missing permissions
@rg_remove_id.error
@rg_tempban.error
async def mod_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = "arwin030/Arwin" # Format: username/repo
CATEGORY_NAME = "Member Channels" 
DATA_FILE = "users.json"
CHECKIN_CHANNEL_NAME = "check-in" # The channel where users should land first

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

    # 1. Generate the content
    codes = []
    for user_id, info in data.items():
        if info.get('friend_code') and info.get('status') == 'online':
            codes.append(info['friend_code'])
    file_content = "\n".join(codes)

    try:
        auth = Auth.Token(GITHUB_TOKEN) # Fixed Deprecation
        g = Github(auth=auth)
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

# ... (Configuration) ...

# Helper to download users.json from GitHub (Persistence)
def download_users_from_github():
    if not GITHUB_TOKEN: return
    try:
        auth = Auth.Token(GITHUB_TOKEN) # Fixed Deprecation
        g = Github(auth=auth)
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(DATA_FILE)
        with open(DATA_FILE, "wb") as f:
            f.write(contents.decoded_content)
        print(f"✅ Downloaded {DATA_FILE} from GitHub")
    except Exception as e:
        print(f"⚠️ Could not download {DATA_FILE} (starting fresh): {e}")

# Helper to upload users.json to GitHub (Persistence)
def upload_users_to_github(data):
    if not GITHUB_TOKEN: return
    json_content = json.dumps(data, indent=4)
    try:
        auth = Auth.Token(GITHUB_TOKEN) # Fixed Deprecation
        g = Github(auth=auth)
        repo = g.get_repo(REPO_NAME)
        try:
            contents = repo.get_contents(DATA_FILE)
            repo.update_file(contents.path, "Bot: Save User DB", json_content, contents.sha)
        except Exception:
            repo.create_file(DATA_FILE, "Bot: Create User DB", json_content)
        print(f"💾 Saved {DATA_FILE} to GitHub")
    except Exception as e:
        print(f"❌ Failed to save {DATA_FILE} to GitHub: {e}")

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_data(data):
    # 1. Save locally
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)
    # 2. Sync to Cloud
    upload_users_to_github(data)


# ... (MyBot Class and on_member_join stay same) ...

# The MyBot class definition is duplicated in the original content,
# I will keep the first one and remove the second one as it's redundant.
# The user's instruction implies the first MyBot class is the primary one.

# class MyBot(commands.Bot):
#     def __init__(self):
#         intents = discord.Intents.default()
#         intents.members = True
#         intents.message_content = True
#         super().__init__(command_prefix="!", intents=intents)

#     async def setup_hook(self):
#         await self.tree.sync()
#         print("Synced slash commands!")
#         # Start dummy server for Render health checks
#         self.loop.create_task(start_dummy_server())

# ... (on_member_join stays same) ...

# ... (on_member_join stays same) ...

# The on_ready and on_message methods are part of the MyBot class,
# and are already defined in the first MyBot class.
# I will ensure the first MyBot class is complete and remove redundant definitions.

#     async def on_ready(self):
#         print(f"Logged in as {self.user} (ID: {self.user.id})")
#         print("------")

#     # Helper command to force sync to the current guild
#     async def on_message(self, message):
#         if message.content == "!sync":
#             await self.tree.sync()
#             await message.channel.send("Synced commands globally!")
#         await super().on_message(message)

# bot = MyBot() # This line is also duplicated, keeping the first one.

@bot.event
async def on_member_join(member):
    guild = member.guild
    print(f"Member joined: {member.name}")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        guild.me: discord.PermissionOverwrite(read_messages=True, manage_channels=True, manage_webhooks=True),
        member: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }

    # 1. Ensure Category Exists
    category = None
    if CATEGORY_NAME:
        category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
        if not category:
            try:
                category = await guild.create_category(CATEGORY_NAME)
            except Exception:
                pass

    # 2. Create Private Channel (Silently - no ping here yet)
    channel_name = f"home-{member.name}"
    private_channel = None
    try:
        private_channel = await guild.create_text_channel(channel_name, overwrites=overwrites, category=category)
        webhook = await private_channel.create_webhook(name=f"{member.name}'s Webhook")
        
        # Post the setup info in the private channel (but don't rely on them seeing it first)
        setup_msg = (
            f"⚡ **Your Private Automation Hub** ⚡\n"
            f"Here is your personal webhook URL: ||{webhook.url}||\n\n"
            f"🛑 **STOP!** Have you set up your bot yet?\n"
            f"Go to {CHECKIN_CHANNEL_NAME} for instructions FIRST."
        )
        await private_channel.send(setup_msg)
        print(f"Created channel for {member.name}")
        
    except Exception as e:
        print(f"Error creating channel: {e}")

    # 3. Ping them in the CHECK-IN channel (The Landing Pad)
    checkin_channel = discord.utils.get(guild.text_channels, name=CHECKIN_CHANNEL_NAME)
    if checkin_channel:
        try:
            welcome_ping = (
                f"👋 Welcome {member.mention}!\n"
                f"Please read the guide here to set up your bot.\n"
                f"✅ **Once you are ready**, your private channel is waiting here: {private_channel.mention}"
            )
            await checkin_channel.send(welcome_ping)
        except Exception as e:
            print(f"Could not ping in check-in: {e}")

# --- SLASH COMMANDS ---

# --- SLASH COMMANDS ---

@bot.tree.command(name="rg_add_user", description="Register your reroll instance details")
@app_commands.describe(friend_code="Your In-Game Player ID", instances="Number of instances (excluding main)", prefix="Username prefix")
async def rg_add_user(interaction: discord.Interaction, friend_code: str, instances: int, prefix: str):
    # Validation (Fast - Do this before deferring)
    if not friend_code.isdigit() or len(friend_code) != 16:
        await interaction.response.send_message(
            f"❌ **Error**: Friend Code must be exactly 16 digits. You entered `{len(friend_code)}` characters.",
            ephemeral=True
        )
        return

    # Defer response
    await interaction.response.defer(ephemeral=False)

    user_id = str(interaction.user.id)
    data = load_data()

    # Check for Duplicates (Global Uniqueness)
    for existing_id, info in data.items():
        if info.get('friend_code') == friend_code and existing_id != user_id:
            await interaction.followup.send(
                f"❌ **Error**: This Friend Code is already registered by another user.",
                ephemeral=True
            )
            return

    # Save to file
    data[user_id] = {
        "username": interaction.user.name,
        "friend_code": friend_code,
        "instances": instances,
        "prefix": prefix,
        "status": "offline" # Default status is offline
    }
    save_data(data)

    await interaction.followup.send(
        f"✅ **Registered & Saved!**\n"
        f"• Friend Code: `{friend_code}`\n"
        f"• Instances: `{instances}`\n"
        f"• Prefix: `{prefix}`\n\n"
        f"You are currently **Offline**. Run `/rg_online` to join the queue."
    )

@bot.tree.command(name="rg_unadd_user", description="Unregister fully (use this if you made a mistake)")
async def rg_unadd_user(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    
    user_id = str(interaction.user.id)
    data = load_data()
    
    if user_id in data:
        del data[user_id]
        save_data(data)
        sync_to_github(data)
        await interaction.followup.send("🗑️ **Unregistered.** Your data has been wiped. You can now register a new ID.")
    else:
        await interaction.followup.send("❌ You are not registered.", ephemeral=True)

@bot.tree.command(name="rg_online", description="Set your status to ONLINE and start accepting requests")
async def rg_online(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False) # Defer immediately

    user_id = str(interaction.user.id)
    data = load_data()
    
    if user_id not in data:
        await interaction.followup.send("❌ You are not registered! proper use: `/rg_add_user` first.", ephemeral=True)
        return

    data[user_id]['status'] = 'online'
    save_data(data)
    sync_to_github(data) # Trigger GitHub Sync

    await interaction.followup.send(
        f"🟢 **Online!** {interaction.user.mention} is now accepting friend requests.\n"
        f"Your ID has been added to the global list."
    )

@bot.tree.command(name="rg_offline", description="Set your status to OFFLINE")
async def rg_offline(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False) # Defer immediately

    user_id = str(interaction.user.id)
    data = load_data()
    
    if user_id in data:
        data[user_id]['status'] = 'offline'
        save_data(data)
        sync_to_github(data) # Trigger GitHub Sync
    
    await interaction.followup.send(
        f"🔴 **Offline.** {interaction.user.mention} has stopped accepting requests.\n"
        f"Your ID has been removed from the global list."
    )

# --- RUN ---
if __name__ == "__main__":
    if TOKEN == "PASTE_YOUR_TOKEN_HERE":
        print("ERROR: Please put your bot token in the bot.py file on line 6.")
    else:
        bot.run(TOKEN)
