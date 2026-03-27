import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Select
from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import os, secrets, string, sqlite3, threading
from datetime import datetime, timedelta

BOT_TOKEN    = os.environ.get("BOT_TOKEN")
GUILD_ID     = int(os.environ.get("GUILD_ID", "1483801939673092198"))
ADMIN_ROLE   = os.environ.get("ADMIN_ROLE", "Admin")
PIX_KEY      = "1de2b00a-2c3c-44c2-b288-de2b80300621"
DOWNLOAD_URL = "https://github.com/never993/bot1/releases/download/v1.0/SearchHost.exe"

# Produtos da loja
PRODUCTS = {
    "1_semana":  {"name": "1 Semana",  "price": "R$ 15,00", "days": 7,  "emoji": "📅"},
    "1_mes":     {"name": "1 Mês",     "price": "R$ 40,00", "days": 30, "emoji": "📆"},
    "lifetime":  {"name": "Lifetime",  "price": "R$ 80,00", "days": 0,  "emoji": "♾️"},
}

_data_dir = "/app/data" if os.path.isdir("/app/data") else os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_data_dir, "panel.db")

def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with get_db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
            key_used TEXT NOT NULL, hwid TEXT, expires_at TEXT)""")
        db.execute("""CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL, used INTEGER DEFAULT 0, expires_at TEXT)""")
        db.execute("""CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT UNIQUE NOT NULL, user_id TEXT NOT NULL,
            product TEXT NOT NULL, status TEXT DEFAULT 'open',
            created_at TEXT NOT NULL)""")
        for col in [("users","hwid","TEXT"),("users","expires_at","TEXT"),("keys","expires_at","TEXT")]:
            try: db.execute(f"ALTER TABLE {col[0]} ADD COLUMN {col[1]} {col[2]}"); db.commit()
            except: pass
        db.commit()

init_db()

def gen_key():
    chars = string.ascii_uppercase + string.digits
    return '-'.join(''.join(secrets.choice(chars) for _ in range(4)) for _ in range(4))

def days_remaining(expires_at):
    if not expires_at: return None
    delta = datetime.fromisoformat(expires_at) - datetime.utcnow()
    return max(0, delta.days)

# ── Flask ─────────────────────────────────────────────────────────────────────
app = Flask(__name__)

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    key      = (data.get("key") or "").strip().upper()
    hwid     = (data.get("hwid") or "").strip()
    if not username or not password or not key:
        return jsonify({"ok": False, "msg": "Campos obrigatorios."}), 400
    with get_db() as db:
        row = db.execute("SELECT used, expires_at FROM keys WHERE key=?", (key,)).fetchone()
        if not row: return jsonify({"ok": False, "msg": "Key invalida."}), 403
        if row["used"]: return jsonify({"ok": False, "msg": "Key ja utilizada."}), 403
        if row["expires_at"] and datetime.utcnow() > datetime.fromisoformat(row["expires_at"]):
            return jsonify({"ok": False, "msg": "Key expirada."}), 403
        if db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
            return jsonify({"ok": False, "msg": "Usuario ja existe."}), 409
        db.execute("INSERT INTO users (username,password,key_used,hwid,expires_at) VALUES (?,?,?,?,?)",
                   (username, generate_password_hash(password), key, hwid or None, row["expires_at"]))
        db.execute("UPDATE keys SET used=1 WHERE key=?", (key,))
        db.commit()
    return jsonify({"ok": True, "msg": "Conta criada com sucesso."})

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    hwid     = (data.get("hwid") or "").strip()
    if not username or not password:
        return jsonify({"ok": False, "msg": "Campos obrigatorios."}), 400
    with get_db() as db:
        row = db.execute("SELECT password, hwid, expires_at FROM users WHERE username=?", (username,)).fetchone()
        if not row or not check_password_hash(row["password"], password):
            return jsonify({"ok": False, "msg": "Usuario ou senha incorretos."}), 401
        if row["expires_at"] and datetime.utcnow() > datetime.fromisoformat(row["expires_at"]):
            return jsonify({"ok": False, "msg": "Licenca expirada."}), 403
        if row["hwid"] and hwid and row["hwid"] != hwid:
            return jsonify({"ok": False, "msg": "Dispositivo nao autorizado."}), 403
        if not row["hwid"] and hwid:
            db.execute("UPDATE users SET hwid=? WHERE username=?", (hwid, username))
            db.commit()
        dias = days_remaining(row["expires_at"])
    return jsonify({"ok": True, "msg": "Login realizado.", "expires": row["expires_at"], "days": dias})

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ── Discord Bot ───────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

def is_admin(interaction: discord.Interaction) -> bool:
    return any(r.name == ADMIN_ROLE for r in interaction.user.roles)

# ── Loja ──────────────────────────────────────────────────────────────────────
class LojaView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📅 1 Semana — R$ 15,00",  style=discord.ButtonStyle.secondary, custom_id="buy_1_semana")
    async def buy_semana(self, interaction: discord.Interaction, button: Button):
        await abrir_ticket(interaction, "1_semana")

    @discord.ui.button(label="📆 1 Mês — R$ 40,00",     style=discord.ButtonStyle.secondary, custom_id="buy_1_mes")
    async def buy_mes(self, interaction: discord.Interaction, button: Button):
        await abrir_ticket(interaction, "1_mes")

    @discord.ui.button(label="♾️ Lifetime — R$ 80,00",  style=discord.ButtonStyle.primary,   custom_id="buy_lifetime")
    async def buy_lifetime(self, interaction: discord.Interaction, button: Button):
        await abrir_ticket(interaction, "lifetime")

async def abrir_ticket(interaction: discord.Interaction, product_id: str):
    guild   = interaction.guild
    product = PRODUCTS[product_id]

    # Verifica se já tem ticket aberto
    with get_db() as db:
        existing = db.execute(
            "SELECT channel_id FROM tickets WHERE user_id=? AND status='open'",
            (str(interaction.user.id),)
        ).fetchone()
    if existing:
        ch = guild.get_channel(int(existing["channel_id"]))
        if ch:
            await interaction.response.send_message(f"❌ Já tens um ticket aberto: {ch.mention}", ephemeral=True)
            return

    # Cria canal privado
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user:   discord.PermissionOverwrite(read_messages=True, send_messages=True),
    }
    for role in guild.roles:
        if role.name == ADMIN_ROLE:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    channel = await guild.create_text_channel(
        f"ticket-{interaction.user.name}",
        overwrites=overwrites,
        topic=f"Ticket de {interaction.user} | {product['name']}"
    )

    with get_db() as db:
        db.execute("INSERT INTO tickets (channel_id, user_id, product, created_at) VALUES (?,?,?,?)",
                   (str(channel.id), str(interaction.user.id), product_id, datetime.utcnow().isoformat()))
        db.commit()

    embed = discord.Embed(title="🛒 Novo Pedido", color=0x7C5CBF)
    embed.add_field(name="Produto",  value=f"{product['emoji']} {product['name']}", inline=True)
    embed.add_field(name="Valor",    value=product["price"],                        inline=True)
    embed.add_field(name="Pagamento", value=(
        f"**Pix:** `{PIX_KEY}`\n"
        f"Após pagar, aguarda a confirmação do admin.\n"
        f"Envia o comprovativo aqui."
    ), inline=False)
    embed.set_footer(text="S Panel • Após confirmação recebes a key por DM")

    await channel.send(f"{interaction.user.mention}", embed=embed, view=TicketAdminView(interaction.user.id, product_id))
    await interaction.response.send_message(f"✅ Ticket criado: {channel.mention}", ephemeral=True)

class TicketAdminView(View):
    def __init__(self, user_id: int, product_id: str):
        super().__init__(timeout=None)
        self.user_id    = user_id
        self.product_id = product_id

    @discord.ui.button(label="✅ Confirmar Pagamento", style=discord.ButtonStyle.success, custom_id="confirm_pay")
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction):
            await interaction.response.send_message("❌ Sem permissao.", ephemeral=True)
            return

        product = PRODUCTS[self.product_id]
        dias    = product["days"]
        expires_at = None if dias == 0 else (datetime.utcnow() + timedelta(days=dias)).isoformat()

        key = gen_key()
        with get_db() as db:
            db.execute("INSERT OR IGNORE INTO keys (key, expires_at) VALUES (?,?)", (key, expires_at))
            db.execute("UPDATE tickets SET status='closed' WHERE channel_id=?", (str(interaction.channel.id),))
            db.commit()

        tipo = "Lifetime" if dias == 0 else product["name"]
        user = interaction.guild.get_member(self.user_id)

        if user:
            dm_embed = discord.Embed(title="🔑 Pagamento Confirmado — S Panel", color=0x7C5CBF)
            dm_embed.add_field(name="Produto",  value=f"{product['emoji']} {tipo}", inline=True)
            dm_embed.add_field(name="Key",      value=f"`{key}`",                   inline=False)
            dm_embed.add_field(name="Download", value=f"[Clica aqui para descarregar o S Panel]({DOWNLOAD_URL})", inline=False)
            dm_embed.add_field(name="Como usar", value="Abre o programa, clica em **Registar**, usa a key acima para criar a tua conta.", inline=False)
            dm_embed.set_footer(text="Nao partilhes a tua key.")
            try:
                await user.send(embed=dm_embed)
            except:
                pass

        await interaction.response.send_message(f"✅ Pagamento confirmado! Key enviada por DM para {user.mention if user else self.user_id}.")
        await interaction.channel.send("Este ticket será fechado em 10 segundos...")
        import asyncio
        await asyncio.sleep(10)
        await interaction.channel.delete()

    @discord.ui.button(label="❌ Fechar Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction):
            await interaction.response.send_message("❌ Sem permissao.", ephemeral=True)
            return
        with get_db() as db:
            db.execute("UPDATE tickets SET status='closed' WHERE channel_id=?", (str(interaction.channel.id),))
            db.commit()
        await interaction.response.send_message("Ticket fechado. Canal será apagado em 5 segundos...")
        import asyncio
        await asyncio.sleep(5)
        await interaction.channel.delete()

# ── Comandos ──────────────────────────────────────────────────────────────────
duracao_choices = [
    app_commands.Choice(name="1 Semana",  value="7"),
    app_commands.Choice(name="1 Mes",     value="30"),
    app_commands.Choice(name="Lifetime",  value="0"),
]

@tree.command(name="loja", description="Mostra o painel da loja", guild=discord.Object(id=GUILD_ID))
async def loja(interaction: discord.Interaction):
    embed = discord.Embed(title="🛒 S Panel — Loja", color=0x7C5CBF,
        description="Escolhe um plano abaixo para abrir um ticket de compra.")
    for pid, p in PRODUCTS.items():
        embed.add_field(name=f"{p['emoji']} {p['name']}", value=p["price"], inline=True)
    embed.set_footer(text="Pagamento via Pix • Key entregue após confirmação")
    await interaction.response.send_message(embed=embed, view=LojaView())

@tree.command(name="gerar", description="Gera uma chave de acesso para o painel", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(usuario="Mencione o usuario", duracao="Duracao da chave")
@app_commands.choices(duracao=duracao_choices)
async def gerar(interaction: discord.Interaction, usuario: discord.Member, duracao: app_commands.Choice[str]):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Sem permissao.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    dias = int(duracao.value)
    expires_at = None if dias == 0 else (datetime.utcnow() + timedelta(days=dias)).isoformat()
    tipo = "Lifetime" if dias == 0 else duracao.name
    key  = gen_key()
    with get_db() as db:
        db.execute("INSERT OR IGNORE INTO keys (key, expires_at) VALUES (?,?)", (key, expires_at))
        db.commit()
    embed = discord.Embed(title="✅ Chave Gerada", color=0x7C5CBF)
    embed.add_field(name="Chave",   value=f"`{key}`",      inline=False)
    embed.add_field(name="Usuario", value=usuario.mention, inline=True)
    embed.add_field(name="Duracao", value=tipo,            inline=True)
    try:
        dm = discord.Embed(title="🔑 Sua chave S Panel", color=0x7C5CBF)
        dm.add_field(name="Chave",    value=f"`{key}`",  inline=False)
        dm.add_field(name="Duracao",  value=tipo,        inline=True)
        dm.add_field(name="Download", value=f"[Descarregar S Panel]({DOWNLOAD_URL})", inline=False)
        dm.set_footer(text="Nao partilhes a tua chave.")
        await usuario.send(embed=dm)
        embed.add_field(name="DM", value="✅ Enviado por DM", inline=False)
    except:
        embed.add_field(name="DM", value="⚠️ Nao foi possivel enviar DM", inline=False)
    await interaction.followup.send(embed=embed, ephemeral=True)

@tree.command(name="revogar", description="Revoga a licenca de um utilizador", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(username="Username do utilizador")
async def revogar(interaction: discord.Interaction, username: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Sem permissao.", ephemeral=True)
        return
    with get_db() as db:
        if not db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
            await interaction.response.send_message(f"❌ `{username}` nao encontrado.", ephemeral=True)
            return
        db.execute("DELETE FROM users WHERE username=?", (username,))
        db.commit()
    await interaction.response.send_message(f"✅ Licenca de `{username}` revogada.", ephemeral=True)

@tree.command(name="info", description="Info de um utilizador", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(username="Username do utilizador")
async def info(interaction: discord.Interaction, username: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Sem permissao.", ephemeral=True)
        return
    with get_db() as db:
        row = db.execute("SELECT username, hwid, expires_at FROM users WHERE username=?", (username,)).fetchone()
    if not row:
        await interaction.response.send_message(f"❌ `{username}` nao encontrado.", ephemeral=True)
        return
    dias = days_remaining(row["expires_at"])
    embed = discord.Embed(title=f"👤 {row['username']}", color=0x7C5CBF)
    embed.add_field(name="Expira", value=row["expires_at"][:10] if row["expires_at"] else "Lifetime", inline=True)
    embed.add_field(name="Dias",   value=str(dias) if dias is not None else "∞", inline=True)
    embed.add_field(name="HWID",   value=f"`{row['hwid'][:16]}...`" if row["hwid"] else "Nao registado", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_ready():
    bot.add_view(LojaView())
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Bot online: {bot.user}")

threading.Thread(target=run_flask, daemon=True).start()
bot.run(BOT_TOKEN)
