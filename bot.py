import discord
import os
import asyncio
from discord.ext import commands, tasks
from discord import app_commands
from github import Github, Auth # Updated import
import json 
from aiohttp import web 
import aiohttp # Added correctly
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
        await download_users_from_github()
        
        # Sync globally (still useful for future)
        await self.tree.sync()
        print("Synced slash commands globally!", flush=True)
        self.loop.create_task(start_dummy_server())
        self.check_bans.start() # Start the ban checker

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})", flush=True)
        print("------", flush=True)
        await update_channel_status(self)
       
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
# Helper to find check-in channel (ignoring status prefix)
def get_checkin_channel(guild):
    for ch in guild.text_channels:
        if ch.name == CHECKIN_CHANNEL_NAME or \
           ch.name == f"🟢-{CHECKIN_CHANNEL_NAME}" or \
           ch.name == f"🔴-{CHECKIN_CHANNEL_NAME}":
            return ch
    return None

# Helper to count online users
def count_online_users(data):
# ... (existing count_online_users) ...

# ... (In check_bans) ...
                            member = guild.get_member(int(user_id))
                            channel = get_checkin_channel(guild)
                            if member and channel:
# ...

# ... (In rg_tempban) ...
    # Apply Discord Permission Override
    channel = get_checkin_channel(member.guild)
    if channel:
# ...

# ... (In on_member_join) ...
            f"Here is your personal webhook URL: ||{webhook.url}||\n\n"
            f"🛑 **STOP!** Have you set up your bot yet?\n"
            f"Go to the **check-in** channel for instructions FIRST."
        )
        await private_channel.send(setup_msg)
        print(f"Created channel for {member.name}", flush=True)
        
    except Exception as e:
        print(f"Error creating channel: {e}", flush=True)

    # 3. Ping them in the CHECK-IN channel (The Landing Pad)
    checkin_channel = get_checkin_channel(guild)
    if checkin_channel:
        try:
# ...
    count = 0
    for info in data.values():
        if info.get('status') == 'online':
            count += 1
    return count

# Helper to update channel name (Rate Limited: 2 per 10 mins)
async def update_channel_status(bot_instance):
    data = load_data()
    online_count = count_online_users(data)
    
    # Determine Status Indicator
    new_prefix = "🟢" if online_count > 0 else "🔴"
    base_name = CHECKIN_CHANNEL_NAME.replace("🟢-", "").replace("🔴-", "") # clean base
    new_name = f"{new_prefix}-{base_name}"
    
    # Find the channel
    # We scan all guilds (usually just one)
    for guild in bot_instance.guilds:
        # Find any channel that matches the base name (ignoring prefix)
        channel = discord.utils.get(guild.text_channels, name=new_name)
        
        # If already named correctly, skip
        if channel:
            continue
            
        # Search for incorrect names to rename
        for ch in guild.text_channels:
            if ch.name.endswith(base_name):
                try:
                    await ch.edit(name=new_name)
                    print(f"🔄 Renamed channel to: {new_name}", flush=True)
                except Exception as e:
                    print(f"⚠️ Channel Rename Rate Limited or Failed: {e}", flush=True)
                break

# Error handler for missing permissions
@rg_remove_id.error
@rg_tempban.error
async def mod_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = "arwinzbronder-ux/Arwin" # Format: username/repo
CATEGORY_NAME = "Member Channels" 
DATA_FILE = "users.json"
import io
from PIL import Image, ImageDraw, ImageFont

# ... (Previous imports) ...

# ... (In Configuration) ...
CHECKIN_CHANNEL_NAME = "check-in" 
WATERMARK_CHANNEL_NAME = "🎰︱group-packs"

# ... (Helper functions) ...

def add_watermark(image_bytes):
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = img.convert("RGBA")
            
            # Create a transparent text layer
            txt_layer = Image.new('RGBA', img.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(txt_layer)
            text = "EternalGP"
            
            # Calculate dynamic font size (20% of height)
            width, height = img.size
            font_size = int(height * 0.20) 
            if font_size < 40: font_size = 40
            
            try:
                 font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
            except:
                 font = ImageFont.load_default()

            # Calculate position (Center)
            left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
            text_width = right - left
            text_height = bottom - top
            
            x = (width - text_width) / 2
            y = (height - text_height) / 2
            
            # Calculate dynamic stroke width
            stroke_width = max(1, int(font_size / 25))
            
            # Draw Opaque Text with Outline
            draw.text((x, y), text, font=font, fill=(255, 255, 255, 255), stroke_width=stroke_width, stroke_fill=(0, 0, 0, 255))
            
            # Apply Global Transparency (e.g. 35% Opacity)
            # Split channels, multiply alpha by 0.35, merge back
            r, g, b, a = txt_layer.split()
            a = a.point(lambda p: int(p * 0.35))
            txt_layer = Image.merge('RGBA', (r, g, b, a))
            
            # Composite
            combined = Image.alpha_composite(img, txt_layer)
            
            output = io.BytesIO()
            combined.save(output, format="PNG")
            output.seek(0)
            return output
    except Exception as e:
        print(f"Error processing image: {e}", flush=True)
        return None

# ... (Inside on_message) ...
    async def on_message(self, message):
        if message.author == self.user:
            return

        if message.channel.name == WATERMARK_CHANNEL_NAME and message.attachments:
            processed_files = []
            for attachment in message.attachments:
                if attachment.content_type and "image" in attachment.content_type:
                    try:
                        image_bytes = await attachment.read()
                        
                        # Process in executor to avoid blocking
                        loop = asyncio.get_running_loop()
                        watermarked_io = await loop.run_in_executor(None, add_watermark, image_bytes)
                        
                        if watermarked_io:
                            processed_files.append(discord.File(fp=watermarked_io, filename=f"watermarked_{attachment.filename}"))
                    except Exception as e:
                        print(f"Failed to watermark attachment: {e}", flush=True)
            
            if processed_files:
                await message.channel.send(
                    f"📸 **Image by {message.author.mention}**", 
                    files=processed_files
                )
                await message.delete()
                return

        if message.content == "!sync":
# ...
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
    print(f"🌍 Dummy server started on port {port}", flush=True)

# Helper function to auto-push to GitHub via API
# BLOCKING function (will be run in executor)
def _blocking_sync(data):
    if not GITHUB_TOKEN:
        print("⚠️ GITHUB_TOKEN not found. Skipping sync.", flush=True)
        return

    # 1. Generate the content
    codes = set()
    for user_id, info in data.items():
        if info.get('friend_code') and info.get('status') == 'online':
            codes.add(info['friend_code'])
    file_content = "\n".join(sorted(list(codes)))

    try:
        auth = Auth.Token(GITHUB_TOKEN) # Fixed Deprecation
        g = Github(auth=auth)
        repo = g.get_repo(REPO_NAME)
        
        # 2. Try to get the existing file (we need its 'sha' to update it)
        try:
            contents = repo.get_contents("ids.txt")
            repo.update_file(contents.path, "[skip ci] [skip render] Bot: Update active IDs", file_content, contents.sha) # Added [skip ci]
            print("🚀 Pushed to GitHub (Updated)!", flush=True)
        except Exception:
            # File doesn't exist, create it
            repo.create_file("ids.txt", "[skip ci] [skip render] Bot: Create IDs file", file_content) # Added [skip ci]
            print("🚀 Pushed to GitHub (Created)!", flush=True)
            
    except Exception as e:
        print(f"❌ GitHub API Error: {e}", flush=True)

# ASYNC wrapper calls the blocking one in a thread
async def sync_to_github(data):
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _blocking_sync, data)

# Helper to sync state from GitHub (Persistence + Self-Healing)
# BLOCKING sync
def _blocking_initial_sync():
    if not GITHUB_TOKEN: return
    try:
        auth = Auth.Token(GITHUB_TOKEN)
        g = Github(auth=auth)
        repo = g.get_repo(REPO_NAME)
        
        # 1. Download users.json
        data = {}
        try:
            contents = repo.get_contents(DATA_FILE)
            with open(DATA_FILE, "wb") as f:
                f.write(contents.decoded_content)
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
            print(f"✅ Downloaded {DATA_FILE}", flush=True)
        except Exception as e:
            print(f"⚠️ Could not download {DATA_FILE}: {e}", flush=True)

        # 2. Download ids.txt and Sync Status
        try:
            ids_content = repo.get_contents("ids.txt")
            online_ids = set(ids_content.decoded_content.decode().splitlines())
            
            updated = False
            for user_id, info in data.items():
                code = info.get('friend_code')
                if code in online_ids:
                    if info.get('status') != 'online':
                        info['status'] = 'online'
                        updated = True
                else:
                    if info.get('status') == 'online':
                        info['status'] = 'offline'
                        updated = True
            
            if updated:
                with open(DATA_FILE, "w") as f:
                    json.dump(data, f, indent=4)
                print("🔄 Synced local statuses with ids.txt", flush=True)
                
        except Exception as e:
            print(f"⚠️ Could not sync with ids.txt: {e}", flush=True)

    except Exception as e:
        print(f"❌ GitHub Init Error: {e}", flush=True)

async def download_users_from_github():
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _blocking_initial_sync)

# Helper to upload users.json to GitHub (Persistence)
# BLOCKING upload
def _blocking_upload(data):
    if not GITHUB_TOKEN: return
    json_content = json.dumps(data, indent=4)
    try:
        auth = Auth.Token(GITHUB_TOKEN) # Fixed Deprecation
        g = Github(auth=auth)
        repo = g.get_repo(REPO_NAME)
        try:
            contents = repo.get_contents(DATA_FILE)
            repo.update_file(contents.path, "[skip ci] [skip render] Bot: Save User DB", json_content, contents.sha)
        except Exception:
            repo.create_file(DATA_FILE, "[skip ci] [skip render] Bot: Create User DB", json_content)
        print(f"💾 Saved {DATA_FILE} to GitHub", flush=True)
    except Exception as e:
        print(f"❌ Failed to save {DATA_FILE} to GitHub: {e}", flush=True)

async def upload_users_to_github(data):
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _blocking_upload, data)

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

# Updated to use ASYNC upload - Caller must await this!
async def save_data_async(data):
    # 1. Save locally
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)
    # 2. Sync to Cloud (Async)
    await upload_users_to_github(data)

# Legacy save (sync) for non-async contexts (if any) - Renamed from save_data
def save_data_sync(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)
    # Cannot await upload_users_to_github here without a loop
    # Ideally all saves should be async now.

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

# bot = MyBot() # This line is also duplicated, keeping the first one.

@bot.command()
async def sync(ctx):
    print(f"Manual sync triggered by {ctx.author}", flush=True)
    if ctx.guild:
        bot.tree.copy_global_to(guild=ctx.guild)
        await bot.tree.sync(guild=ctx.guild)
        await ctx.send(f"✅ **Force Synced!** Commands available in **{ctx.guild.name}** immediately.")
    else:
        await bot.tree.sync()
        await ctx.send("Synced globally.")

@bot.event
async def on_member_join(member):
    guild = member.guild
    print(f"Member joined: {member.name}", flush=True)

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
        print(f"Created channel for {member.name}", flush=True)
        
    except Exception as e:
        print(f"Error creating channel: {e}", flush=True)

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
            print(f"Could not ping in check-in: {e}", flush=True)

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

    # 1. Existing User Check (Prevent Re-registration)
    if user_id in data:
        current_code = data[user_id].get('friend_code', 'Not Set')
        current_status = data[user_id].get('status', 'offline')
        await interaction.followup.send(
            f"❌ **You are already registered!**\n"
            f"• Friend Code: `{current_code}`\n"
            f"• Status: `{current_status}`\n\n"
            f"• Prior Status: `{current_status}`\n\n"
            f"💡 **Want to go Online?** Run `/rg_online`.\n"
            f"💡 **Want to change ID?** Run `/rg_unadd_user` first.",
            ephemeral=True
        )
        return

    # 2. Check for Duplicates (Global Uniqueness)
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
    await save_data_async(data) # Updated to async save

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
        await save_data_async(data) # Updated to async save
        await sync_to_github(data) # Reverted to sync_to_github (Updates ids.txt)
        await interaction.followup.send("🗑️ **Unregistered.** Your data has been wiped. You can now register a new ID.")
    else:
        await interaction.followup.send("❌ You are not registered.", ephemeral=True)

@bot.tree.command(name="rg_change_id", description="Update your Friend Code without losing your status")
@app_commands.describe(new_code="Your NEW 16-digit Friend Code")
async def rg_change_id(interaction: discord.Interaction, new_code: str):
    # Validation
    if not new_code.isdigit() or len(new_code) != 16:
        await interaction.response.send_message(
            f"❌ **Error**: Friend Code must be exactly 16 digits.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=False)
    
    user_id = str(interaction.user.id)
    data = load_data()
    
    # Check registration
    if user_id not in data:
        await interaction.followup.send("❌ You are not registered! proper use: `/rg_add_user` first.", ephemeral=True)
        return

    # Check Global Uniqueness
    for existing_id, info in data.items():
        if info.get('friend_code') == new_code and existing_id != user_id:
            await interaction.followup.send(
                f"❌ **Error**: This Friend Code is already registered by another user.",
                ephemeral=True
            )
            return

    old_code = data[user_id].get('friend_code')
    
    # Update Data
    data[user_id]['friend_code'] = new_code
    await save_data_async(data) # Update DB
    
    # If Online, we must update the public list immediately
    if data[user_id].get('status') == 'online':
        await sync_to_github(data)
        
    await interaction.followup.send(
        f"✅ **ID Updated!**\n"
        f"Old: `{old_code}`\n"
        f"New: `{new_code}`"
    )

@bot.tree.command(name="rg_online", description="Set your status to ONLINE and start accepting requests")
async def rg_online(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False) # Defer immediately

    user_id = str(interaction.user.id)
    data = load_data()
    
    if user_id not in data:
        await interaction.followup.send("❌ You are not registered! proper use: `/rg_add_user` first.", ephemeral=True)
        return

    # Check if already online
    if data[user_id].get('status') == 'online':
        await interaction.followup.send("⚠️ **Already Online!** You are already in the queue.", ephemeral=True)
        return

    data[user_id]['status'] = 'online'
    await save_data_async(data) # Update DB
    await sync_to_github(data) # Reverted to sync_to_github (Updates ids.txt)

    # Verification Step
    msg = await interaction.followup.send(f"⏳ **Verifying accessibility...** (Checking https://arwin.de/ids.txt)")
    
    verified = False
    friend_code = data[user_id]['friend_code']
    
    for i in range(12): # Try for 60 seconds
        try:
            async with aiohttp.ClientSession() as session:
                # Add timestamp to bypass cache
                async with session.get(f"https://arwin.de/ids.txt?t={int(datetime.now().timestamp())}") as response:
                    if response.status == 200:
                        text = await response.text()
                        if friend_code in text:
                            verified = True
                            break
        except Exception as e:
            print(f"Verification Check Failed: {e}", flush=True)
            
        await asyncio.sleep(5)
    
    if verified:
        await msg.edit(content=f"🟢 **Online!** {interaction.user.mention} is now accepting friend requests.\n✅ **Verified:** Your ID is visible on the public list.")
        await update_channel_status(interaction.client)
    else:
        await msg.edit(content=f"⚠️ **Pushed directly to GitHub**, but `arwin.de` is taking a while to update.\nYour ID *will* appear shortly.")

@bot.tree.command(name="rg_offline", description="Set your status to OFFLINE")
async def rg_offline(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False) # Defer immediately

    user_id = str(interaction.user.id)
    data = load_data()
    
    if user_id in data:
        # Check if already offline
        if data[user_id].get('status') == 'offline':
            await interaction.followup.send("⚠️ **Already Offline!** You are not in the queue.", ephemeral=True)
            return

        data[user_id]['status'] = 'offline'
        await save_data_async(data) # Update DB
        await sync_to_github(data) # Reverted to sync_to_github (Updates ids.txt)
    
    await interaction.followup.send(
        f"🔴 **Offline.** {interaction.user.mention} has stopped accepting requests.\n"
        f"Your ID has been removed from the global list."
    )
    await update_channel_status(interaction.client)

@bot.tree.command(name="rg_update_bot", description="[Admin] Upload a new bot.py file to update the bot remotely")
@app_commands.describe(file="The new bot.py file")
@app_commands.checks.has_permissions(administrator=True)
async def rg_update_bot(interaction: discord.Interaction, file: discord.Attachment):
    if not file.filename.endswith(".py"):
        await interaction.response.send_message("❌ Error: File must be a Python file (.py)", ephemeral=True)
        return
        
    await interaction.response.defer(ephemeral=False)
    
    try:
        content = await file.read()
        
        # Determine strict file path for bot.py in the repo root
        file_path = "bot.py"
        
        # Use blocking helper for GitHub API call
        def _blocking_update_bot_file():
            auth = Auth.Token(GITHUB_TOKEN)
            g = Github(auth=auth)
            repo = g.get_repo(REPO_NAME)
            contents = repo.get_contents(file_path)
            repo.update_file(contents.path, f"Bot: Remote Update by {interaction.user.name}", content, contents.sha)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _blocking_update_bot_file)
        
        await interaction.followup.send("✅ **Update Pushed!** Render should restart the bot automatically in ~1 minute.")
    except Exception as e:
        await interaction.followup.send(f"❌ Update failed: {e}", ephemeral=True)

# ... (Run Check stays the same) ...
if __name__ == "__main__":
    if TOKEN == "PASTE_YOUR_TOKEN_HERE":
        print("ERROR: Please put your bot token in the bot.py file on line 6.", flush=True)
    else:
        bot.run(TOKEN)
