#!/usr/bin/env python3
"""
Script pour générer une clé secrète Flask sécurisée
"""

import secrets

# Générer une clé secrète de 32 bytes (256 bits)
secret_key = secrets.token_hex(32)

print("🔑 Clé secrète Flask générée :")
print(f"FLASK_SECRET_KEY={secret_key}")
print("\n📝 Copiez cette ligne dans votre config.env") 