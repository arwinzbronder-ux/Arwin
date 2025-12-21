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

# --- HELPER FUNCTIONS ---

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}
        
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

# ... (Previous helper functions) ...

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

# ... (Server and Bot Class) ...

# ... (Inside on_member_join) ...

    # 2. Create Private Channel
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

    # 3. Ping them in the CHECK-IN channel
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
