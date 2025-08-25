import csv
import os
import json
import sqlite3
from datetime import datetime
from contextlib import contextmanager
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.request import HTTPXRequest
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv('config.env')

# ==== CONSTANTES ====
# Rendre le chemin DB configurable pour pointer vers un stockage persistant en production
DB_FILE = os.getenv("DB_FILE", "signalements.db")
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
                photo_id TEXT,
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
            SELECT date_heure, utilisateur, type, message, photo_id, latitude, longitude
            FROM signalements
            ORDER BY date_heure DESC
        """)
        for row in cursor.fetchall():
            df.append({
                "Date/Heure": row["date_heure"],
                "Utilisateur": row["utilisateur"],
                "Type": row["type"],
                "Message": row["message"],
                "Photo": row["photo_id"] if row["photo_id"] else None,
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

    # Proposer ajout de photo OU localisation
    bouton_photo = KeyboardButton("📷 Joindre une photo")
    bouton_loc = KeyboardButton("📍 Envoyer ma localisation", request_location=True)
    reply_markup = ReplyKeyboardMarkup([[bouton_photo, bouton_loc]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "Vous pouvez d'abord ajouter une photo, puis envoyer votre localisation.",
        reply_markup=reply_markup
    )
    return LOCALISATION

# ==== Localisation du signalement ====
async def localisation_signalement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.full_name
    texte = context.user_data.get("texte", "")
    type_signalement = context.user_data.get("type_signalement", "Autres")
    location = update.message.location if update and update.message else None

    # Vérifications robustes de la localisation
    if not location or location.latitude is None or location.longitude is None:
        await update.message.reply_text("❌ Localisation invalide ou absente.")
        return await demander_localisation(update, context)
    
    # Vérifier s'il y a une photo dans le contexte (optionnel)
    photo_id = context.user_data.get("photo_id")

    # Enregistre dans DB
    ensure_db_exists()
    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO signalements (date_heure, utilisateur, type, message, photo_id, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            user,
            type_signalement,
            texte,
            photo_id,
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

Voir sur la carte: https://gamousonagedbot-production.up.railway.app/carte"""
            
            if photo_id:
                # Envoyer la photo avec la notification
                await context.bot.send_photo(
                    chat_id=GROUP_CHAT_ID,
                    photo=photo_id,
                    caption=notification
                )
            else:
                # Envoyer seulement le texte
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

Pour configurer les notifications, définissez la variable d'environnement GROUP_CHAT_ID={chat_id}."""
    
    await update.message.reply_text(message)

# ==== Gestion des photos (commande séparée) ====
async def add_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande pour ajouter une photo au signalement en cours"""
    if update.message.photo:
        photo = update.message.photo[-1]  # La plus grande taille
        context.user_data["photo_id"] = photo.file_id
        # Après une photo, ne proposer QUE la localisation
        bouton_loc = KeyboardButton("📍 Envoyer ma localisation", request_location=True)
        reply_markup = ReplyKeyboardMarkup([[bouton_loc]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(
            "✅ Photo ajoutée au signalement ! Maintenant, envoyez votre localisation.",
            reply_markup=reply_markup,
        )
        return LOCALISATION
    else:
        await update.message.reply_text("❌ Veuillez envoyer une photo.")

async def demander_localisation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invite l'utilisateur à partager sa localisation avec le bouton dédié."""
    bouton_loc = KeyboardButton("📍 Envoyer ma localisation", request_location=True)
    reply_markup = ReplyKeyboardMarkup([[bouton_loc]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "Veuillez partager votre localisation en appuyant sur le bouton ci-dessous.",
        reply_markup=reply_markup,
    )
    return LOCALISATION

async def demander_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invite l'utilisateur à prendre/joindre une photo via l'appareil/le trombone."""
    await update.message.reply_text(
        "Appuyez sur l'icône appareil photo ou trombone de Telegram pour prendre/joindre une photo, puis envoyez-la ici.",
        reply_markup=ReplyKeyboardRemove()
    )
    return TEXTE

def build_application():
    """Construit et retourne l'application Telegram (python-telegram-bot Application)."""
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN non défini dans les variables d'environnement")

    # Configurer des timeouts HTTP explicites pour éviter les erreurs ReadError intermittentes
    request = HTTPXRequest(
        connect_timeout=15,
        read_timeout=60,
        write_timeout=15,
        pool_timeout=15,
    )
    application = ApplicationBuilder().token(BOT_TOKEN).request(request).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOIX: [MessageHandler(filters.TEXT & ~filters.COMMAND, choix_type)],
            TEXTE: [
                MessageHandler(filters.TEXT & filters.Regex(r"^📷 Joindre une photo$"), demander_photo),
                MessageHandler(filters.PHOTO, add_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, texte_signalement),
            ],
            LOCALISATION: [
                MessageHandler(filters.TEXT & filters.Regex(r"^📷 Joindre une photo$"), demander_photo),
                MessageHandler(filters.PHOTO, add_photo),
                MessageHandler(filters.LOCATION, localisation_signalement),
                MessageHandler(filters.TEXT & ~filters.COMMAND, demander_localisation),
            ]
        },
        fallbacks=[],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("groupinfo", get_group_info))
    application.add_handler(CommandHandler("photo", add_photo))

    return application

# ==== MAIN ====
if __name__ == "__main__":
    app = build_application()
    print("🚀 Bot SONAGED actif…")
    if GROUP_CHAT_ID:
        print(f"📢 Notifications activées pour le groupe: {GROUP_CHAT_ID}")
    else:
        print("⚠️ Notifications groupe désactivées (GROUP_CHAT_ID = None)")
    app.run_polling()