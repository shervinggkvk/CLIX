import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from datetime import datetime, time
import pytz
import os
import re

# ================= CONFIG =================
TOKEN = os.getenv("TOKEN")  # از Environment Variable گرفته میشه

ROB_CHANNEL_ID = 1450316803103391765
PUNISH_CHANNEL_ID = 1322499770081873972
PAY_CHANNEL_ID = 1450473268091027486
PAY_CONFIRM_ROLE = 1325224075769155694

SOURCE_HEALTH_CHANNEL_ID = 163667378383
DEST_HEALTH_CHANNEL_ID = 1353144294839419031
# =========================================

iran_tz = pytz.timezone("Asia/Tehran")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================= DATABASE =================
conn = sqlite3.connect("rob.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS rob_reports (
    user_id INTEGER,
    status TEXT,
    timestamp TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS car_punish_payments (
    user_id INTEGER,
    amount INTEGER,
    timestamp TEXT
)
""")

conn.commit()

# ================= HEALTH / ENGINE MONITOR =================

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.channel.id == SOURCE_HEALTH_CHANNEL_ID:
        content = message.content

        # Health
        health_match = re.search(r'health\s*[:\-]?\s*(\d{1,3})\s*%', content, re.IGNORECASE)
        health = int(health_match.group(1)) if health_match else None

        # Engine
        engine_match = re.search(r'engine\s*[:\-]?\s*(true|false)', content, re.IGNORECASE)
        engine = engine_match.group(1).lower() if engine_match else None

        send_health = health is not None and health < 85
        send_engine = engine == "false"

        if send_health or send_engine:
            # Player Name
            name_match = re.search(r'steam:\S+\s+([A-Za-z0-9_]+)\s+id:', content)
            player_name = name_match.group(1) if name_match else "Unknown"

            # Penalties
            fines = []
            if send_engine:
                fines.append("250k engin lose")
            if send_health:
                fines.append("35k")

            dest = message.guild.get_channel(DEST_HEALTH_CHANNEL_ID)
            if dest:
                await dest.send(
                    f"👤 Player: **{player_name}**\n"
                    f"❤️ Health: **{health if health is not None else 'N/A'}%**\n"
                    f"🔧 Engine: **{engine if engine is not None else 'N/A'}**\n\n"
                    f"**shomare kart jahat pardakht jarime 336892 ({' | '.join(fines)})**"
                )

    await bot.process_commands(message)

# ================= ROB SYSTEM =================

class RobTypeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Maze bank"),
            discord.SelectOption(label="Flat javahery"),
            discord.SelectOption(label="Airport"),
            discord.SelectOption(label="City javahery"),
            discord.SelectOption(label="Shams javahery"),
            discord.SelectOption(label="Central bank"),
            discord.SelectOption(label="Cargo"),
            discord.SelectOption(label="Benny"),
            discord.SelectOption(label="Shop"),
            discord.SelectOption(label="MiniJavahery"),
            discord.SelectOption(label="Bime"),
            discord.SelectOption(label="GunShop"),
            discord.SelectOption(label="MiniBank"),
        ]
        super().__init__(placeholder="راب رو انتخاب کن", options=options)

    async def callback(self, interaction: discord.Interaction):
        self.view.rob_type = self.values[0]
        await interaction.response.edit_message(
            content="وضعیت راب رو انتخاب کن:",
            view=StatusView(self.view.rob_type)
        )


class StatusSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Win", emoji="🟢"),
            discord.SelectOption(label="Lose", emoji="🔴"),
            discord.SelectOption(label="No PD", emoji="🟠"),
        ]
        super().__init__(placeholder="وضعیت راب", options=options)

    async def callback(self, interaction: discord.Interaction):
        self.view.status = self.values[0]
        await interaction.response.edit_message(
            content="تعداد پلیرها رو انتخاب کن:",
            view=PlayerCountView(self.view.rob_type, self.view.status)
        )


class PlayerCountSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=str(i)) for i in range(1, 11)]
        super().__init__(placeholder="تعداد پلیرها", options=options)

    async def callback(self, interaction: discord.Interaction):
        count = int(self.values[0])
        await interaction.response.edit_message(
            content="پلیرها رو انتخاب کن:",
            view=PlayerSelectView(self.view.rob_type, self.view.status, count)
        )


class PlayerSelect(discord.ui.UserSelect):
    def __init__(self, count):
        super().__init__(
            placeholder="پلیرها رو انتخاب کن",
            min_values=count,
            max_values=count
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.players = self.values
        await interaction.response.edit_message(
            content="برای ارسال گزارش دکمه رو بزن",
            view=self.view
        )


class RobTypeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.rob_type = None
        self.add_item(RobTypeSelect())


class StatusView(discord.ui.View):
    def __init__(self, rob_type):
        super().__init__(timeout=120)
        self.rob_type = rob_type
        self.status = None
        self.add_item(StatusSelect())


class PlayerCountView(discord.ui.View):
    def __init__(self, rob_type, status):
        super().__init__(timeout=120)
        self.rob_type = rob_type
        self.status = status
        self.add_item(PlayerCountSelect())


class PlayerSelectView(discord.ui.View):
    def __init__(self, rob_type, status, count):
        super().__init__(timeout=120)
        self.rob_type = rob_type
        self.status = status
        self.players = []
        self.add_item(PlayerSelect(count))

    @discord.ui.button(label="ارسال به rob-status", style=discord.ButtonStyle.success)
    async def send_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.guild.get_channel(ROB_CHANNEL_ID)
        if not channel:
            return await interaction.response.send_message("❌ چنل پیدا نشد", ephemeral=True)

        now_iran = datetime.now(iran_tz).isoformat()
        for player in self.players:
            cursor.execute(
                "INSERT INTO rob_reports VALUES (?, ?, ?)",
                (player.id, self.status, now_iran)
            )
        conn.commit()

        await interaction.response.send_message("✅ گزارش ثبت شد", ephemeral=True)

# ================= CAR PUNISH =================

class CarPunishModal(discord.ui.Modal, title="پرداخت Car Punishment"):
    amount = discord.ui.TextInput(label="تعداد پرداخت", required=True)

    def __init__(self, member, max_punish):
        super().__init__()
        self.member = member
        self.max_punish = max_punish

    async def on_submit(self, interaction: discord.Interaction):
        if PAY_CONFIRM_ROLE not in [r.id for r in interaction.user.roles]:
            return await interaction.response.send_message("❌ دسترسی نداری", ephemeral=True)

        amount = int(self.amount.value)
        if amount < 1 or amount > self.max_punish:
            return await interaction.response.send_message("❌ عدد نامعتبر", ephemeral=True)

        cursor.execute(
            "INSERT INTO car_punish_payments VALUES (?, ?, ?)",
            (self.member.id, amount, datetime.now(iran_tz).isoformat())
        )
        conn.commit()

        await interaction.response.send_message("✅ پرداخت ثبت شد", ephemeral=True)


class CarPunishPayView(discord.ui.View):
    def __init__(self, member, max_punish):
        super().__init__(timeout=300)
        self.member = member
        self.max_punish = max_punish

    @discord.ui.button(label="💰 ثبت پرداخت", style=discord.ButtonStyle.success)
    async def pay(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(
            CarPunishModal(self.member, self.max_punish)
        )

# ================= SLASH COMMANDS =================

@bot.tree.command(name="rob", description="ثبت نتیجه راب")
async def rob(interaction: discord.Interaction):
    await interaction.response.send_message(
        "راب کدوم بوده؟",
        view=RobTypeView(),
        ephemeral=True
    )


@bot.tree.command(name="checkrankup", description="چک آمار راب و Car Punishment")
@app_commands.choices(
    period=[
        app_commands.Choice(name="1day", value="1day"),
        app_commands.Choice(name="1month", value="1month"),
    ]
)
async def checkrankup(interaction: discord.Interaction, member: discord.Member, period: app_commands.Choice[str]):
    await interaction.response.defer(ephemeral=True)

    now = datetime.now(iran_tz)
    start_time = (
        iran_tz.localize(datetime.combine(now.date(), time.min))
        if period.value == "1day"
        else iran_tz.localize(datetime(now.year, now.month, 1))
    )

    cursor.execute("""
        SELECT status, COUNT(*)
        FROM rob_reports
        WHERE user_id = ? AND timestamp >= ?
        GROUP BY status
    """, (member.id, start_time.isoformat()))

    stats = dict(cursor.fetchall())

    total_rob = stats.get("Win", 0) + stats.get("Lose", 0) + stats.get("No PD", 0)

    punish = 0
    punish_channel = interaction.guild.get_channel(PUNISH_CHANNEL_ID)
    if punish_channel:
        async for msg in punish_channel.history(after=start_time, limit=None):
            if member in msg.mentions:
                punish += 1

    cursor.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM car_punish_payments WHERE user_id = ?",
        (member.id,)
    )
    paid = cursor.fetchone()[0]

    punish = max(punish - paid, 0)
    car_money = punish * 30

    embed = discord.Embed(
        title="📊 CHECK RANK UP",
        description=f"👤 Player: {member.mention}",
        color=discord.Color.blurple()
    )

    embed.add_field(name="🟢 Win", value=stats.get("Win", 0))
    embed.add_field(name="🔴 Lose", value=stats.get("Lose", 0))
    embed.add_field(name="🟠 No PD", value=stats.get("No PD", 0))
    embed.add_field(name="📦 Total Rob", value=total_rob)
    embed.add_field(name="🚗 Car Punishment", value=f"{punish} = {car_money}k")

    await interaction.followup.send(embed=embed, ephemeral=True)

    if punish > 0:
        pay_channel = interaction.guild.get_channel(PAY_CHANNEL_ID)
        if pay_channel:
            await pay_channel.send(
                f"{member.mention} دارای **{punish}** Car Punishment است",
                view=CarPunishPayView(member, punish)
            )

# ================= READY =================

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"🔥 Bot Online as {bot.user}")

bot.run(TOKEN)
