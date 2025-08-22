#!/usr/bin/env python3
"""
Script de migration CSV vers SQLite
Migre les données existantes de signalements.csv vers signalements.db
"""

import csv
import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager

CSV_FILE = "signalements.csv"
DB_FILE = "signalements.db"

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def create_db_schema():
    """Crée la table signalements si elle n'existe pas"""
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

def migrate_csv_to_sqlite():
    """Migre les données du CSV vers SQLite"""
    if not os.path.exists(CSV_FILE):
        print(f"❌ Fichier {CSV_FILE} non trouvé. Aucune migration nécessaire.")
        return
    
    create_db_schema()
    
    migrated_count = 0
    with open(CSV_FILE, "r", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        
        with get_db_connection() as conn:
            for row in reader:
                try:
                    # Conversion des coordonnées
                    latitude = float(row["Latitude"]) if row["Latitude"] else None
                    longitude = float(row["Longitude"]) if row["Longitude"] else None
                    
                    # Insertion dans SQLite
                    conn.execute("""
                        INSERT INTO signalements (date_heure, utilisateur, type, message, latitude, longitude)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        row["Date/Heure"],
                        row["Utilisateur"],
                        row["Type"],
                        row["Message"],
                        latitude,
                        longitude
                    ))
                    migrated_count += 1
                    
                except Exception as e:
                    print(f"⚠️ Erreur lors de la migration de la ligne: {row}")
                    print(f"   Erreur: {e}")
                    continue
            
            conn.commit()
    
    print(f"✅ Migration terminée: {migrated_count} signalements migrés vers SQLite")
    
    # Vérification
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) as count FROM signalements")
        total_count = cursor.fetchone()["count"]
        print(f"📊 Total signalements dans la base: {total_count}")

if __name__ == "__main__":
    print("🔄 Migration CSV vers SQLite...")
    migrate_csv_to_sqlite()
    print("✅ Migration terminée!") 