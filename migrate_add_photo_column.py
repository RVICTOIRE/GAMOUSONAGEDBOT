#!/usr/bin/env python3
"""
Script de migration pour ajouter la colonne photo_id à la base de données existante
"""

import sqlite3
import os

def migrate_database():
    """Ajoute la colonne photo_id à la table signalements si elle n'existe pas"""
    
    db_file = "signalements.db"
    
    if not os.path.exists(db_file):
        print(f"✅ Base de données {db_file} n'existe pas encore, elle sera créée automatiquement")
        return
    
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        # Vérifier si la colonne photo_id existe déjà
        cursor.execute("PRAGMA table_info(signalements)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if "photo_id" not in columns:
            print("🔄 Ajout de la colonne photo_id...")
            cursor.execute("ALTER TABLE signalements ADD COLUMN photo_id TEXT")
            conn.commit()
            print("✅ Colonne photo_id ajoutée avec succès")
        else:
            print("✅ Colonne photo_id existe déjà")
        
        # Afficher la structure de la table
        cursor.execute("PRAGMA table_info(signalements)")
        print("\n📋 Structure de la table signalements :")
        for column in cursor.fetchall():
            print(f"  - {column[1]} ({column[2]})")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Erreur lors de la migration : {e}")

if __name__ == "__main__":
    print("🚀 Migration de la base de données pour le support des photos...")
    migrate_database()
    print("✅ Migration terminée") 