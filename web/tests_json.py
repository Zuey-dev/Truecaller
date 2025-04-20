import os
import json

# Afficher le contenu du répertoire actuel
print("Contenu du répertoire:")
for file in os.listdir("."):
    print(f" - {file}")

# Vérifier si ranking.json existe
if os.path.exists("ranking.json"):
    print("\nLe fichier ranking.json existe.")
    try:
        with open("ranking.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        print("Le fichier JSON est valide.")
        print(f"Date de mise à jour: {data.get('updated_at', 'Non trouvée')}")
        print(f"Nombre de joueurs: {len(data.get('players', []))}")
    except json.JSONDecodeError as e:
        print(f"Erreur de décodage JSON: {e}")
    except Exception as e:
        print(f"Erreur lors de la lecture du fichier: {e}")
else:
    print("\nLe fichier ranking.json n'existe pas dans ce répertoire.")