# 📸 Fonctionnalité Photo - Guide

## 🆕 Nouvelle fonctionnalité ajoutée

Le bot Telegram et l'API Flask supportent maintenant **l'ajout de photos** aux signalements !

## 🔄 Nouveau flux de signalement

### 1. **Démarrage** (`/start`)
- Choix du type de signalement

### 2. **Description** 
- Saisie du message détaillé

### 3. **📸 Photo (NOUVEAU)**
- Bouton "📷 Joindre une photo" pour inviter l'envoi d'une vraie photo
- Le bot accepte aussi les images envoyées comme documents (HD)

### 4. **📍 Localisation**
- Envoi de la position GPS

## 🗄️ Base de données mise à jour

### Nouvelle colonne ajoutée :
- `photo_id` : Stocke l'ID de la photo Telegram

### Structure complète :
```sql
CREATE TABLE signalements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date_heure TEXT NOT NULL,
    utilisateur TEXT NOT NULL,
    type TEXT NOT NULL,
    message TEXT NOT NULL,
    photo_id TEXT,           -- NOUVEAU
    latitude REAL,
    longitude REAL
)
```

## 📱 Notifications améliorées

### Dans le groupe Telegram :
- **Avec photo** : Photo + légende avec les détails
- **Sans photo** : Message texte classique

## 🔧 Migration

### Pour mettre à jour une base existante :
```bash
python migrate_add_photo_column.py
```

### Pour un nouveau déploiement :
- La base se crée automatiquement avec la bonne structure

## 🌐 API mise à jour

### Endpoint POST `/api/signalements`
```json
{
  "Utilisateur": "Nom",
  "Type": "📍 Dépôt",
  "Message": "Description",
  "Photo": "photo_file_id_telegram",  // NOUVEAU (optionnel)
  "Latitude": 14.123456,
  "Longitude": -16.123456
}
```

### Endpoint GET `/signalements.json`
```json
[
  {
    "Date/Heure": "2025-08-22 13:30:00",
    "Utilisateur": "Nom",
    "Type": "📍 Dépôt",
    "Message": "Description",
    "Photo": "photo_file_id_telegram",  // NOUVEAU
    "Latitude": 14.123456,
    "Longitude": -16.123456
  }
]
```

## 🚀 Déploiement

### 1. **Commitez les changements :**
```bash
git add .
git commit -m "📸 Ajout support photos aux signalements"
git push origin main
```

### 2. **Sur Railway :**
- Définissez les variables d'env du bot: `BOT_TOKEN`, `DB_FILE`, `WEBHOOK_URL`, `WEBHOOK_PATH` (optionnel), `WEBHOOK_SECRET` (optionnel), `PORT`
- Définissez l'API Flask avec `DB_FILE` identique au bot
- Pointez `WEBHOOK_URL` vers votre domaine public + `WEBHOOK_PATH`

### 3. **Testez :**
- Envoyez `/start` au bot
- Appuyez sur "📷 Joindre une photo" puis envoyez une photo
- Partagez la localisation
- Vérifiez les notifications dans le groupe

## ✅ Avantages

- **📸 Documentation visuelle** des problèmes
- **🔍 Meilleure compréhension** pour les agents
- **📱 Interface intuitive** avec boutons
- **⚡ Optionnel** - pas obligatoire
- **🔄 Compatible** avec les anciens signalements

## 🎯 Utilisation

1. **Utilisateur** : `/start` → Type → Message → **Photo** → Localisation
2. **Bot** : Enregistre tout + notifie le groupe avec photo
3. **Agents** : Voient la photo directement dans le groupe
4. **API** : Photo disponible dans `/signalements.json` 