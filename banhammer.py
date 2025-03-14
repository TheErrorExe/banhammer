print("Banhammer Discord Bot, Copyright (C) 2025 TheErrorExe. This program comes with ABSOLUTELY NO WARRANTY. This is free software, and you are welcome to redistribute it under certain conditions. This Bot is licensed under the GPLv3 (GNU General Public License). You should have received a copy of the GNU General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.")

"""
Copyright (C) 2025 TheErrorExe

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import discord
from discord.ext import commands, tasks
import yaml
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict
import random
import string
import os
import asyncio

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, name="banhammer")

config = {}
server_configs = {}

def load_config():
    global config
    if os.path.exists("botconfig.yml"):
        with open("botconfig.yml", "r") as f:
            config = yaml.safe_load(f)
    else:
        config = {
            "token": "YOUR_BOT_TOKEN",
            "database_type": "sqlite",
            "database_name": "modbot.db",
            "mongo_uri": "mongodb://localhost:27017",
            "default_prefix": ".",
            "automod": {"forbidden_words": []}
        }
        with open("botconfig.yml", "w") as f:
            yaml.dump(config, f)
def get_servers_db_connection():
    conn = sqlite3.connect("servers.db")
    conn.row_factory = sqlite3.Row
    return conn

def initialize_servers_db():
    conn = get_servers_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS server_configs (
            guild_id TEXT PRIMARY KEY,
            prefix TEXT,
            automod TEXT,
            modlog_channel TEXT
        )
    ''')
    conn.commit()

def load_server_config(guild_id):
    conn = get_servers_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM server_configs WHERE guild_id = ?", (guild_id,))
    row = cursor.fetchone()
    if row:
        server_configs[guild_id] = {
            "prefix": row["prefix"],
            "automod": yaml.safe_load(row["automod"]),
            "modlog_channel": row["modlog_channel"]
        }
    else:
        server_configs[guild_id] = {
            "prefix": config["default_prefix"],
            "automod": config["automod"].copy(),
            "modlog_channel": None
        }
    return server_configs[guild_id]

def save_server_config(guild_id):
    if guild_id in server_configs:
        conn = get_servers_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO server_configs (guild_id, prefix, automod, modlog_channel)
            VALUES (?, ?, ?, ?)
        ''', (
            guild_id,
            server_configs[guild_id]["prefix"],
            yaml.dump(server_configs[guild_id]["automod"]),
            server_configs[guild_id]["modlog_channel"]
        ))
        conn.commit()
        
def save_config():
    with open("botconfig.yml", "w") as f:
        yaml.dump(config, f)

def get_db_connection(guild_id=None):
    if config["database_type"] == "sqlite":
        db_name = f"server_{guild_id}.db" if guild_id else config["database_name"]
        conn = sqlite3.connect(db_name)
        conn.row_factory = sqlite3.Row
        return conn
    elif config["database_type"] == "mongodb":
        from pymongo import MongoClient
        client = MongoClient(config["mongo_uri"])
        db = client["modbot"] if not guild_id else client[f"server_{guild_id}"]
        return db

def initialize_db(guild_id=None):
    try:
        conn = get_db_connection(guild_id)
        if config["database_type"] == "sqlite":
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    type TEXT,
                    user_id INTEGER,
                    moderator_id INTEGER,
                    reason TEXT,
                    status TEXT,
                    timestamp TEXT,
                    expires_at TEXT,
                    guild_id INTEGER
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS warnings (
                    user_id INTEGER,
                    reason TEXT,
                    guild_id INTEGER
                )
            ''')
            conn.commit()
        elif config["database_type"] == "mongodb":
            db = conn
            if "cases" not in db.list_collection_names():
                db.create_collection("cases")
            if "warnings" not in db.list_collection_names():
                db.create_collection("warnings")
    except Exception as e:
        print(f"Error initializing database: {e}")

def generate_case_id():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=10))

def load_data(guild_id):
    conn = get_db_connection(guild_id)
    if config["database_type"] == "sqlite":
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cases WHERE guild_id = ?", (guild_id,))
        cases = {str(row["case_id"]): dict(row) for row in cursor.fetchall()}
        cursor.execute("SELECT * FROM warnings WHERE guild_id = ?", (guild_id,))
        warnings = defaultdict(list)
        for row in cursor.fetchall():
            warnings[str(row["user_id"])].append(row["reason"])
        return {"cases": cases, "warnings": warnings}
    elif config["database_type"] == "mongodb":
        db = conn
        cases = {str(case["_id"]): case for case in db.cases.find({"guild_id": guild_id})}
        warnings = defaultdict(list)
        for warning in db.warnings.find({"guild_id": guild_id}):
            warnings[str(warning["user_id"])].append(warning["reason"])
        return {"cases": cases, "warnings": warnings}

def save_case(case):
    conn = get_db_connection(case["guild_id"])
    if config["database_type"] == "sqlite":
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO cases (case_id, type, user_id, moderator_id, reason, status, timestamp, expires_at, guild_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (case["case_id"], case["type"], case["user_id"], case["moderator_id"], case["reason"], case["status"], case["timestamp"], case.get("expires_at", ""), case["guild_id"]))
        conn.commit()
    elif config["database_type"] == "mongodb":
        db = conn
        db.cases.insert_one(case)

async def update_case(case_id, status, guild_id):
    conn = get_db_connection(guild_id)
    if config["database_type"] == "sqlite":
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE cases SET status = ? WHERE case_id = ?
        ''', (status, case_id))
        conn.commit()
    elif config["database_type"] == "mongodb":
        db = conn
        db.cases.update_one({"_id": case_id}, {"$set": {"status": status}})

async def delete_case(case_id, guild_id):
    conn = get_db_connection(guild_id)
    if config["database_type"] == "sqlite":
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM cases WHERE case_id = ?
        ''', (case_id,))
        conn.commit()
    elif config["database_type"] == "mongodb":
        db = conn
        db.cases.delete_one({"_id": case_id})

def add_warning(user_id, reason, guild_id):
    conn = get_db_connection(guild_id)
    if config["database_type"] == "sqlite":
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO warnings (user_id, reason, guild_id) VALUES (?, ?, ?)
        ''', (user_id, reason, guild_id))
        conn.commit()
    elif config["database_type"] == "mongodb":
        db = conn
        db.warnings.insert_one({"user_id": user_id, "reason": reason, "guild_id": guild_id})

def remove_warning(user_id, index, guild_id):
    conn = get_db_connection(guild_id)
    if config["database_type"] == "sqlite":
        cursor = conn.cursor()
        cursor.execute("SELECT reason FROM warnings WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
        warnings = cursor.fetchall()
        if 0 < index <= len(warnings):
            cursor.execute('''
                DELETE FROM warnings WHERE user_id = ? AND reason = ? AND guild_id = ?
            ''', (user_id, warnings[index - 1][0], guild_id))
            conn.commit()
    elif config["database_type"] == "mongodb":
        db = conn
        warnings = list(db.warnings.find({"user_id": user_id, "guild_id": guild_id}))
        if 0 < index <= len(warnings):
            db.warnings.delete_one({"_id": warnings[index - 1]["_id"]})

def create_embed(title, description, color=discord.Color.blue()):
    return discord.Embed(title=title, description=description, color=color)

async def notify_user(member, title, description):
    try:
        await member.send(embed=create_embed(title, description, discord.Color.orange()))
    except:
        pass

async def log_action(action, moderator, target, reason, guild_id):
    server_config = load_server_config(guild_id)
    modlog_channel_id = server_config.get("modlog_channel")
    if modlog_channel_id:
        modlog_channel = bot.get_channel(modlog_channel_id)
        if modlog_channel and modlog_channel.permissions_for(modlog_channel.guild.me).send_messages:
            embed = create_embed(
                "📜 Modlog Entry",
                f"**Action:** {action}\n"
                f"**Moderator:** {moderator.mention}\n"
                f"**Target:** {target.mention}\n"
                f"**Reason:** {reason}",
                discord.Color.green()
            )
            await modlog_channel.send(embed=embed)

async def mute_user(member, duration):
    muted_role = discord.utils.get(member.guild.roles, name="Muted")
    if not muted_role:
        muted_role = await member.guild.create_role(name="Muted")
        for channel in member.guild.channels:
            await channel.set_permissions(muted_role, send_messages=False, add_reactions=False)
    await member.add_roles(muted_role)
    if duration > 0:
        await asyncio.sleep(duration)
        await member.remove_roles(muted_role)



@tasks.loop(minutes=1)
async def check_temp_actions():
    temp_actions = load_temp_actions()
    for action in temp_actions[:]:
        if datetime.now() >= action["expires_at"]:
            guild = bot.get_guild(int(action["guild_id"]))
            if guild:
                if action["action_type"] == "tempban":
                    user = await bot.fetch_user(int(action["user_id"]))
                    await guild.unban(user)
                elif action["action_type"] == "tempmute":
                    member = guild.get_member(int(action["user_id"]))
                    if member:
                        muted_role = discord.utils.get(guild.roles, name="Muted")
                        if muted_role and muted_role in member.roles:
                            await member.remove_roles(muted_role)
            remove_temp_action(action["action_id"])
            
def get_actions_db_connection():
    conn = sqlite3.connect("actions.db")
    conn.row_factory = sqlite3.Row
    return conn

def initialize_actions_db():
    conn = get_actions_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS temp_actions (
            action_id TEXT PRIMARY KEY,
            guild_id TEXT,
            user_id TEXT,
            action_type TEXT,
            expires_at TEXT,
            reason TEXT
        )
    ''')
    conn.commit()

def load_temp_actions():
    conn = get_actions_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM temp_actions")
    temp_actions = []
    for row in cursor.fetchall():
        temp_actions.append({
            "action_id": row["action_id"],
            "guild_id": row["guild_id"],
            "user_id": row["user_id"],
            "action_type": row["action_type"],
            "expires_at": datetime.fromisoformat(row["expires_at"]),
            "reason": row["reason"]
        })
    return temp_actions

def save_temp_action(action):
    conn = get_actions_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO temp_actions (action_id, guild_id, user_id, action_type, expires_at, reason)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        action["action_id"],
        action["guild_id"],
        action["user_id"],
        action["action_type"],
        action["expires_at"].isoformat(),
        action.get("reason", "")
    ))
    conn.commit()

def remove_temp_action(action_id):
    conn = get_actions_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM temp_actions WHERE action_id = ?", (action_id,))
    conn.commit()


@bot.command()
@commands.has_permissions(manage_guild=True)
async def configmodlog(ctx, channel: discord.TextChannel):
    server_config = load_server_config(ctx.guild.id)
    server_config["modlog_channel"] = channel.id
    save_server_config(ctx.guild.id)
    await ctx.send(embed=create_embed("✅ Modlog Channel Set", f"Modlog channel set to {channel.mention}"))

@bot.command()
@commands.has_permissions(manage_guild=True)
async def warn(ctx, member: discord.Member, *, reason="No reason provided"):
    case_id = generate_case_id()
    case = {
        "case_id": case_id,
        "type": "warn",
        "user_id": member.id,
        "moderator_id": ctx.author.id,
        "reason": reason,
        "status": "open",
        "timestamp": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "guild_id": ctx.guild.id
    }
    save_case(case)
    add_warning(member.id, reason, ctx.guild.id)
    await ctx.send(embed=create_embed("⚠️ Warning Issued", f"{member.mention} has been warned.\n**Case ID:** {case_id}\n**Reason:** {reason}"))
    await notify_user(member, "⚠️ You have been warned", f"**Server:** {ctx.guild.name}\n**Reason:** {reason}")
    await log_action("Warn", ctx.author, member, reason, ctx.guild.id)

@bot.command()
@commands.has_permissions(manage_guild=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    case_id = generate_case_id()
    case = {
        "case_id": case_id,
        "type": "ban",
        "user_id": member.id,
        "moderator_id": ctx.author.id,
        "reason": reason,
        "status": "open",
        "timestamp": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "guild_id": ctx.guild.id
    }
    save_case(case)
    await member.ban(reason=reason)
    await ctx.send(embed=create_embed("🔨 User Banned", f"{member.mention} has been banned.\n**Case ID:** {case_id}\n**Reason:** {reason}"))
    await log_action("Ban", ctx.author, member, reason, ctx.guild.id)

@bot.command()
@commands.has_permissions(manage_guild=True)
async def timeban(ctx, member: discord.Member, duration: int, *, reason="No reason provided"):
    action_id = generate_case_id()
    expires_at = datetime.now() + timedelta(minutes=duration)
    action = {
        "action_id": action_id,
        "guild_id": str(ctx.guild.id),
        "user_id": str(member.id),
        "action_type": "tempban",
        "expires_at": expires_at,
        "reason": reason
    }
    save_temp_action(action)
    await member.ban(reason=reason)
    await ctx.send(embed=create_embed("🔨 User Temp-Banned", f"{member.mention} has been banned for **{duration} minutes**.\n**Action ID:** {action_id}\n**Reason:** {reason}"))
    await log_action("Temp-Ban", ctx.author, member, reason, ctx.guild.id)
    
@bot.command()
@commands.has_permissions(manage_guild=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    case_id = generate_case_id()
    case = {
        "case_id": case_id,
        "type": "kick",
        "user_id": member.id,
        "moderator_id": ctx.author.id,
        "reason": reason,
        "status": "open",
        "timestamp": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "guild_id": ctx.guild.id
    }
    save_case(case)
    await member.kick(reason=reason)
    await ctx.send(embed=create_embed("👢 User Kicked", f"{member.mention} has been kicked.\n**Case ID:** {case_id}\n**Reason:** {reason}"))
    await log_action("Kick", ctx.author, member, reason, ctx.guild.id)

@bot.command()
@commands.has_permissions(manage_guild=True)
async def mute(ctx, member: discord.Member, *, reason="No reason provided"):
    case_id = generate_case_id()
    case = {
        "case_id": case_id,
        "type": "mute",
        "user_id": member.id,
        "moderator_id": ctx.author.id,
        "reason": reason,
        "status": "open",
        "timestamp": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "guild_id": ctx.guild.id
    }
    save_case(case)
    await mute_user(member, 0)
    await ctx.send(embed=create_embed("🔇 User Muted", f"{member.mention} has been muted.\n**Case ID:** {case_id}\n**Reason:** {reason}"))
    await log_action("Mute", ctx.author, member, reason, ctx.guild.id)

@bot.command()
@commands.has_permissions(manage_guild=True)
async def timemute(ctx, member: discord.Member, duration: int, *, reason="No reason provided"):
    action_id = generate_case_id()
    expires_at = datetime.now() + timedelta(minutes=duration)
    action = {
        "action_id": action_id,
        "guild_id": str(ctx.guild.id),
        "user_id": str(member.id),
        "action_type": "tempmute",
        "expires_at": expires_at,
        "reason": reason
    }
    save_temp_action(action)
    await mute_user(member, duration * 60)
    await ctx.send(embed=create_embed(
        "🔇 User Temp-Muted",
        f"{member.mention} has been muted for **{duration} minutes**.\n"
        f"**Action ID:** {action_id}\n"
        f"**Reason:** {reason}"
    ))
    await log_action("Temp-Mute", ctx.author, member, reason, ctx.guild.id)
    
@bot.command()
@commands.has_permissions(manage_guild=True)
async def caseclose(ctx, case_id: str):
    data = load_data(ctx.guild.id)
    if case_id not in data["cases"]:
        await ctx.send(embed=create_embed("⚠️ Error", "Case not found.", discord.Color.red()))
        return
    await update_case(case_id, "closed", ctx.guild.id)
    await ctx.send(embed=create_embed("✅ Case Closed", f"Case #{case_id} has been closed."))

@bot.command()
@commands.has_permissions(manage_guild=True)
async def casedel(ctx, case_id: str):
    data = load_data(ctx.guild.id)
    if case_id not in data["cases"]:
        await ctx.send(embed=create_embed("⚠️ Error", "Case not found.", discord.Color.red()))
        return
    await delete_case(case_id, ctx.guild.id)
    await ctx.send(embed=create_embed("✅ Case Deleted", f"Case #{case_id} has been deleted."))

@bot.command()
@commands.has_permissions(manage_guild=True)
async def casereopen(ctx, case_id: str):
    data = load_data(ctx.guild.id)
    if case_id not in data["cases"]:
        await ctx.send(embed=create_embed("⚠️ Error", "Case not found.", discord.Color.red()))
        return
    await update_case(case_id, "open", ctx.guild.id)
    await ctx.send(embed=create_embed("✅ Case Reopened", f"Case #{case_id} has been reopened."))

@bot.command()
async def warns(ctx, member: discord.Member = None):
    member = member or ctx.author
    data = load_data(ctx.guild.id)
    warnings = data["warnings"].get(str(member.id), [])
    if warnings:
        warn_list = "\n".join([f"{i+1}. {warn}" for i, warn in enumerate(warnings)])
        await ctx.send(embed=create_embed(f"📋 Warnings for {member.name}", warn_list))
    else:
        await ctx.send(embed=create_embed("📋 No Warnings", f"{member.mention} has no warnings."))

@bot.command(name="userinfo", aliases=["ui"])
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    data = load_data(ctx.guild.id)
    warnings = data["warnings"].get(str(member.id), [])
    roles = [role.mention for role in member.roles if role.name != "@everyone"]
    
    embed = create_embed(
        f"Userinfo: {member.name}",
        f"**ID:** {member.id}\n"
        f"**Joined:** {member.joined_at.strftime('%d.%m.%Y')}\n"
        f"**Created:** {member.created_at.strftime('%d.%m.%Y')}\n"
        f"**Warnings:** {len(warnings)}\n"
        f"**Roles:** {', '.join(roles) if roles else 'No roles'}"
    )
    
    if member.avatar:
        embed.set_thumbnail(url=member.avatar.url)
    else:
        embed.set_thumbnail(url=member.default_avatar.url)
    
    await ctx.send(embed=embed)
    
@bot.command()
@commands.has_permissions(manage_guild=True)
async def automod(ctx, action: str, *, word: str = None):
    server_config = load_server_config(ctx.guild.id)
    automod_words = server_config["automod"].setdefault("forbidden_words", [])

    if action == "add":
        if not word:
            await ctx.send(embed=create_embed("⚠️ Error", "Please specify a word to filter.", discord.Color.red()))
            return
        if word.lower() in automod_words:
            await ctx.send(embed=create_embed("⚠️ Error", "This word is already in the filter.", discord.Color.red()))
            return
        automod_words.append(word.lower())
        save_server_config(ctx.guild.id)
        await ctx.send(embed=create_embed("✅ Automod", f"Word `{word}` added to automoderation."))

    elif action == "remove":
        if not word:
            await ctx.send(embed=create_embed("⚠️ Error", "Please specify a word to remove.", discord.Color.red()))
            return
        if word.lower() not in automod_words:
            await ctx.send(embed=create_embed("⚠️ Error", "This word is not in the filter.", discord.Color.red()))
            return
        automod_words.remove(word.lower())
        save_server_config(ctx.guild.id)
        await ctx.send(embed=create_embed("✅ Automod", f"Word `{word}` removed from automoderation."))

    elif action == "list":
        if not automod_words:
            await ctx.send(embed=create_embed("📋 Automod List", "No forbidden words found."))
        else:
            await ctx.send(embed=create_embed("📋 Automod List", "\n".join(automod_words)))

@bot.command()
async def commands(ctx):
    commands_list = [cmd.name for cmd in bot.commands]
    await ctx.send(embed=create_embed("📜 Available Commands", f"`{', '.join(commands_list)}`"))

@commands.has_permissions(manage_guild=True)
@bot.command()
async def cases(ctx, member: discord.Member = None):
    data = load_data(ctx.guild.id)
    cases = data["cases"]

    if not cases:
        await ctx.send(embed=create_embed("📜 Cases", "No cases found.", discord.Color.blue()))
        return

    if member:
        user_cases = {case_id: case_data for case_id, case_data in cases.items() if case_data["user_id"] == member.id}
        if not user_cases:
            await ctx.send(embed=create_embed("📜 Cases", f"No cases found for {member.mention}.", discord.Color.blue()))
            return
        cases = user_cases

    cases_list = []
    for case_id, case_data in cases.items():
        case_type = case_data["type"]
        user_id = case_data["user_id"]
        moderator_id = case_data["moderator_id"]
        reason = case_data["reason"]
        status = case_data["status"]
        timestamp = case_data["timestamp"]

        cases_list.append(
            f"**Case ID:** {case_id}\n"
            f"**Type:** {case_type}\n"
            f"**User:** <@{user_id}>\n"
            f"**Moderator:** <@{moderator_id}>\n"
            f"**Reason:** {reason}\n"
            f"**Status:** {status}\n"
            f"**Timestamp:** {timestamp}\n"
            "────────────"
        )

    pages = []
    current_page = ""
    for case in cases_list:
        if len(current_page) + len(case) > 2000:
            pages.append(current_page)
            current_page = case
        else:
            current_page += "\n" + case

    if current_page:
        pages.append(current_page)

    for i, page in enumerate(pages):
        embed_title = f"📜 Cases for {member.display_name}" if member else "📜 Cases"
        embed = create_embed(
            f"{embed_title} (Page {i + 1}/{len(pages)})",
            page,
            discord.Color.blue()
        )
        await ctx.send(embed=embed)
        
@bot.event
async def on_ready():
    print(f"✅ {bot.user} is online!")
    initialize_servers_db()
    initialize_actions_db()
    for guild in bot.guilds:
        load_server_config(guild.id)
    check_temp_actions.start()

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    server_config = load_server_config(message.guild.id)
    forbidden_words = server_config["automod"].get("forbidden_words", [])
    content_lower = message.content.lower()

    for word in forbidden_words:
        if word in content_lower:
            await message.delete()
            await message.channel.send(f"{message.author.mention}, your message contained a forbidden word.", delete_after=5)
            await log_action("Automod Filter", bot.user, message.author, f"Used forbidden word: {word}", message.guild.id)
            break

    await bot.process_commands(message)
"""
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(embed=create_embed(
            "⚠️ Error",
            f"Missing arguments! Correct usage: `{ctx.command} {ctx.command.signature}`.",
            discord.Color.red()
        ))
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send(embed=create_embed(
            "🔨 Error",
            "You don't have permission to use this command.",
            discord.Color.red()
        ))
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send(embed=create_embed(
            "⚠️ Error",
            "Unknown command. Use `.commands` for a list.",
            discord.Color.red()
        ))
    elif isinstance(error, commands.BadArgument):
        await ctx.send(embed=create_embed(
            "⚠️ Error",
            f"Invalid argument! Correct usage: `{ctx.command} {ctx.command.signature}`.",
            discord.Color.red()
        ))
    else:
        await ctx.send(embed=create_embed(
            "❌ Error",
            "An unexpected error occurred.",
            discord.Color.red()
        ))
        print(f"Unexpected error in command '{ctx.command}': {error}")
        raise error
"""
load_config()
bot.run(config["token"])
