import csv
import os
import json
import sqlite3
from datetime import datetime
from contextlib import contextmanager
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv('config.env')

# ==== CONSTANTES ====
DB_FILE = "signalements.db"
BOT_TOKEN = os.getenv('BOT_TOKEN')
GROUP_CHAT_ID = int(os.getenv('GROUP_CHAT_ID', 0)) if os.getenv('GROUP_CHAT_ID') else None

# États de la conversation
CHOIX, TEXTE, LOCALISATION = range(3)

# ==== Connexion base de données ====
@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# ==== Crée DB s'il n'existe pas ====
def ensure_db_exists():
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signalements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date_heure TEXT NOT NULL,
                utilisateur TEXT NOT NULL,
                type TEXT NOT NULL,
                message TEXT NOT NULL,
                latitude REAL,
                longitude REAL
            )
        """)
        conn.commit()

# ==== Fonction mise à jour JSON ====
def mise_a_jour_json():
    ensure_db_exists()
    df = []
    with get_db_connection() as conn:
        cursor = conn.execute("""
            SELECT date_heure, utilisateur, type, message, latitude, longitude
            FROM signalements
            ORDER BY date_heure DESC
        """)
        for row in cursor.fetchall():
            df.append({
                "Date/Heure": row["date_heure"],
                "Utilisateur": row["utilisateur"],
                "Type": row["type"],
                "Message": row["message"],
                "Latitude": row["latitude"],
                "Longitude": row["longitude"]
            })
    with open("signalements.json", "w", encoding="utf-8") as f:
        json.dump(df, f, ensure_ascii=False, indent=4)

# ==== /start ====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu = [["📍 Dépôt", "🗑 Bac plein", "🔹 Autres"]]
    reply_markup = ReplyKeyboardMarkup(menu, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Que souhaitez-vous signaler ?", reply_markup=reply_markup)
    return CHOIX

# ==== Choix du type ====
async def choix_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["type_signalement"] = update.message.text
    await update.message.reply_text("Merci. Veuillez préciser les détails du signalement.")
    return TEXTE

# ==== Texte du signalement ====
async def texte_signalement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.full_name
    type_signalement = context.user_data.get("type_signalement", "Autres")
    texte = update.message.text
    context.user_data["texte"] = texte

    # Demande localisation
    bouton_loc = KeyboardButton("📍 Envoyer ma localisation", request_location=True)
    reply_markup = ReplyKeyboardMarkup([[bouton_loc]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Merci ! Veuillez envoyer votre localisation :", reply_markup=reply_markup)
    return LOCALISATION

# ==== Localisation du signalement ====
async def localisation_signalement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.full_name
    texte = context.user_data.get("texte", "")
    type_signalement = context.user_data.get("type_signalement", "Autres")
    location = update.message.location

    # Enregistre dans DB
    ensure_db_exists()
    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO signalements (date_heure, utilisateur, type, message, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            user,
            type_signalement,
            texte,
            location.latitude,
            location.longitude
        ))
        conn.commit()

    # Mise à jour JSON
    mise_a_jour_json()

    # Notification au groupe (si configuré)
    if GROUP_CHAT_ID:
        try:
            notification = f"""🚨 NOUVEAU SIGNALEMENT

📍 Type: {type_signalement}
👤 Utilisateur: {user}
📝 Message: {texte}
🌍 Localisation: {location.latitude}, {location.longitude}
🕐 Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

Voir sur la carte: http://127.0.0.1:5000/carte"""
            
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=notification,
                disable_web_page_preview=True
            )
        except Exception as e:
            print(f"Erreur notification groupe: {e}")

    await update.message.reply_text("✅ Signalement complet enregistré !")
    context.user_data.clear()
    return await start(update, context)  # Retour au menu principal

# ==== Fonction pour récupérer l'ID du groupe ====
async def get_group_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande pour récupérer l'ID du groupe"""
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    chat_title = update.effective_chat.title or "Chat privé"
    
    message = f"""📋 Informations du chat:

🏷 Type: {chat_type}
📝 Nom: {chat_title}
🆔 Chat ID: {chat_id}

Pour configurer les notifications, remplacez GROUP_CHAT_ID = None par GROUP_CHAT_ID = {chat_id} dans le code."""
    
    await update.message.reply_text(message)

# ==== MAIN ====
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOIX: [MessageHandler(filters.TEXT & ~filters.COMMAND, choix_type)],
            TEXTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, texte_signalement)],
            LOCALISATION: [MessageHandler(filters.LOCATION, localisation_signalement)]
        },
        fallbacks=[],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("groupinfo", get_group_info))
    
    print("🚀 Bot SONAGED actif…")
    if GROUP_CHAT_ID:
        print(f"📢 Notifications activées pour le groupe: {GROUP_CHAT_ID}")
    else:
        print("⚠️ Notifications groupe désactivées (GROUP_CHAT_ID = None)")
    app.run_polling()