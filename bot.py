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
HEARTBEAT_CHANNEL_ID = 1450631414432272454
LIVE_PACKS_ID = 1455270012544876635
DEAD_PACKS_ID = 1455283748118462652
CHECKIN_PING_ID = 1450630077753856121
WHITELIST_FILE = "whitelist.txt"
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

def load_whitelist():
    defaults = {"MegaGyarados", "MegaBlaziken", "MegaAltaria", "CrimsonBlaze"}
    if not os.path.exists(WHITELIST_FILE):
        return list(defaults)
        
    try:
        with open(WHITELIST_FILE, "r") as f:
            content = f.read().strip()
            if not content: return list(defaults)
            return [line.strip() for line in content.splitlines() if line.strip()]
    except Exception:
        return list(defaults)

def _blocking_upload_whitelist(data_list):
    if not GITHUB_TOKEN: return
    content = "\n".join(sorted(list(set(data_list))))
    try:
        auth = Auth.Token(GITHUB_TOKEN)
        g = Github(auth=auth)
        repo = g.get_repo(REPO_NAME)
        try:
            contents = repo.get_contents(WHITELIST_FILE)
            repo.update_file(contents.path, "[skip ci] [skip render] Bot: Update whitelist", content, contents.sha)
        except Exception:
            repo.create_file(WHITELIST_FILE, "[skip ci] [skip render] Bot: Create whitelist", content)
        print(f"💾 Saved {WHITELIST_FILE} to GitHub", flush=True)
    except Exception as e:
        print(f"❌ Failed to save {WHITELIST_FILE} to GitHub: {e}", flush=True)

async def save_whitelist_async(data_list):
    try:
        with open(WHITELIST_FILE, "w") as f:
            f.write("\n".join(sorted(list(set(data_list)))))
    except Exception as e:
        print(f"Error saving local whitelist: {e}", flush=True)
        
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _blocking_upload_whitelist, data_list)

async def manage_roles(member, status):
    if member.bot: return
    
    guild = member.guild
    role_rerolling = discord.utils.get(guild.roles, name=ROLE_REROLLING)
    role_not_rerolling = discord.utils.get(guild.roles, name=ROLE_NOT_REROLLING)

    if not role_rerolling:
        try:
            role_rerolling = await guild.create_role(name=ROLE_REROLLING, color=discord.Color.green(), hoist=True, permissions=discord.Permissions.none())
        except: pass

    if not role_not_rerolling:
        try:
            role_not_rerolling = await guild.create_role(name=ROLE_NOT_REROLLING, color=discord.Color.red(), hoist=True, permissions=discord.Permissions.none())
        except: pass

    try:
        if status == 'online':
            if role_rerolling: await member.add_roles(role_rerolling)
            if role_not_rerolling: await member.remove_roles(role_not_rerolling)
        else:
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
        
        ids = set()
        file_sha = None
        try:
            contents = repo.get_contents("vip_ids.txt")
            file_sha = contents.sha
            existing_text = contents.decoded_content.decode()
            ids = set(existing_text.splitlines())
        except Exception:
            pass 
            
        if new_id not in ids:
            ids.add(new_id)
            new_content = "\n".join(sorted(list(ids)))
            
            if file_sha:
                repo.update_file("vip_ids.txt", "[skip ci] [skip render] Bot: Update VIP IDs", new_content, file_sha)
            else:
                repo.create_file("vip_ids.txt", "[skip ci] [skip render] Bot: Create VIP IDs", new_content)
            print(f"💎 Added VIP ID {new_id} to vip_ids.txt", flush=True)
            
    except Exception as e:
        print(f"❌ Failed to update vip_ids.txt: {e}", flush=True)

async def update_vip_list(new_id):
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _blocking_update_vip, new_id)

def count_online_users(data):
    count = 0
    for info in data.values():
        if info.get('status') == 'online' or info.get('secondary_status') == 'online':
            count += 1
    return count

def get_checkin_channel(guild):
    for ch in guild.text_channels:
        if CHECKIN_CHANNEL_NAME in ch.name:
            return ch
    return None

def add_watermark(image_bytes):
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = img.convert("RGBA")
            txt_layer = Image.new('RGBA', img.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(txt_layer)
            text = "EternalGP"
            width, height = img.size
            font_size = int(height * 0.09) 
            if font_size < 15: font_size = 15
            try:
                 font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
            except:
                 font = ImageFont.load_default()
            left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
            text_width = right - left
            text_height = bottom - top
            x = (width - text_width) / 2
            y = (height - text_height) / 2
            stroke_width = max(1, int(font_size / 25))
            draw.text((x, y), text, font=font, fill=(255, 255, 255, 255), stroke_width=stroke_width, stroke_fill=(0, 0, 0, 255))
            r, g, b, a = txt_layer.split()
            a = a.point(lambda p: int(p * 0.35))
            txt_layer = Image.merge('RGBA', (r, g, b, a))
            combined = Image.alpha_composite(img, txt_layer)
            output = io.BytesIO()
            combined.save(output, format="PNG")
            output.seek(0)
            return output
    except Exception as e:
        print(f"Error processing image: {e}", flush=True)
        return None

    async def on_message(self, message):
        # 1. VIP ID Extraction
        if message.channel.name == SOURCE_CHANNEL_NAME:
            if "Invalid" in message.content:
                print(f"⚠️ Ignored Invalid Pack message from {message.author}", flush=True)
                try: await message.delete() 
                except: pass
                return

            match = re.search(r'\((\d{16})\)', message.content)
            if match:
                vip_id = match.group(1)
                print(f"🔍 Detected VIP ID: {vip_id}", flush=True)
                # We still allow auto-add, or should we wait for Alive? 
                # User didn't specify changing this logic, so we keep auto-add.
                await update_vip_list(vip_id)
                
            # TRIAGE: If Webhook, Repost with Buttons
            if message.webhook_id:
                view = PackView()
                files = []
                # Repost attachments
                if message.attachments:
                    try:
                        for attachment in message.attachments:
                            # We must read into BytesIO because we can't reuse the attachment object directly easily
                            # Actually await attachment.to_file() works
                            files.append(await attachment.to_file())
                    except: pass
                
                try:
                    await message.channel.send(content=message.content, files=files, view=view)
                    await message.delete()
                except Exception as e:
                    print(f"Failed to triage pack: {e}", flush=True)
                return # Stop processing (we handled it)

        # 2. Smart Heartbeat Routing & Policing
        # Check if channel is a 'home-' channel AND message is from a webhook
        if message.channel.name.startswith("home-") and message.webhook_id:
            try:
                # Identify Member from Channel Name (home-username)
                username_from_channel = message.channel.name.replace("home-", "")
                member = discord.utils.get(message.guild.members, name=username_from_channel)
                
                # If member not found by name, try looking up in our DB if possible, or just skip policing (can't ban null)
                # We'll validte if we have the user_id in our DB
                user_id = str(member.id) if member else None
                
                if not member or not user_id: 
                    # Try to match DB username?
                    # For now, if we can't find the member object, we can't effectively ban (role/ping). 
                    # We will still forward blindly? No, user specified "take ID offline" - requires DB access.
                    pass

                # Proceed only if we identified the member and they are in our DB logic (implicitly)
                # ACTUALLY, we can just check if user_id is in load_data()
                data = load_data()
                
                if user_id and user_id in data:
                    content = message.content
                    reason = None
                    
                    # --- RULE 2: "1P Method" ---
                    if "1P Method" in content:
                        reason = "Forbidden Strategy: 1P Method detected."

                    # --- PARSING ---
                    # Time: 120m Packs: 414
                    # Opening: CrimsonBlaze,
                    time_match = re.search(r"Time:\s*(\d+)m\s*Packs:\s*(\d+)", content)
                    opening_match = re.search(r"Opening:\s*(.+)", content) # Capture rest of line
                    
                    current_time = int(time_match.group(1)) if time_match else 0
                    current_packs = int(time_match.group(2)) if time_match else 0
                    
                    # --- RULE 1: Stalling (Time +30m, Packs same) ---
                    if time_match:
                        last_stats = data[user_id].get('last_heartbeat', {})
                        last_time = last_stats.get('time', 0)
                        last_packs = last_stats.get('packs', 0)
                        
                        # Check: New Time is roughly ~30m more (allow >= 25) AND Packs are identical
                        # Only check if we actually have history (last_time > 0)
                        if last_time > 0 and (current_time - last_time) >= 25 and current_packs == last_packs:
                            reason = f"Stalling Detected: Time passed ({current_time - last_time}m) but Packs ({current_packs}) did not increase."
                            
                    # --- RULE 3: Wrong Pack Type ---
                    if not reason and opening_match:
                        opening_str = opening_match.group(1).replace(",", " ").strip()
                        
                        allowed_packs = set(load_whitelist())
                        
                        # Split by space and check each word (ignoring empty strings)
                        found_words = [w for w in opening_str.split() if w]
                        for word in found_words:
                            if word not in allowed_packs:
                                reason = f"Forbidden Pack: '{word}' is not allowed."
                                break

                    if reason:
                        # BAN HAMMER
                        print(f"🚫 POLICING BAN: {member.name} - {reason}", flush=True)
                        
                        # 1. Update Data (Offline)
                        data[user_id]['status'] = 'offline'
                        data[user_id]['secondary_status'] = 'offline' 
                        # Clear heartbeat history on ban so they can reset
                        if 'last_heartbeat' in data[user_id]: del data[user_id]['last_heartbeat']
                        
                        await save_data_async(data)
                        await sync_to_github(data)
                        
                        # 2. Roles
                        await manage_roles(member, 'offline')
                        await update_channel_status(self) # Update check-in count
                        
                        # 3. Ping in Check-in
                        try:
                            checkin_ping_channel = await self.fetch_channel(CHECKIN_PING_ID)
                            await checkin_ping_channel.send(
                                f"🚨 {member.mention} **has been automatically taken offline.**\n"
                                f"**Reason:** {reason}\n"
                                f"Please adjust your settings before checking in again."
                            )
                        except Exception as e:
                            print(f"Failed to ping ban in check-in: {e}", flush=True)
                        
                        # Continue to forward for transparency

                    else:
                        # ALL GOOD - Update History
                        if time_match:
                            data[user_id]['last_heartbeat'] = {'time': current_time, 'packs': current_packs}
                            await save_data_async(data)
                        
                    # ALWAYS Forward to Heartbeat Channel (Transparency)
                    try:
                        hb_channel = await self.fetch_channel(HEARTBEAT_CHANNEL_ID)
                        # Replicate Format: MemberName\nContent
                        forward_msg = f"{member.name}\n{content}"
                        await hb_channel.send(forward_msg)
                    except Exception as e:
                            print(f"Failed to forward heartbeat: {e}", flush=True)

            except Exception as e:
                print(f"⚠️ Heartbeat Policing Error: {e}", flush=True)


        # ... (Existing Check for self.user to prevent loops) ...
        if message.author == self.user:
            return

        # 2. Watermarking
        # ...

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
        
class PackView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Alive", style=discord.ButtonStyle.green, custom_id="pack_alive")
    async def alive_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_triage(interaction, LIVE_PACKS_ID, "Alive")

    @discord.ui.button(label="Dead", style=discord.ButtonStyle.red, custom_id="pack_dead")
    async def dead_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_triage(interaction, DEAD_PACKS_ID, "Dead")

    async def handle_triage(self, interaction: discord.Interaction, channel_id, action):
        target_channel = interaction.guild.get_channel(channel_id)
        if not target_channel:
            try: target_channel = await interaction.guild.fetch_channel(channel_id)
            except: 
                await interaction.response.send_message("❌ Target channel not found.", ephemeral=True)
                return

        # Prepare Content
        content = interaction.message.content
        files = []
        if interaction.message.attachments:
            try:
                for attachment in interaction.message.attachments:
                    files.append(await attachment.to_file())
            except: pass
            
        header = f"✅ **Alive** (Checked by {interaction.user.mention})" if action == "Alive" else f"❌ **Dead** (Checked by {interaction.user.mention})"
        final_msg = f"{header}\n\n{content}"
        
        try:
            await target_channel.send(content=final_msg, files=files)
            await interaction.message.delete() # Clean up original
        except Exception as e:
            await interaction.message.delete()
            await interaction.response.send_message(f"❌ Failed to move: {e}", ephemeral=True)

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
        # Primary ID
        if info.get('friend_code') and info.get('status') == 'online':
            codes.add(info['friend_code'])
        # Secondary ID
        if info.get('secondary_code') and info.get('secondary_status') == 'online':
            codes.add(info['secondary_code'])
            
    file_content = "\n".join(sorted(list(codes)))

    try:
        auth = Auth.Token(GITHUB_TOKEN)
        g = Github(auth=auth)
        repo = g.get_repo(REPO_NAME)
        
        try:
            contents = repo.get_contents("ids.txt")
            repo.update_file(contents.path, "[skip ci] [skip render] Bot: Update active IDs", file_content, contents.sha)
            print("🚀 Pushed to GitHub (ids.txt Updated)!", flush=True)
        except Exception:
            repo.create_file("ids.txt", "[skip ci] [skip render] Bot: Create IDs file", file_content)
            print("🚀 Pushed to GitHub (ids.txt Created)!", flush=True)

        # Sync ids2.txt
        try:
            contents = repo.get_contents("ids2.txt")
            repo.update_file(contents.path, "[skip ci] [skip render] Bot: Update active IDs (Backup)", file_content, contents.sha)
            print("🚀 Pushed to GitHub (ids2.txt Updated)!", flush=True)
        except Exception:
            repo.create_file("ids2.txt", "[skip ci] [skip render] Bot: Create IDs 2 file", file_content)
            print("🚀 Pushed to GitHub (ids2.txt Created)!", flush=True)
            
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

        # 2. Download Whitelist
        try:
            try:
                w_contents = repo.get_contents(WHITELIST_FILE)
                with open(WHITELIST_FILE, "wb") as f:
                    f.write(w_contents.decoded_content)
                print(f"✅ Downloaded {WHITELIST_FILE}", flush=True)
            except Exception:
                 # File doesn't exist on GitHub -> Create it with Defaults
                 print(f"⚠️ {WHITELIST_FILE} not found on GitHub. Creating defaults...", flush=True)
                 defaults = ["MegaGyarados", "MegaBlaziken", "MegaAltaria", "CrimsonBlaze"]
                 content = "\n".join(sorted(defaults))
                 repo.create_file(WHITELIST_FILE, "[skip ci] [skip render] Bot: Init Whitelist", content)
                 # Also save locally
                 with open(WHITELIST_FILE, "w") as f:
                     f.write(content)
                 print(f"🚀 Created {WHITELIST_FILE} on GitHub and Local.", flush=True)
        except Exception as e:
            print(f"⚠️ Whitelist sync failed: {e}", flush=True)

        # 3. Download ids.txt and Sync Status
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

async def cleanup_duplicate_roles(guild):
    # Cleanup Rerolling Duplicates
    rerolling_roles = [r for r in guild.roles if r.name == ROLE_REROLLING]
    if len(rerolling_roles) > 1:
        print(f"⚠️ Found {len(rerolling_roles)} roles named '{ROLE_REROLLING}'. Cleaning up...", flush=True)
        # Keep the one with the highest position (or just the first one)
        # We'll just keep the first one and delete the rest
        for role in rerolling_roles[1:]:
            try:
                await role.delete(reason="Bot Cleanup: Duplicate Role")
                print(f"🗑️ Deleted duplicate role '{ROLE_REROLLING}' (ID: {role.id})", flush=True)
            except Exception as e:
                print(f"Failed to delete duplicate role: {e}", flush=True)

    # Cleanup Not Rerolling Duplicates
    not_rerolling_roles = [r for r in guild.roles if r.name == ROLE_NOT_REROLLING]
    if len(not_rerolling_roles) > 1:
        print(f"⚠️ Found {len(not_rerolling_roles)} roles named '{ROLE_NOT_REROLLING}'. Cleaning up...", flush=True)
        for role in not_rerolling_roles[1:]:
            try:
                await role.delete(reason="Bot Cleanup: Duplicate Role")
                print(f"🗑️ Deleted duplicate role '{ROLE_NOT_REROLLING}' (ID: {role.id})", flush=True)
            except Exception as e:
                print(f"Failed to delete duplicate role: {e}", flush=True)

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

# --- BOT CLASS & INSTANTIATION ---
# CRITICAL: This must come BEFORE any @bot.tree.command decorators

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await download_users_from_github()
        await self.tree.sync()
        self.add_view(PackView()) # Persist View
        print("Synced slash commands globally!", flush=True)
        self.loop.create_task(start_dummy_server())
        self.check_bans.start()
        self.cleanup_checkin.start()
        self.update_heartbeat_ppm.start()

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})", flush=True)
        print("------", flush=True)
        await update_channel_status(self)
        
        # Sync Roles for ALL Members (Startup)
        data = load_data()
        online_users = {uid for uid, info in data.items() if info.get('status') == 'online'}
        
        print("🔄 Syncing roles for all members...", flush=True)
        for guild in self.guilds:
            # 1. Cleanup Duplicates first
            await cleanup_duplicate_roles(guild)
            
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
    
    @tasks.loop(minutes=15)
    async def update_heartbeat_ppm(self):
        try:
            channel = await self.fetch_channel(HEARTBEAT_CHANNEL_ID)
        except Exception as e:
            print(f"⚠️ Heartbeat channel fetch failed: {e}", flush=True)
            return

        try:
            # Stats dictionary: {member_name: ppm}
            member_stats = {}
            
            # Fetch lookback (30 min heartbeat + 10 min buffer)
            cutoff = datetime.now() - timedelta(minutes=40)
            
            # Process NEWEST messages first
            async for message in channel.history(limit=100, after=cutoff):
                if not message.content: continue
                
                # FILTER: Only include specific bot types
                if "Type: Inject Wonderpick 96P+" not in message.content:
                    continue

                lines = message.content.splitlines()
                if not lines: continue
                
                # First line is ID/Name
                member_name = lines[0].strip()
                
                # Extract PPM
                match = re.search(r"Avg:\s*([\d\.]+)\s*packs/min", message.content)
                if match:
                    try:
                        ppm = float(match.group(1))
                        member_stats[member_name] = ppm
                    except ValueError:
                        pass
        
            # Sum totals
            total_ppm = sum(member_stats.values())
            print(f"💓 Calculated Total PPM: {total_ppm} (from {len(member_stats)} bots)", flush=True)
            
            # Rename Channel (Rounded to nearest int)
            new_name = f"💓︱group-heartbeat︱{int(round(total_ppm))} PPM"
            if channel.name != new_name:
                await channel.edit(name=new_name)
                print(f"💓 Updated Heartbeat: {new_name}", flush=True)
                
        except Exception as e:
            print(f"Failed to update Heartbeat PPM: {e}", flush=True)

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
            # FILTER: Ignore invalid packs
            if "Invalid" in message.content:
                print(f"⚠️ Ignored Invalid Pack message from {message.author}", flush=True)
                try: await message.delete() 
                except: pass
                return

            # Look for 16-digit ID in parenthesis: e.g. (9075827188388472)
            match = re.search(r'\((\d{16})\)', message.content)
            if match:
                vip_id = match.group(1)
                print(f"🔍 Detected VIP ID: {vip_id}", flush=True)
                await update_vip_list(vip_id)
            
            # TRIAGE: If Webhook, Repost with Buttons
            if message.webhook_id:
                view = PackView()
                files = []
                if message.attachments:
                    try:
                        for attachment in message.attachments:
                            files.append(await attachment.to_file())
                    except: pass
                
                try:
                    await message.channel.send(content=message.content, files=files, view=view)
                    await message.delete()
                except Exception as e:
                    print(f"Failed to triage pack: {e}", flush=True)
                return # Stop processing (we handled it)

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
        "secondary_code": None,
        "instances": instances,
        "prefix": prefix,
        "status": "offline",
        "secondary_status": "offline"
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

@bot.tree.command(name="rg_add_secondary_id", description="Register a 2nd Friend Code for simultaneous rerolling")
@app_commands.describe(friend_code="Your 2nd In-Game ID")
async def rg_add_secondary_id(interaction: discord.Interaction, friend_code: str):
    if not friend_code.isdigit() or len(friend_code) != 16:
        await interaction.response.send_message("❌ Error: ID must be 16 digits.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)
    user_id = str(interaction.user.id)
    data = load_data()
    
    if user_id not in data:
        await interaction.followup.send("❌ You are not registered! proper use: `/rg_add_user` first.", ephemeral=True)
        return

    for uid, info in data.items():
        if info.get('friend_code') == friend_code or info.get('secondary_code') == friend_code:
             await interaction.followup.send("❌ This ID is already registered.", ephemeral=True)
             return

    data[user_id]['secondary_code'] = friend_code
    data[user_id]['secondary_status'] = 'offline' 
    await save_data_async(data)
    
    await interaction.followup.send(f"✅ **Secondary ID Added!**\nCode: `{friend_code}`\nRun `/rg_online_2nd` to activate it.")

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
    try:
        await interaction.response.defer(ephemeral=False)
    except Exception as e:
        print(f"⚠️ Defer Failed (Unknown Interaction?): {e}", flush=True)
        return

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
    
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4)) as session:
            for i in range(36):
                print(f"🔍 Verification Attempt {i+1}/36 for {friend_code}", flush=True)
                try:
                    async with session.get(f"https://arwin.de/ids.txt?t={int(datetime.now().timestamp())}") as response:
                        if response.status == 200:
                            text = await response.text()
                            if friend_code in text:
                                verified = True
                                break
                except Exception as e:
                    print(f"Verification Check Failed (Attempt {i+1}): {e}", flush=True)
                
                await asyncio.sleep(5)
    except Exception as e:
        print(f"Session Error: {e}", flush=True)
    
    try:
        if verified:
            await msg.edit(content=f"🟢 **Online!** {interaction.user.mention} is now accepting friend requests.\n✅ **Verified:** Your ID is visible on the public list.")
            await manage_roles(interaction.user, 'online')
            await update_channel_status(interaction.client)
        else:
            await msg.edit(content=f"⚠️ **Pushed directly to GitHub**, but `arwin.de` is taking a while to update.\nYour ID *will* appear shortly. (Timed out after 3m)")
    except Exception as e:
         print(f"Failed to edit message: {e}", flush=True)

@bot.tree.command(name="rg_online_2nd", description="Set your SECONDARY ID to ONLINE")
async def rg_online_2nd(interaction: discord.Interaction):
    try:
        await interaction.response.defer(ephemeral=False)
    except: return

    user_id = str(interaction.user.id)
    data = load_data()
    
    if user_id not in data or not data[user_id].get('secondary_code'):
        await interaction.followup.send("❌ **No Secondary ID found!** Use `/rg_add_secondary_id` first.", ephemeral=True)
        return

    if data[user_id].get('secondary_status') == 'online':
        await interaction.followup.send("⚠️ **Secondary ID Already Online!**", ephemeral=True)
        return

    data[user_id]['secondary_status'] = 'online'
    await save_data_async(data)
    await sync_to_github(data)
    
    msg = await interaction.followup.send(f"⏳ **Verifying 2nd ID accessibility...**")
    
    verified = False
    sec_code = data[user_id]['secondary_code']
    
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4)) as session:
            for i in range(36): 
                try:
                    async with session.get(f"https://arwin.de/ids.txt?t={int(datetime.now().timestamp())}") as response:
                        if response.status == 200:
                            text = await response.text()
                            if sec_code in text:
                                verified = True
                                break
                except: pass
                await asyncio.sleep(5)
    except: pass
    
    if verified:
        await msg.edit(content=f"🟢 **Secondary ID Online!** `{sec_code}` is live.")
        await manage_roles(interaction.user, 'online') 
        await update_channel_status(interaction.client)
    else:
        await msg.edit(content=f"⚠️ **Pushed 2nd ID**, but verification timed out. It should appear shortly.")

@bot.tree.command(name="rg_offline", description="Set ALL your IDs to OFFLINE")
async def rg_offline(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)

    user_id = str(interaction.user.id)
    data = load_data()
    
    if user_id in data:
        if data[user_id].get('status') == 'offline' and data[user_id].get('secondary_status') == 'offline':
             await interaction.followup.send("⚠️ **Already Offline!**", ephemeral=True)
             return

        data[user_id]['status'] = 'offline'
        data[user_id]['secondary_status'] = 'offline'
        await save_data_async(data)
        await sync_to_github(data)
        await manage_roles(interaction.user, 'offline')
    
    await interaction.followup.send(
        f"🔴 **Offline.** All your IDs have been removed from the list."
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
        data[user_id]['secondary_status'] = 'offline'
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
        await interaction.followup.send(f"🗑️ **VIP ID Removed!** `{vip_id}` is gone.")
    else:
        await interaction.followup.send(f"❌ Failed: {msg}", ephemeral=True)

@bot.tree.command(name="rg_startingtime", description="[Admin] Set the daily start time channel name")
@app_commands.describe(time="The time to display (e.g. 14:30)")
@app_commands.checks.has_permissions(administrator=True)
async def rg_startingtime(interaction: discord.Interaction, time: str):
    await interaction.response.defer(ephemeral=False)
    
    guild = interaction.guild
    # Sanitized time for Text Channel (lowercase, dashes only)
    clean_time = time.replace(":", "-").replace(" ", "-").lower()
    channel_name = f"todays-start-{clean_time}-utc"
    
    # 1. Find/Create Setup Category
    SETUP_CATEGORY_NAME = "Setup"
    category = discord.utils.get(guild.categories, name=SETUP_CATEGORY_NAME)
    
    if not category:
        try:
            category = await guild.create_category(SETUP_CATEGORY_NAME)
            print(f"Created category: {SETUP_CATEGORY_NAME}", flush=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to create category '{SETUP_CATEGORY_NAME}': {e}", ephemeral=True)
            return

    # 2. Find Existing Channel
    target_channel = None
    for channel in category.text_channels:
        if channel.name.startswith("todays-start"):
            target_channel = channel
            break
            
    # 3. Rename or Create
    try:
        if target_channel:
            if target_channel.name != channel_name:
                await target_channel.edit(name=channel_name)
                await interaction.followup.send(f"✅ Updated channel to: {target_channel.mention}")
            else:
                await interaction.followup.send(f"⚠️ Channel is already named {target_channel.mention}")
        else:
            # Create new
            target_channel = await guild.create_text_channel(channel_name, category=category)
            await target_channel.set_permissions(guild.default_role, send_messages=False) # Read-only
            await interaction.followup.send(f"✅ Created channel: {target_channel.mention}")
            
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to update/create channel: {e}", ephemeral=True)

@rg_update_bot.error
@rg_remove_vip.error
@rg_startingtime.error
async def admin_error(interaction: discord.Interaction, error):
    pass # handled by global mod_error or just ignore

@bot.tree.command(name="rg_whitelist_add", description="[Admin] Add a pack name to the allowed whitelist")
@app_commands.describe(pack_name="The pack string to allow (case sensitive)")
@app_commands.checks.has_permissions(administrator=True)
async def rg_whitelist_add(interaction: discord.Interaction, pack_name: str):
    await interaction.response.defer(ephemeral=False)
    
    current_list = load_whitelist()
    if pack_name in current_list:
        await interaction.followup.send(f"⚠️ `{pack_name}` is already in the whitelist.")
        return

    current_list.append(pack_name)
    await save_whitelist_async(current_list)
    await interaction.followup.send(f"✅ Added `{pack_name}` to whitelist.")

@bot.tree.command(name="rg_whitelist_remove", description="[Admin] Remove a pack name from the allowed whitelist")
@app_commands.describe(pack_name="The pack string to remove")
@app_commands.checks.has_permissions(administrator=True)
async def rg_whitelist_remove(interaction: discord.Interaction, pack_name: str):
    await interaction.response.defer(ephemeral=False)
    
    current_list = load_whitelist()
    if pack_name not in current_list:
        await interaction.followup.send(f"⚠️ `{pack_name}` is not in the whitelist.")
        return

    current_list.remove(pack_name)
    await save_whitelist_async(current_list)
    await interaction.followup.send(f"🗑️ Removed `{pack_name}` from whitelist.")

@bot.tree.command(name="rg_whitelist_list", description="Show all allowed packs")
async def rg_whitelist_list(interaction: discord.Interaction):
    current_list = load_whitelist()
    formatted = "\n".join([f"• {item}" for item in sorted(current_list)])
    await interaction.response.send_message(f"📜 **Allowed Packs Whitelist:**\n\n{formatted}")

@rg_whitelist_add.error
@rg_whitelist_remove.error
@rg_whitelist_list.error
async def whitelist_error(interaction: discord.Interaction, error):
    pass

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
