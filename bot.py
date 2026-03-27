import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import os, secrets, string, sqlite3, threading
from datetime import datetime

BOT_TOKEN    = os.environ.get("BOT_TOKEN")
GUILD_ID     = int(os.environ.get("GUILD_ID", "1483801939673092198"))
ADMIN_ROLE   = os.environ.get("ADMIN_ROLE", "Admin")
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "changeme")

_data_dir = "/app/data" if os.path.isdir("/app/data") else os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_data_dir, "panel.db")

def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with get_db() as db:
        db.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, key_used TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS keys (id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT UNIQUE NOT NULL, used INTEGER DEFAULT 0)")
        db.commit()

init_db()

def gen_key():
    chars = string.ascii_uppercase + string.digits
    parts = [''.join(secrets.choice(chars) for _ in range(4)) for _ in range(4)]
    return '-'.join(parts)

app = Flask(__name__)

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    key      = (data.get("key") or "").strip().upper()
    if not username or not password or not key:
        return jsonify({"ok": False, "msg": "Campos obrigatorios."}), 400
    with get_db() as db:
        row = db.execute("SELECT used FROM keys WHERE key=?", (key,)).fetchone()
        if not row:
            return jsonify({"ok": False, "msg": "Key invalida."}), 403
        if row["used"]:
            return jsonify({"ok": False, "msg": "Key ja utilizada."}), 403
        if db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
            return jsonify({"ok": False, "msg": "Usuario ja existe."}), 409
        db.execute("INSERT INTO users (username,password,key_used) VALUES (?,?,?)", (username, generate_password_hash(password), key))
        db.execute("UPDATE keys SET used=1 WHERE key=?", (key,))
        db.commit()
    return jsonify({"ok": True, "msg": "Conta criada com sucesso."})

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    if not username or not password:
        return jsonify({"ok": False, "msg": "Campos obrigatorios."}), 400
    with get_db() as db:
        row = db.execute("SELECT password FROM users WHERE username=?", (username,)).fetchone()
        if not row or not check_password_hash(row["password"], password):
            return jsonify({"ok": False, "msg": "Usuario ou senha incorretos."}), 401
    return jsonify({"ok": True, "msg": "Login realizado."})

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

def is_admin(interaction: discord.Interaction) -> bool:
    return any(r.name == ADMIN_ROLE for r in interaction.user.roles)

@tree.command(name="gerar", description="Gera uma chave de acesso para o painel", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(usuario="Mencione o usuario que vai receber a chave")
async def gerar(interaction: discord.Interaction, usuario: discord.Member):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Sem permissao.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    key = gen_key()
    with get_db() as db:
        db.execute("INSERT OR IGNORE INTO keys (key) VALUES (?)", (key,))
        db.commit()
    embed = discord.Embed(title="✅ Chave Gerada", color=0x7C5CBF)
    embed.add_field(name="Chave", value=f"`{key}`", inline=False)
    embed.add_field(name="Usuario", value=usuario.mention, inline=True)
    embed.set_footer(text="S Panel Auth")
    try:
        dm_embed = discord.Embed(title="🔑 Sua chave S Panel", color=0x7C5CBF)
        dm_embed.add_field(name="Chave", value=f"`{key}`", inline=False)
        dm_embed.add_field(name="Como usar", value="Vai ao painel, clica em Registar e usa esta chave para criar a tua conta.", inline=False)
        dm_embed.set_footer(text="Nao partilhes a tua chave.")
        await usuario.send(embed=dm_embed)
        embed.add_field(name="DM", value="✅ Chave enviada por DM", inline=False)
    except:
        embed.add_field(name="DM", value="⚠️ Nao foi possivel enviar DM", inline=False)
    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Bot online: {bot.user} | Comandos sincronizados no servidor {GUILD_ID}")

threading.Thread(target=run_flask, daemon=True).start()
bot.run(BOT_TOKEN)
