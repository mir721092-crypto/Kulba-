# -*- coding: utf-8 -*-
"""
Кулба Кассир — Telegram бот барои ҳисобу китоби мағоза
Фурӯш, мол (анбор), қарзу дайн, хароҷот, ҳисобот
"""

import os
import sqlite3
import logging
from datetime import datetime, date

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, filters
)

# ---------- ТАНЗИМОТ ----------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8934353778:AAGdADr4qNHBaZMTRtDAi5YfpwRVZIlkd08")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8417990452"))  # Танҳо шумо метавонед истифода баред
DB_PATH = os.environ.get("DB_PATH", "kulba.db")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ---------- ПОЙГОҲИ МАЪЛУМОТ ----------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS mol (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL,
        miqdor REAL NOT NULL DEFAULT 0,
        vohid TEXT DEFAULT 'дона',
        narx_kharid REAL DEFAULT 0,
        narx_furush REAL DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS furush (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mol_id INTEGER,
        mol_nom TEXT,
        miqdor REAL,
        narx REAL,
        summa REAL,
        sana TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS qarz (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mizoj TEXT NOT NULL,
        summa REAL NOT NULL,
        tavsif TEXT,
        sana TEXT,
        pardokht_shud INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS kharoj (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tavsif TEXT NOT NULL,
        summa REAL NOT NULL,
        sana TEXT
    )""")
    conn.commit()
    conn.close()

def only_admin(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *a, **kw):
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("Бубахшед, ин бот шахсист.")
            return ConversationHandler.END
        return await func(update, context, *a, **kw)
    return wrapper

def fmt(n):
    try:
        n = float(n)
        if n == int(n):
            return f"{int(n):,}".replace(",", " ")
        return f"{n:,.2f}".replace(",", " ")
    except Exception:
        return str(n)

def today():
    return date.today().strftime("%Y-%m-%d")

# ---------- CONVERSATION STATES ----------
(
    F_MOL, F_MIQDOR,           # фурӯш
    M_NOM, M_MIQDOR, M_NARX_K, M_NARX_F,   # мол нав
    Q_MIZOJ, Q_SUMMA, Q_TAVSIF,            # қарз
    KH_TAVSIF, KH_SUMMA                    # хароҷот
) = range(11)

MAIN_MENU = [
    ["🛒 Фурӯш", "📦 Мол"],
    ["💰 Қарз", "💸 Хароҷот"],
    ["📊 Ҳисобот"],
]

def main_kb():
    return ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)

# ---------- /start ----------
@only_admin
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Ассалому алейкум! Ин боти ҳисобу китоби Кулба аст.\n\n"
        "Аз тугмаҳои поён истифода баред 👇",
        reply_markup=main_kb()
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Бекор шуд.", reply_markup=main_kb())
    return ConversationHandler.END

# ---------- МОЛИ НАВ ----------
@only_admin
async def mol_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db()
    rows = conn.execute("SELECT * FROM mol ORDER BY nom").fetchall()
    conn.close()
    if rows:
        txt = "📦 *Мавҷудияти анбор:*\n\n"
        for r in rows:
            txt += f"• {r['nom']} — {fmt(r['miqdor'])} {r['vohid']} (нархи фурӯш: {fmt(r['narx_furush'])} с.)\n"
    else:
        txt = "Анбор холист.\n"
    txt += "\nБарои иловаи моли нав, номи молро нависед (ё /bekor барои бекор кардан):"
    await update.message.reply_text(txt, parse_mode="Markdown")
    return M_NOM

async def mol_nom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["m_nom"] = update.message.text.strip()
    await update.message.reply_text("Миқдори он чанд аст? (мисол: 50)")
    return M_MIQDOR

async def mol_miqdor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["m_miqdor"] = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Лутфан рақам нависед. Масалан: 50")
        return M_MIQDOR
    await update.message.reply_text("Нархи харид (барои як дона) чанд сомонӣ?")
    return M_NARX_K

async def mol_narx_k(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["m_narx_k"] = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Лутфан рақам нависед.")
        return M_NARX_K
    await update.message.reply_text("Нархи фурӯш (барои як дона) чанд сомонӣ?")
    return M_NARX_F

async def mol_narx_f(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        narx_f = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Лутфан рақам нависед.")
        return M_NARX_F
    ud = context.user_data
    conn = db()
    conn.execute(
        "INSERT INTO mol (nom, miqdor, narx_kharid, narx_furush) VALUES (?,?,?,?)",
        (ud["m_nom"], ud["m_miqdor"], ud["m_narx_k"], narx_f)
    )
    conn.commit()
    conn.close()
    await update.message.reply_text(
        f"✅ Илова шуд: {ud['m_nom']} — {fmt(ud['m_miqdor'])} дона",
        reply_markup=main_kb()
    )
    context.user_data.clear()
    return ConversationHandler.END

# ---------- ФУРӮШ ----------
@only_admin
async def furush_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db()
    rows = conn.execute("SELECT * FROM mol WHERE miqdor > 0 ORDER BY nom").fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("Анбор холист. Аввал моле илова кунед (📦 Мол).", reply_markup=main_kb())
        return ConversationHandler.END
    kb = [[InlineKeyboardButton(f"{r['nom']} ({fmt(r['miqdor'])} {r['vohid']})", callback_data=f"sell_{r['id']}")] for r in rows]
    await update.message.reply_text("Кадом молро фурӯхтед?", reply_markup=InlineKeyboardMarkup(kb))
    return F_MOL

async def furush_mol_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    mol_id = int(query.data.split("_")[1])
    conn = db()
    r = conn.execute("SELECT * FROM mol WHERE id=?", (mol_id,)).fetchone()
    conn.close()
    context.user_data["s_mol_id"] = mol_id
    context.user_data["s_mol_nom"] = r["nom"]
    context.user_data["s_narx"] = r["narx_furush"]
    context.user_data["s_max"] = r["miqdor"]
    await query.edit_message_text(
        f"{r['nom']} — нархи фурӯш: {fmt(r['narx_furush'])} с./{r['vohid']}\n"
        f"Мавҷуд: {fmt(r['miqdor'])} {r['vohid']}\n\n"
        f"Миқдори фурӯхта шударо нависед:"
    )
    return F_MIQDOR

async def furush_miqdor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        miqdor = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Лутфан рақам нависед.")
        return F_MIQDOR
    ud = context.user_data
    if miqdor > ud["s_max"]:
        await update.message.reply_text(f"Мавҷуд танҳо {fmt(ud['s_max'])} дона аст. Аз нав нависед:")
        return F_MIQDOR
    summa = miqdor * ud["s_narx"]
    conn = db()
    conn.execute(
        "INSERT INTO furush (mol_id, mol_nom, miqdor, narx, summa, sana) VALUES (?,?,?,?,?,?)",
        (ud["s_mol_id"], ud["s_mol_nom"], miqdor, ud["s_narx"], summa, today())
    )
    conn.execute("UPDATE mol SET miqdor = miqdor - ? WHERE id=?", (miqdor, ud["s_mol_id"]))
    conn.commit()
    conn.close()
    await update.message.reply_text(
        f"✅ Фурӯш сабт шуд:\n{ud['s_mol_nom']} — {fmt(miqdor)} дона\nСумма: {fmt(summa)} сомонӣ",
        reply_markup=main_kb()
    )
    context.user_data.clear()
    return ConversationHandler.END

# ---------- ҚАРЗ ----------
@only_admin
async def qarz_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Номи мизоҷ (қарздор)?")
    return Q_MIZOJ

async def qarz_mizoj(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["q_mizoj"] = update.message.text.strip()
    await update.message.reply_text("Маблағи қарз чанд сомонӣ?")
    return Q_SUMMA

async def qarz_summa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["q_summa"] = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Лутфан рақам нависед.")
        return Q_SUMMA
    await update.message.reply_text("Тавсиф (барои чӣ)? Агар лозим набошад '-' нависед.")
    return Q_TAVSIF

async def qarz_tavsif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    tavsif = update.message.text.strip()
    conn = db()
    conn.execute(
        "INSERT INTO qarz (mizoj, summa, tavsif, sana) VALUES (?,?,?,?)",
        (ud["q_mizoj"], ud["q_summa"], tavsif, today())
    )
    conn.commit()
    conn.close()
    await update.message.reply_text(
        f"✅ Қарз сабт шуд:\n{ud['q_mizoj']} — {fmt(ud['q_summa'])} сомонӣ",
        reply_markup=main_kb()
    )
    context.user_data.clear()
    return ConversationHandler.END

# ---------- ХАРОҶОТ ----------
@only_admin
async def kharoj_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Хароҷот барои чӣ буд?")
    return KH_TAVSIF

async def kharoj_tavsif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["kh_tavsif"] = update.message.text.strip()
    await update.message.reply_text("Маблағаш чанд сомонӣ?")
    return KH_SUMMA

async def kharoj_summa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        summa = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Лутфан рақам нависед.")
        return KH_SUMMA
    ud = context.user_data
    conn = db()
    conn.execute(
        "INSERT INTO kharoj (tavsif, summa, sana) VALUES (?,?,?)",
        (ud["kh_tavsif"], summa, today())
    )
    conn.commit()
    conn.close()
    await update.message.reply_text(
        f"✅ Хароҷот сабт шуд:\n{ud['kh_tavsif']} — {fmt(summa)} сомонӣ",
        reply_markup=main_kb()
    )
    context.user_data.clear()
    return ConversationHandler.END

# ---------- ҲИСОБОТ ----------
@only_admin
async def hisobot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db()
    t = today()
    furush_row = conn.execute("SELECT COALESCE(SUM(summa),0) s, COUNT(*) c FROM furush WHERE sana=?", (t,)).fetchone()
    kharoj_row = conn.execute("SELECT COALESCE(SUM(summa),0) s FROM kharoj WHERE sana=?", (t,)).fetchone()
    qarz_row = conn.execute("SELECT COALESCE(SUM(summa),0) s FROM qarz WHERE pardokht_shud=0").fetchone()
    mol_count = conn.execute("SELECT COUNT(*) c FROM mol").fetchone()
    conn.close()

    txt = f"📊 *Ҳисоботи имрӯз* ({t})\n\n"
    txt += f"🛒 Фурӯш: {fmt(furush_row['s'])} сомонӣ ({furush_row['c']} амалиёт)\n"
    txt += f"💸 Хароҷот: {fmt(kharoj_row['s'])} сомонӣ\n"
    txt += f"💰 Фоидаи имрӯз (тахминӣ): {fmt(furush_row['s'] - kharoj_row['s'])} сомонӣ\n\n"
    txt += f"⚠️ Ҷамъи қарзи парадохтнашуда: {fmt(qarz_row['s'])} сомонӣ\n"
    txt += f"📦 Номгӯи мол дар анбор: {mol_count['c']}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")

# ---------- MAIN ----------
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("hisobot", hisobot))
    app.add_handler(MessageHandler(filters.Regex("^📊 Ҳисобот$"), hisobot))

    mol_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📦 Мол$"), mol_start)],
        states={
            M_NOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, mol_nom)],
            M_MIQDOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, mol_miqdor)],
            M_NARX_K: [MessageHandler(filters.TEXT & ~filters.COMMAND, mol_narx_k)],
            M_NARX_F: [MessageHandler(filters.TEXT & ~filters.COMMAND, mol_narx_f)],
        },
        fallbacks=[CommandHandler("bekor", cancel)],
    )

    furush_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🛒 Фурӯш$"), furush_start)],
        states={
            F_MOL: [CallbackQueryHandler(furush_mol_chosen, pattern="^sell_")],
            F_MIQDOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, furush_miqdor)],
        },
        fallbacks=[CommandHandler("bekor", cancel)],
    )

    qarz_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💰 Қарз$"), qarz_start)],
        states={
            Q_MIZOJ: [MessageHandler(filters.TEXT & ~filters.COMMAND, qarz_mizoj)],
            Q_SUMMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, qarz_summa)],
            Q_TAVSIF: [MessageHandler(filters.TEXT & ~filters.COMMAND, qarz_tavsif)],
        },
        fallbacks=[CommandHandler("bekor", cancel)],
    )

    kharoj_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💸 Хароҷот$"), kharoj_start)],
        states={
            KH_TAVSIF: [MessageHandler(filters.TEXT & ~filters.COMMAND, kharoj_tavsif)],
            KH_SUMMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, kharoj_summa)],
        },
        fallbacks=[CommandHandler("bekor", cancel)],
    )

    app.add_handler(mol_conv)
    app.add_handler(furush_conv)
    app.add_handler(qarz_conv)
    app.add_handler(kharoj_conv)

    logger.info("Бот оғоз шуд...")
    app.run_polling()

if __name__ == "__main__":
    main()
