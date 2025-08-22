#!/usr/bin/env python3
"""
Script de test pour vérifier la fonctionnalité photo
"""

import sqlite3
import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv('config.env')

def test_database_structure():
    """Teste la structure de la base de données"""
    db_file = "signalements.db"
    
    if not os.path.exists(db_file):
        print(f"❌ Base de données {db_file} n'existe pas")
        return False
    
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        # Vérifier la structure de la table
        cursor.execute("PRAGMA table_info(signalements)")
        columns = [column[1] for column in cursor.fetchall()]
        
        print("📋 Structure de la table signalements :")
        for column in cursor.fetchall():
            print(f"  - {column[1]} ({column[2]})")
        
        # Vérifier si photo_id existe
        if "photo_id" in columns:
            print("✅ Colonne photo_id présente")
        else:
            print("❌ Colonne photo_id manquante")
            return False
        
        # Compter les signalements
        cursor.execute("SELECT COUNT(*) FROM signalements")
        count = cursor.fetchone()[0]
        print(f"📊 Nombre de signalements : {count}")
        
        # Vérifier les signalements avec photos
        cursor.execute("SELECT COUNT(*) FROM signalements WHERE photo_id IS NOT NULL")
        photo_count = cursor.fetchone()[0]
        print(f"📸 Signalements avec photos : {photo_count}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Erreur lors du test : {e}")
        return False

def test_api_endpoints():
    """Teste les endpoints de l'API"""
    print("\n🌐 Test des endpoints API :")
    
    # Simuler une requête GET
    try:
        import requests
        response = requests.get("http://127.0.0.1:5000/signalements.json", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ GET /signalements.json : {len(data)} signalements")
            
            # Vérifier la structure des données
            if data and "Photo" in data[0]:
                print("✅ Champ Photo présent dans les données")
            else:
                print("⚠️ Champ Photo manquant dans les données")
        else:
            print(f"❌ GET /signalements.json : {response.status_code}")
    except Exception as e:
        print(f"❌ Erreur API : {e}")

if __name__ == "__main__":
    print("🧪 Test de la fonctionnalité photo...")
    
    # Test de la base de données
    if test_database_structure():
        print("✅ Tests de base de données réussis")
    else:
        print("❌ Tests de base de données échoués")
    
    # Test des endpoints API
    test_api_endpoints()
    
    print("\n🎯 Résumé :")
    print("- Vérifiez que la colonne photo_id existe")
    print("- Testez le bot avec /start")
    print("- Vérifiez les notifications dans le groupe") 