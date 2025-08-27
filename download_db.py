import os
import subprocess
import sys

def download_railway_db():
    """Télécharge la base de données depuis Railway"""
    print("📥 Téléchargement de la base de données depuis Railway...")
    
    try:
        # Vérifier si Railway CLI est installé
        result = subprocess.run(['railway', '--version'], capture_output=True, text=True)
        if result.returncode != 0:
            print("❌ Railway CLI non installé. Installez-le avec: npm install -g @railway/cli")
            return False
        
        # Se connecter au projet
        print("🔗 Connexion au projet Railway...")
        subprocess.run(['railway', 'login'], check=True)
        
        # Télécharger la base de données
        print("📥 Téléchargement de signalements.db...")
        subprocess.run([
            'railway', 'connect', 
            '--service', 'gamousonagedbot-production',
            '--command', 'cp signalements.db /tmp/signalements.db'
        ], check=True)
        
        subprocess.run([
            'railway', 'download', 
            '--service', 'gamousonagedbot-production',
            '/tmp/signalements.db',
            'signalements.db'
        ], check=True)
        
        print("✅ Base de données téléchargée avec succès!")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Erreur: {e}")
        return False
    except Exception as e:
        print(f"❌ Erreur inattendue: {e}")
        return False

if __name__ == "__main__":
    download_railway_db()
