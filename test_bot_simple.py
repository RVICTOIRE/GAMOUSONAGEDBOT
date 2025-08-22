#!/usr/bin/env python3
"""
Script de test simple pour vérifier le bot
"""

import sqlite3
import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv('config.env')

def test_bot_configuration():
    """Teste la configuration du bot"""
    print("🔧 Test de configuration du bot...")
    
    # Vérifier les variables d'environnement
    bot_token = os.getenv('BOT_TOKEN')
    group_chat_id = os.getenv('GROUP_CHAT_ID')
    
    if bot_token:
        print("✅ BOT_TOKEN configuré")
    else:
        print("❌ BOT_TOKEN manquant")
        return False
    
    if group_chat_id:
        print(f"✅ GROUP_CHAT_ID configuré: {group_chat_id}")
    else:
        print("⚠️ GROUP_CHAT_ID non configuré (notifications désactivées)")
    
    return True

def test_database():
    """Teste la base de données"""
    print("\n🗄️ Test de la base de données...")
    
    db_file = "signalements.db"
    
    if not os.path.exists(db_file):
        print(f"⚠️ Base de données {db_file} n'existe pas encore")
        return True
    
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        # Vérifier la structure
        cursor.execute("PRAGMA table_info(signalements)")
        columns = [column[1] for column in cursor.fetchall()]
        
        required_columns = ["id", "date_heure", "utilisateur", "type", "message", "photo_id", "latitude", "longitude"]
        
        for col in required_columns:
            if col in columns:
                print(f"✅ Colonne {col} présente")
            else:
                print(f"❌ Colonne {col} manquante")
                return False
        
        # Compter les signalements
        cursor.execute("SELECT COUNT(*) FROM signalements")
        count = cursor.fetchone()[0]
        print(f"📊 Signalements en base: {count}")
        
        # Signalements avec photos
        cursor.execute("SELECT COUNT(*) FROM signalements WHERE photo_id IS NOT NULL")
        photo_count = cursor.fetchone()[0]
        print(f"📸 Signalements avec photos: {photo_count}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Erreur base de données: {e}")
        return False

def test_imports():
    """Teste les imports nécessaires"""
    print("\n📦 Test des imports...")
    
    try:
        import telegram
        print("✅ python-telegram-bot installé")
    except ImportError:
        print("❌ python-telegram-bot manquant")
        return False
    
    try:
        from dotenv import load_dotenv
        print("✅ python-dotenv installé")
    except ImportError:
        print("❌ python-dotenv manquant")
        return False
    
    return True

def main():
    """Fonction principale de test"""
    print("🧪 Test du bot SONAGED optimisé...\n")
    
    # Test des imports
    if not test_imports():
        print("\n❌ Problème avec les dépendances")
        return
    
    # Test de la configuration
    if not test_bot_configuration():
        print("\n❌ Problème de configuration")
        return
    
    # Test de la base de données
    if not test_database():
        print("\n❌ Problème avec la base de données")
        return
    
    print("\n✅ Tous les tests sont passés !")
    print("\n🎯 Le bot est prêt à être utilisé :")
    print("- /start pour commencer un signalement")
    print("- /photo pour ajouter une photo")
    print("- /groupinfo pour voir les infos du groupe")

if __name__ == "__main__":
    main() 