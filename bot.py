import discord
import os
import asyncio
from discord.ext import commands, tasks
from discord import app_commands
from github import Github, Auth
import json
from aiohttp import web
import aiohttp
from datetime import datetime, timedelta
import re
import io
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = "arwinzbronder-ux/Arwin" # Format: username/repo
CATEGORY_NAME = "Member Channels"
DATA_FILE = "users.json"
CHECKIN_CHANNEL_NAME = "check-in"
WATERMARK_CHANNEL_NAME = "🏆︱live-godpacks-showcase"
SOURCE_CHANNEL_NAME = "🎰︱group-packs"
ROLE_REROLLING = "Rerolling"
ROLE_NOT_REROLLING = "Not Rerolling"

# --- HELPER FUNCTIONS ---

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

async def manage_roles(member, status):
    if member.bot: return
    
    guild = member.guild
    role_rerolling = discord.utils.get(guild.roles, name=ROLE_REROLLING)
    role_not_rerolling = discord.utils.get(guild.roles, name=ROLE_NOT_REROLLING)

    # Auto-Create Roles if Missing (Permissions.none() ensures no unexpected rights)
    if not role_rerolling:
        try:
            role_rerolling = await guild.create_role(name=ROLE_REROLLING, color=discord.Color.green(), hoist=True, permissions=discord.Permissions.none())
            print(f"Created role: {ROLE_REROLLING}", flush=True)
        except Exception as e:
            print(f"Failed to create role {ROLE_REROLLING}: {e}", flush=True)

    if not role_not_rerolling:
        try:
            role_not_rerolling = await guild.create_role(name=ROLE_NOT_REROLLING, color=discord.Color.red(), hoist=True, permissions=discord.Permissions.none())
            print(f"Created role: {ROLE_NOT_REROLLING}", flush=True)
        except Exception as e:
            print(f"Failed to create role {ROLE_NOT_REROLLING}: {e}", flush=True)

    try:
        if status == 'online':
            if role_rerolling: await member.add_roles(role_rerolling)
            if role_not_rerolling: await member.remove_roles(role_not_rerolling)
        else:
             # Default state (Offline / Unregistered / Removed)
            if role_not_rerolling: await member.add_roles(role_not_rerolling)
            if role_rerolling: await member.remove_roles(role_rerolling)
            
    except Exception as e:
        print(f"Failed to update roles for {member.name}: {e}", flush=True)
        
def _blocking_update_vip(new_id):
    if not GITHUB_TOKEN: return
    try:
        auth = Auth.Token(GITHUB_TOKEN)
        g = Github(auth=auth)
        repo = g.get_repo(REPO_NAME)
        
        # 1. Get current VIP IDs
        ids = set()
        file_sha = None
        try:
            contents = repo.get_contents("vip_ids.txt")
            file_sha = contents.sha
            existing_text = contents.decoded_content.decode()
            ids = set(existing_text.splitlines())
        except Exception:
            pass # File might not exist yet
            
        # 2. Add New ID
        if new_id not in ids:
            ids.add(new_id)
            new_content = "\n".join(sorted(list(ids)))
            
            # 3. Save back
            if file_sha:
                repo.update_file("vip_ids.txt", "[skip ci] [skip render] Bot: Update VIP IDs", new_content, file_sha)
                print(f"💎 Added VIP ID {new_id} to vip_ids.txt (Updated)", flush=True)
            else:
                repo.create_file("vip_ids.txt", "[skip ci] [skip render] Bot: Create VIP IDs", new_content)
                print(f"💎 Added VIP ID {new_id} to vip_ids.txt (Created)", flush=True)
        else:
            print(f"ℹ️ VIP ID {new_id} already exists.", flush=True)
            
    except Exception as e:
        print(f"❌ Failed to update vip_ids.txt: {e}", flush=True)

async def update_vip_list(new_id):
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _blocking_update_vip, new_id)

def count_online_users(data):
    count = 0
    for info in data.values():
        if info.get('status') == 'online':
            count += 1
    return count

# Helper to find check-in channel (ignoring status prefix)
def get_checkin_channel(guild):
    # Search for any channel containing the base name
    for ch in guild.text_channels:
        if CHECKIN_CHANNEL_NAME in ch.name:
            return ch
    return None

def add_watermark(image_bytes):
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = img.convert("RGBA")
            
            # Create a transparent text layer
            txt_layer = Image.new('RGBA', img.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(txt_layer)
            text = "EternalGP"
            
            # Calculate dynamic font size (9% of height - Fine tuned)
            width, height = img.size
            font_size = int(height * 0.09) 
            if font_size < 15: font_size = 15
            
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

# --- GITHUB SYNC FUNCTIONS ---

def _blocking_sync(data):
    if not GITHUB_TOKEN:
        print("⚠️ GITHUB_TOKEN not found. Skipping sync.", flush=True)
        return

    codes = set()
    for user_id, info in data.items():
        if info.get('friend_code') and info.get('status') == 'online':
            codes.add(info['friend_code'])
    file_content = "\n".join(sorted(list(codes)))

    try:
        auth = Auth.Token(GITHUB_TOKEN)
        g = Github(auth=auth)
        repo = g.get_repo(REPO_NAME)
        
        try:
            contents = repo.get_contents("ids.txt")
            repo.update_file(contents.path, "[skip ci] [skip render] Bot: Update active IDs", file_content, contents.sha)
            print("🚀 Pushed to GitHub (Updated)!", flush=True)
        except Exception:
            repo.create_file("ids.txt", "[skip ci] [skip render] Bot: Create IDs file", file_content)
            print("🚀 Pushed to GitHub (Created)!", flush=True)
            
    except Exception as e:
        print(f"❌ GitHub API Error: {e}", flush=True)

async def sync_to_github(data):
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _blocking_sync, data)

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

def _blocking_upload(data):
    if not GITHUB_TOKEN: return
    json_content = json.dumps(data, indent=4)
    try:
        auth = Auth.Token(GITHUB_TOKEN)
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

async def save_data_async(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)
    await upload_users_to_github(data)

async def update_channel_status(bot_instance):
    data = load_data()
    online_count = count_online_users(data)
    
    new_prefix = "🟢" if online_count > 0 else "🔴"
    
    # Format: 🟢︱check-in︱3
    new_name = f"{new_prefix}︱{CHECKIN_CHANNEL_NAME}︱{online_count}"
    
    # We scan all guilds (usually just one)
    for guild in bot_instance.guilds:
        channel = get_checkin_channel(guild)
        
        if channel:
            if channel.name == new_name:
                continue # Already correct
            
            try:
                await channel.edit(name=new_name)
                print(f"🔄 Renamed channel to: {new_name}", flush=True)
            except Exception as e:
                print(f"⚠️ Channel Rename Rate Limited (Ignored): {e}", flush=True)

# --- SERVER ---

async def health_check(request):
    return web.Response(text="Bot is ALIVE!")

async def start_dummy_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🌍 Dummy server started on port {port}", flush=True)

# --- BOT CLASS ---

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await download_users_from_github()
        await self.tree.sync()
        print("Synced slash commands globally!", flush=True)
        self.loop.create_task(start_dummy_server())
        self.check_bans.start()
        self.cleanup_checkin.start()

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})", flush=True)
        print("------", flush=True)
        await update_channel_status(self)
        
        # Sync Roles for ALL Members (Startup)
        data = load_data()
        online_users = {uid for uid, info in data.items() if info.get('status') == 'online'}
        
        print("🔄 Syncing roles for all members...", flush=True)
        for guild in self.guilds:
            for member in guild.members:
                if member.bot: continue
                
                status = 'online' if str(member.id) in online_users else 'offline'
                # We spin this off to not block
                self.loop.create_task(manage_roles(member, status))
        print("✅ Role sync initiated.", flush=True)
       
    @tasks.loop(hours=1)
    async def cleanup_checkin(self):
        cutoff = datetime.now() - timedelta(hours=48)
        for guild in self.guilds:
            channel = get_checkin_channel(guild)
            if channel:
                try:
                    # Purge bot messages older than 48h
                    deleted = await channel.purge(
                        limit=None, 
                        check=lambda m: m.author == self.user, 
                        before=cutoff
                    )
                    if deleted:
                        print(f"🧹 Cleaned {len(deleted)} old messages in {channel.name}", flush=True)
                except Exception as e:
                    print(f"Failed to cleanup {channel.name}: {e}", flush=True)

    @tasks.loop(minutes=10)
    async def check_bans(self):
        data = load_data()
        changed = False
        current_time = datetime.now()
        
        for user_id, info in list(data.items()):
            ban_expiry_str = info.get("ban_expiry")
            if ban_expiry_str:
                try:
                    ban_expiry = datetime.fromisoformat(ban_expiry_str)
                    if current_time > ban_expiry:
                        del data[user_id]["ban_expiry"]
                        changed = True
                        
                        if self.guilds:
                            guild = self.guilds[0]
                            member = guild.get_member(int(user_id))
                            channel = get_checkin_channel(guild)
                            if member and channel:
                                await channel.set_permissions(member, overwrite=None)
                                print(f"🔓 Unbanned {member.name}")
                except Exception as e:
                    print(f"Error checking ban for {user_id}: {e}", flush=True)

        if changed:
            await save_data_async(data)

    async def on_message(self, message):
        # 1. VIP ID Extraction (Webhook Messages in Group Packs)
        if message.channel.name == SOURCE_CHANNEL_NAME:
            # Look for 16-digit ID in parenthesis: e.g. (9075827188388472)
            match = re.search(r'\((\d{16})\)', message.content)
            if match:
                vip_id = match.group(1)
                print(f"🔍 Detected VIP ID: {vip_id}", flush=True)
                await update_vip_list(vip_id)

        if message.author == self.user:
            return

        # 2. Watermarking (Images in Godpacks Showcase)
        if message.channel.name == WATERMARK_CHANNEL_NAME and message.attachments:
            processed_files = []
            for attachment in message.attachments:
                if attachment.content_type and "image" in attachment.content_type:
                    try:
                        image_bytes = await attachment.read()
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
            await self.tree.sync()
            await message.channel.send("Synced commands globally!")
        await super().on_message(message)

# CREATE BOT INSTANCE HERE (BEFORE COMMANDS)
bot = MyBot()

# --- COMMANDS ---

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

    category = None
    if CATEGORY_NAME:
        category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
        if not category:
            try:
                category = await guild.create_category(CATEGORY_NAME)
            except Exception:
                pass

    channel_name = f"home-{member.name}"
    private_channel = None
    try:
        private_channel = await guild.create_text_channel(channel_name, overwrites=overwrites, category=category)
        webhook = await private_channel.create_webhook(name=f"{member.name}'s Webhook")
        
        setup_msg = (
            f"Here is your personal webhook URL: ||{webhook.url}||\n\n"
            f"You can use your personal webhook for tracking tradable cards."
        )
        await private_channel.send(setup_msg)
        print(f"Created channel for {member.name}", flush=True)
        
    except Exception as e:
        print(f"Error creating channel: {e}", flush=True)

    # 4. Assign Default Role (Not Rerolling)
    await manage_roles(member, 'offline')

    checkin_channel = get_checkin_channel(guild)
    if checkin_channel:
        try:
            welcome_ping = (
                f"👋 Welcome {member.mention}!\n"
                f"Please read the guide in <#1451910453612777655>.\n"
                f"✅ **Once your AHK bot is ready**, you can check in here."
            )
            await checkin_channel.send(welcome_ping)
        except Exception as e:
            print(f"Could not ping in check-in: {e}", flush=True)

@bot.tree.command(name="rg_add_user", description="Register your reroll instance details")
@app_commands.describe(friend_code="Your In-Game Player ID", instances="Number of instances (excluding main)", prefix="Username prefix")
async def rg_add_user(interaction: discord.Interaction, friend_code: str, instances: int, prefix: str):
    if not friend_code.isdigit() or len(friend_code) != 16:
        await interaction.response.send_message(
            f"❌ **Error**: Friend Code must be exactly 16 digits. You entered `{len(friend_code)}` characters.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=False)
    user_id = str(interaction.user.id)
    data = load_data()

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

    for existing_id, info in data.items():
        if info.get('friend_code') == friend_code and existing_id != user_id:
            await interaction.followup.send(
                f"❌ **Error**: This Friend Code is already registered by another user.",
                ephemeral=True
            )
            return

    data[user_id] = {
        "username": interaction.user.name,
        "friend_code": friend_code,
        "instances": instances,
        "prefix": prefix,
        "status": "offline"
    }
    await save_data_async(data)

    await manage_roles(interaction.user, 'offline')

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
        await save_data_async(data)
        await sync_to_github(data)
        await manage_roles(interaction.user, 'offline')
        await interaction.followup.send("🗑️ **Unregistered.** Your data has been wiped. You can now register a new ID.")
        await update_channel_status(interaction.client)
    else:
        await interaction.followup.send("❌ You are not registered.", ephemeral=True)

@bot.tree.command(name="rg_change_id", description="Update your Friend Code without losing your status")
@app_commands.describe(new_code="Your NEW 16-digit Friend Code")
async def rg_change_id(interaction: discord.Interaction, new_code: str):
    if not new_code.isdigit() or len(new_code) != 16:
        await interaction.response.send_message(
            f"❌ **Error**: Friend Code must be exactly 16 digits.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=False)
    user_id = str(interaction.user.id)
    data = load_data()
    
    if user_id not in data:
        await interaction.followup.send("❌ You are not registered! proper use: `/rg_add_user` first.", ephemeral=True)
        return

    for existing_id, info in data.items():
        if info.get('friend_code') == new_code and existing_id != user_id:
            await interaction.followup.send(
                f"❌ **Error**: This Friend Code is already registered by another user.",
                ephemeral=True
            )
            return

    old_code = data[user_id].get('friend_code')
    data[user_id]['friend_code'] = new_code
    await save_data_async(data)
    
    if data[user_id].get('status') == 'online':
        await sync_to_github(data)
        
    await interaction.followup.send(
        f"✅ **ID Updated!**\n"
        f"Old: `{old_code}`\n"
        f"New: `{new_code}`"
    )

@bot.tree.command(name="rg_online", description="Set your status to ONLINE and start accepting requests")
async def rg_online(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)

    user_id = str(interaction.user.id)
    data = load_data()
    
    if user_id not in data:
        await interaction.followup.send("❌ You are not registered! proper use: `/rg_add_user` first.", ephemeral=True)
        return

    if data[user_id].get('status') == 'online':
        await interaction.followup.send("⚠️ **Already Online!** You are already in the queue.", ephemeral=True)
        return

    data[user_id]['status'] = 'online'
    await save_data_async(data)
    await sync_to_github(data)

    msg = await interaction.followup.send(f"⏳ **Verifying accessibility...** (Checking https://arwin.de/ids.txt)")
    
    verified = False
    friend_code = data[user_id]['friend_code']
    
    for i in range(12):
        try:
            async with aiohttp.ClientSession() as session:
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
        await manage_roles(interaction.user, 'online')
        await update_channel_status(interaction.client)
    else:
        await msg.edit(content=f"⚠️ **Pushed directly to GitHub**, but `arwin.de` is taking a while to update.\nYour ID *will* appear shortly.")

@bot.tree.command(name="rg_offline", description="Set your status to OFFLINE")
async def rg_offline(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)

    user_id = str(interaction.user.id)
    data = load_data()
    
    if user_id in data:
        if data[user_id].get('status') == 'offline':
            await interaction.followup.send("⚠️ **Already Offline!** You are not in the queue.", ephemeral=True)
            return

        data[user_id]['status'] = 'offline'
        await save_data_async(data)
        await sync_to_github(data)
        await manage_roles(interaction.user, 'offline')
    
    await interaction.followup.send(
        f"🔴 **Offline.** {interaction.user.mention} has stopped accepting requests.\n"
        f"Your ID has been removed from the global list."
    )
    await update_channel_status(interaction.client)

@bot.tree.command(name="rg_remove_id", description="[Admin] Remove a Friend Code from the database")
@app_commands.describe(friend_code="The 16-digit ID to remove")
@app_commands.checks.has_permissions(manage_messages=True)
async def rg_remove_id(interaction: discord.Interaction, friend_code: str):
    await interaction.response.defer(ephemeral=False)

    data = load_data()
    found_user_id = None
    
    for user_id, info in data.items():
        if info.get('friend_code') == friend_code:
            found_user_id = user_id
            break
    
    if found_user_id:
        data[found_user_id]['friend_code'] = None
        data[found_user_id]['status'] = 'offline'
        await save_data_async(data)
        await sync_to_github(data)
        
        member = interaction.guild.get_member(int(found_user_id))
        if member:
            await manage_roles(member, 'offline')
        
        await interaction.followup.send(f"🗑️ Removed ID `{friend_code}` from the list and set user to Offline.")
        await update_channel_status(interaction.client)
    else:
        await interaction.followup.send(f"❌ ID `{friend_code}` not found in database.", ephemeral=True)

@bot.tree.command(name="rg_tempban", description="[Admin] Ban a user from the check-in channel for 48h")
@app_commands.describe(member="The user to ban")
@app_commands.checks.has_permissions(manage_messages=True)
async def rg_tempban(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=False)

    expiry_time = datetime.now() + timedelta(hours=48)
    data = load_data()
    user_id = str(member.id)
    if user_id not in data:
         data[user_id] = {}
    
    data[user_id]["ban_expiry"] = expiry_time.isoformat()
    if data[user_id].get('status') == 'online':
        data[user_id]['status'] = 'offline'
        await sync_to_github(data)
        await manage_roles(member, 'offline')
        await update_channel_status(interaction.client)
    
    await save_data_async(data)
    
    channel = get_checkin_channel(member.guild)
    if channel:
        await channel.set_permissions(member, send_messages=False, read_messages=False)
        await interaction.followup.send(f"🚫 Banned {member.mention} from {channel.mention} for 48 hours.")
    else:
        await interaction.followup.send(f"⚠️ Could not find channel `{CHECKIN_CHANNEL_NAME}` to apply ban.", ephemeral=True)

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
        file_path = "bot.py"
        
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

@bot.tree.command(name="rg_remove_vip", description="[Admin] Remove a VIP ID from vip_ids.txt without redeploying")
@app_commands.describe(vip_id="The 16-digit VIP ID to remove")
@app_commands.checks.has_permissions(manage_messages=True)
async def rg_remove_vip(interaction: discord.Interaction, vip_id: str):
    if not vip_id.isdigit() or len(vip_id) != 16:
        await interaction.response.send_message("❌ Error: VIP ID must be 16 digits.", ephemeral=True)
        return
        
    await interaction.response.defer(ephemeral=False)
    
    def _blocking_remove_vip_id():
        if not GITHUB_TOKEN: return False, "No GitHub Token"
        try:
            auth = Auth.Token(GITHUB_TOKEN)
            g = Github(auth=auth)
            repo = g.get_repo(REPO_NAME)
            
            try:
                contents = repo.get_contents("vip_ids.txt")
                file_sha = contents.sha
                existing_text = contents.decoded_content.decode()
                ids = set(existing_text.splitlines())
                
                if vip_id in ids:
                    ids.remove(vip_id)
                    new_content = "\n".join(sorted(list(ids)))
                    repo.update_file("vip_ids.txt", "[skip ci] [skip render] Bot: Remove VIP ID", new_content, file_sha)
                    return True, "Removed"
                else:
                    return False, "ID not found in list"
            except Exception as e:
                return False, str(e)
        except Exception as e:
            return False, str(e)

    loop = asyncio.get_running_loop()
    success, msg = await loop.run_in_executor(None, _blocking_remove_vip_id)
    
    if success:
        await interaction.followup.send(f"🗑️ **VIP ID Removed!** `{vip_id}` is gone. No redeploy triggered.")
    else:
        await interaction.followup.send(f"❌ Failed: {msg}", ephemeral=True)

@rg_update_bot.error
@rg_remove_vip.error
async def admin_error(interaction: discord.Interaction, error):
    pass # handled by global mod_error or just ignore

@rg_remove_id.error
@rg_tempban.error
async def mod_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)

if __name__ == "__main__":
    if TOKEN == "PASTE_YOUR_TOKEN_HERE":
        print("ERROR: Please put your bot token in the bot.py file on line 6.", flush=True)
    else:
        bot.run(TOKEN)
