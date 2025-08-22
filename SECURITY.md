# 🔒 Guide de Sécurité

## Configuration des variables d'environnement

### 1. Récupérer un nouveau token Telegram
Si votre token a été exposé sur GitHub :

1. Allez sur [@BotFather](https://t.me/botfather)
2. Tapez `/mybots`
3. Sélectionnez votre bot
4. Cliquez "API Token"
5. Tapez `/revoke` pour révoquer l'ancien token
6. Générez un nouveau token avec `/newtoken`

### 2. Configurer l'application

1. **Copiez le fichier d'exemple :**
```bash
cp config.env.example config.env
```

2. **Éditez `config.env` avec vos vraies valeurs :**
```env
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
GROUP_CHAT_ID=-4818785764
FLASK_SECRET_KEY=your_random_secret_key_here
FLASK_ENV=development
```

3. **Générez une clé secrète Flask :**
```python
import secrets
print(secrets.token_hex(32))
```

### 3. Vérifier que les fichiers sensibles sont ignorés

Assurez-vous que `.gitignore` contient :
```
.env
config.env
*.env
*.db
```

### 4. Supprimer l'historique Git (si nécessaire)

Si le token a été commité :

```bash
git filter-branch --force --index-filter \
"git rm --cached --ignore-unmatch gamousonagedbot.py" \
--prune-empty --tag-name-filter cat -- --all
```

## Variables d'environnement requises

| Variable | Description | Exemple |
|----------|-------------|---------|
| `BOT_TOKEN` | Token Telegram du bot | `1234567890:ABCdef...` |
| `GROUP_CHAT_ID` | ID du groupe pour notifications | `-4818785764` |
| `FLASK_SECRET_KEY` | Clé secrète Flask | `a1b2c3d4e5f6...` |
| `FLASK_ENV` | Environnement Flask | `development` |

## Déploiement sécurisé

- ✅ Utilisez toujours des variables d'environnement
- ✅ Ne committez jamais de tokens dans Git
- ✅ Utilisez des secrets managers en production
- ✅ Régénérez les tokens exposés immédiatement 