import os
import subprocess
import time
import shutil

def sync_to_github():
    """Synchronise les fichiers JSON avec le dépôt GitHub"""
    try:
        # Chemin vers votre dépôt local
        repo_path = "chemin/vers/votre/repo/github"
        
        # Fichiers à synchroniser
        files_to_sync = ["ranking.json", "lp_history.json"]
        
        # Copier les fichiers vers le dépôt
        for file in files_to_sync:
            if os.path.exists(file):
                shutil.copy(file, os.path.join(repo_path, file))
                print(f"Fichier {file} copié vers le dépôt")
        
        # Changer de répertoire vers le dépôt
        os.chdir(repo_path)
        
        # Ajouter les fichiers modifiés
        subprocess.run(["git", "add", *files_to_sync])
        
        # Créer un commit avec un message incluant l'horodatage
        commit_message = f"Mise à jour des données - {time.strftime('%Y-%m-%d %H:%M:%S')}"
        subprocess.run(["git", "commit", "-m", commit_message])
        
        # Pousser les changements
        subprocess.run(["git", "push"])
        
        print("Synchronisation avec GitHub réussie")
        return True
    except Exception as e:
        print(f"Erreur lors de la synchronisation avec GitHub: {e}")
        return False