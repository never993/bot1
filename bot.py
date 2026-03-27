import discord
from discord import app_commands
from discord.ext import commands
import os
from db import create_license, revoke_license, get_license, validate_license
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN  = os.environ.get("BOT_TOKEN", "SEU_TOKEN_AQUI")
GUILD_ID   = int(os.environ.get("GUILD_ID", "1483801939673092198"))
ADMIN_ROLE = os.environ.get("ADMIN_ROLE", "Admin")  # nome do cargo que pode gerar chaves

# ── Bot setup ─────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

def is_admin(interaction: discord.Interaction) -> bool:
    return any(r.name == ADMIN_ROLE for r in interaction.user.roles)

# ── /gerar ────────────────────────────────────────────────────────────────────
@tree.command(name="gerar", description="Gera uma chave de licenca", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    usuario="Mencione o usuario que vai receber a chave",
    dias="Numero de dias (0 = permanente)"
)
async def gerar(interaction: discord.Interaction, usuario: discord.Member, dias: int = 30):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Sem permissao.", ephemeral=True)
        return

    days = None if dias == 0 else dias
    key  = create_license(str(usuario.id), str(usuario), days)

    tipo = "**Permanente**" if days is None else f"**{dias} dias**"
    embed = discord.Embed(title="✅ Chave Gerada", color=0x7C5CBF)
    embed.add_field(name="Chave",    value=f"`{key}`",        inline=False)
    embed.add_field(name="Usuario",  value=usuario.mention,   inline=True)
    embed.add_field(name="Duracao",  value=tipo,              inline=True)
    embed.set_footer(text="S Panel Auth")

    # Envia a chave em DM para o usuario
    try:
        dm_embed = discord.Embed(title="🔑 Sua chave S Panel", color=0x7C5CBF)
        dm_embed.add_field(name="Chave",   value=f"`{key}`", inline=False)
        dm_embed.add_field(name="Duracao", value=tipo,       inline=True)
        dm_embed.set_footer(text="Nao compartilhe sua chave.")
        await usuario.send(embed=dm_embed)
        embed.add_field(name="DM", value="✅ Chave enviada por DM", inline=False)
    except:
        embed.add_field(name="DM", value="⚠️ Nao foi possivel enviar DM", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

# ── /revogar ──────────────────────────────────────────────────────────────────
@tree.command(name="revogar", description="Revoga uma chave de licenca", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(chave="A chave a ser revogada")
async def revogar(interaction: discord.Interaction, chave: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Sem permissao.", ephemeral=True)
        return

    ok = revoke_license(chave.strip().upper())
    if ok:
        await interaction.response.send_message(f"✅ Chave `{chave}` revogada.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Chave nao encontrada.", ephemeral=True)

# ── /info ─────────────────────────────────────────────────────────────────────
@tree.command(name="info", description="Mostra informacoes de uma chave", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(chave="A chave para consultar")
async def info(interaction: discord.Interaction, chave: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Sem permissao.", ephemeral=True)
        return

    row = get_license(chave.strip().upper())
    if not row:
        await interaction.response.send_message("❌ Chave nao encontrada.", ephemeral=True)
        return

    status = "✅ Ativa" if row["active"] else "❌ Revogada"
    if row["active"] and row["expires_at"]:
        exp = datetime.fromisoformat(row["expires_at"])
        if datetime.utcnow() > exp:
            status = "⏰ Expirada"

    embed = discord.Embed(title="🔍 Info da Chave", color=0x7C5CBF)
    embed.add_field(name="Chave",    value=f"`{row['key']}`",                          inline=False)
    embed.add_field(name="Usuario",  value=f"{row['username']} (`{row['user_id']}`)",  inline=False)
    embed.add_field(name="Status",   value=status,                                     inline=True)
    embed.add_field(name="Criada",   value=row["created_at"][:10],                     inline=True)
    embed.add_field(name="Expira",   value=row["expires_at"][:10] if row["expires_at"] else "Nunca", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ── /minhaschave ──────────────────────────────────────────────────────────────
@tree.command(name="minhaschave", description="Mostra sua chave ativa", guild=discord.Object(id=GUILD_ID))
async def minhaschave(interaction: discord.Interaction):
    from db import get_conn
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM licenses WHERE user_id=? AND active=1 ORDER BY created_at DESC",
            (str(interaction.user.id),)
        ).fetchall()

    if not rows:
        await interaction.response.send_message("❌ Voce nao tem chave ativa.", ephemeral=True)
        return

    embed = discord.Embed(title="🔑 Suas Chaves", color=0x7C5CBF)
    for row in rows:
        exp = row["expires_at"][:10] if row["expires_at"] else "Permanente"
        embed.add_field(name=f"`{row['key']}`", value=f"Expira: {exp}", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ── Startup ───────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Bot online: {bot.user} | Comandos sincronizados no servidor {GUILD_ID}")

bot.run(BOT_TOKEN)
