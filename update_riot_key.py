import os
import requests
from dotenv import load_dotenv

def check_riot_key_validity(api_key):
    """Vérifie si la clé Riot est valide."""
    url = "https://euw1.api.riotgames.com/lol/status/v4/platform-data"
    headers = {"X-Riot-Token": api_key}
    response = requests.get(url, headers=headers)
    return response.status_code == 200

def update_riot_key(new_key):
    """Met à jour la clé Riot dans le fichier config.env."""
    with open("config.env", "r") as file:
        lines = file.readlines()

    with open("config.env", "w") as file:
        for line in lines:
            if line.startswith("RIOT_API_KEY="):
                file.write(f"RIOT_API_KEY={new_key}\n")
            else:
                file.write(line)

def main():
    load_dotenv(dotenv_path="./config.env")
    current_key = os.getenv("RIOT_API_KEY")

    if not check_riot_key_validity(current_key):
        print("La clé Riot actuelle est invalide ou expirée.")
        # Remplacez cette ligne par le code pour obtenir une nouvelle clé
        new_key = input("Veuillez entrer la nouvelle clé Riot : ")
        update_riot_key(new_key)
        print("La clé Riot a été mise à jour.")
    else:
        print("La clé Riot actuelle est toujours valide.")

if __name__ == "__main__":
    main()