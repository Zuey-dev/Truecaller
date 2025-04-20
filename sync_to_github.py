import os
import subprocess
import time
import shutil

def sync_to_github():
    """Synchronise les fichiers JSON avec le dépôt GitHub"""
    try:
        # Configuration Git
        subprocess.run(["git", "config", "--global", "user.email", "bot@example.com"], check=True)
        subprocess.run(["git", "config", "--global", "user.name", "Bot"], check=True)
        
        # Chemin vers votre dépôt local
        repo_path = "chemin/vers/votre/repo/github"
        
        # Fichiers à synchroniser
        files_to_sync = ["ranking.json", "web/ranking.json", "lp_history.json"]
        
        # Copier les fichiers vers le dépôt
        for file in files_to_sync:
            if os.path.exists(file):
                shutil.copy(file, os.path.join(repo_path, file))
                print(f"Fichier {file} copié vers le dépôt")
        
        # Changer de répertoire vers le dépôt
        os.chdir(repo_path)
        
        # Ajouter les fichiers modifiés
        subprocess.run(["git", "add", *files_to_sync], check=True)
        
        # Créer un commit
        subprocess.run(["git", "commit", "-m", "Update ranking data [bot]"], check=True)
        
        # Pousser les modifications
        subprocess.run(["git", "push", "origin", "main"], check=True)
        
        print("Synchronisation avec GitHub réussie")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors de la synchronisation avec GitHub: {e}")
        return False
    except Exception as e:
        print(f"Exception lors de la synchronisation avec GitHub: {e}")
        return False