#!/usr/bin/env python3
"""
Script pour lancer le bot Telegram sur Railway
"""

import os
import sys
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv('config.env')

# Vérifier que le token est configuré
if not os.getenv('BOT_TOKEN'):
    print("❌ Erreur: BOT_TOKEN non configuré dans les variables d'environnement")
    sys.exit(1)

# Importer la factory et lancer le bot
from gamousonagedbot import build_application, GROUP_CHAT_ID

if __name__ == "__main__":
    print("🤖 Démarrage du bot Telegram SONAGED...")
    if GROUP_CHAT_ID:
        print(f"📢 Notifications activées pour le groupe: {GROUP_CHAT_ID}")
    else:
        print("⚠️ Notifications groupe désactivées (GROUP_CHAT_ID = None)")
    application = build_application()
    application.run_polling() 