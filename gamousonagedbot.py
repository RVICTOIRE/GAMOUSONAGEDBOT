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
CHOIX, TEXTE, PHOTO, LOCALISATION = range(4)

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

    # Demande photo (optionnelle)
    menu_photo = [["📸 Prendre une photo", "⏭️ Passer cette étape"]]
    reply_markup = ReplyKeyboardMarkup(menu_photo, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Voulez-vous ajouter une photo au signalement ?", reply_markup=reply_markup)
    return PHOTO

# ==== Gestion de la photo ====
async def gestion_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choix = update.message.text
    
    if choix == "📸 Prendre une photo":
        # Demande de prendre une photo
        bouton_photo = KeyboardButton("📷 Prendre une photo", request_contact=False)
        reply_markup = ReplyKeyboardMarkup([[bouton_photo]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("Veuillez prendre une photo du problème :", reply_markup=reply_markup)
        return PHOTO
    
    elif choix == "⏭️ Passer cette étape":
        # Pas de photo, on passe à la localisation
        context.user_data["photo_id"] = None
        bouton_loc = KeyboardButton("📍 Envoyer ma localisation", request_location=True)
        reply_markup = ReplyKeyboardMarkup([[bouton_loc]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("Veuillez envoyer votre localisation :", reply_markup=reply_markup)
        return LOCALISATION
    
    elif update.message.photo:
        # Photo reçue
        photo = update.message.photo[-1]  # La plus grande taille
        context.user_data["photo_id"] = photo.file_id
        
        bouton_loc = KeyboardButton("📍 Envoyer ma localisation", request_location=True)
        reply_markup = ReplyKeyboardMarkup([[bouton_loc]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("✅ Photo reçue ! Maintenant, veuillez envoyer votre localisation :", reply_markup=reply_markup)
        return LOCALISATION
    
    else:
        await update.message.reply_text("Veuillez choisir une option ou envoyer une photo.")
        return PHOTO

# ==== Localisation du signalement ====
async def localisation_signalement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.full_name
    texte = context.user_data.get("texte", "")
    type_signalement = context.user_data.get("type_signalement", "Autres")
    photo_id = context.user_data.get("photo_id")
    location = update.message.location

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


def build_application():
    """Construit et retourne l'application Telegram (python-telegram-bot Application)."""
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN non défini dans les variables d'environnement")

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOIX: [MessageHandler(filters.TEXT & ~filters.COMMAND, choix_type)],
            TEXTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, texte_signalement)],
            PHOTO: [MessageHandler(filters.TEXT | filters.PHOTO, gestion_photo)],
            LOCALISATION: [MessageHandler(filters.LOCATION, localisation_signalement)]
        },
        fallbacks=[],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("groupinfo", get_group_info))

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