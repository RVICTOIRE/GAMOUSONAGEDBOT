# 📱 Guide d'Utilisation - Bot SONAGED

## 🚀 **Comment utiliser le bot**

### **Flux principal (sans photo) :**
1. **`/start`** → Choisir le type de signalement
2. **Taper le message** → Décrire le problème
3. **📍 Envoyer la localisation** → Position GPS (bouton affiché)

### **Flux avec photo (optionnel) :**
1. **`/start`** → Choisir le type de signalement
2. **Taper le message** → Décrire le problème
3. Appuyer sur **📷 Joindre une photo** puis envoyer une vraie photo (ou une image comme document)
4. Le bot affiche ensuite uniquement **📍 Envoyer ma localisation** → partager la position GPS

## 📸 **Comment ajouter une photo**

### **Méthode 1 : Bouton "📷 Joindre une photo"**
- Appuyez sur le bouton, puis utilisez l'appareil photo ou le trombone pour envoyer la photo
- Après réception, le bot propose uniquement la localisation

### **Méthode 2 : Photo spontanée**
- Envoyez une photo (ou une image comme document) à n'importe quel moment du flux
- Le bot l'ajoute et affiche uniquement le bouton localisation

## 🎯 **Commandes disponibles**

- **`/start`** - Démarrer un nouveau signalement
- **`/groupinfo`** - Voir les informations du groupe (pour configurer les notifications)

## ✅ **Avantages de cette approche**

- **🔄 Simple** : Pas d'étapes complexes
- **⚡ Flexible** : Photo optionnelle à n'importe quel moment
- **🛡️ Robuste** : Moins d'erreurs possibles
- **📱 Intuitif** : Interface familière

## 🔧 **Résolution de problèmes**

### **Le bot ne répond pas :**
- Vérifiez que vous avez envoyé `/start` au moins une fois
- Assurez-vous que le bot est actif sur Railway

### **La photo ne s'affiche pas :**
- Assurez-vous d'envoyer une vraie photo (ou un document image), pas un fichier non image
- En groupe, vérifiez que `GROUP_CHAT_ID` est correctement configuré côté bot

### **Erreur de localisation :**
- Assurez-vous d'avoir activé la géolocalisation
- Utilisez le bouton "📍 Envoyer ma localisation"

## 🎉 **C'est tout !**

Le bot est maintenant **optimisé et simplifié**. Plus de problèmes avec les états complexes ! 

---

## 🌐 Déploiement (Webhook)

Le bot peut fonctionner en **polling** (local/dev) ou en **webhook** (prod).

### Variables d'environnement importantes (bot):
- **`BOT_TOKEN`**: jeton Telegram
- **`GROUP_CHAT_ID`**: ID du groupe pour les notifications (optionnel)
- **`DB_FILE`**: chemin absolu vers la base SQLite (ex: `/data/signalements.db`)
- **`WEBHOOK_URL`**: URL publique (ex: `https://votre-domaine/bot`)
- **`WEBHOOK_PATH`**: chemin webhook (défaut: `/webhook`)
- **`WEBHOOK_SECRET`**: secret optionnel de vérification
- **`PORT`**: port d'écoute du service bot (défaut: `8080`)

Si `WEBHOOK_URL` est défini, le bot démarre en webhook; sinon, en polling.

### Variables d'environnement (API Flask):
- **`DB_FILE`**: même chemin que le bot pour partager la même base
- **`JSON_FILE`**: (optionnel) snapshot JSON

### Conseils production:
- Pointez `DB_FILE` du bot et de l'API vers le même volume persistant
- Exposez le port du bot derrière un reverse proxy HTTPS (Nginx/Cloudflare)
- Vérifiez `GET /debug/signalements` côté API pour confirmer la lecture DB