import json
import os
import requests
import time
import datetime
import threading
from dotenv import load_dotenv
from sync_to_github import sync_to_github

STATE_FILE = "ranking_state.json"
last_games_info = {}
LAST_MATCHES_FILE = "last_matches.json"

load_dotenv(dotenv_path="./config.env")  # Use forward slashes or raw string

RIOT_API_KEY = os.getenv("RIOT_API_KEY")
WEBHOOK_URL_GAMES = os.getenv("DISCORD_WEBHOOK_URL_GAMES")
WEBHOOK_URL_RANKING = os.getenv("DISCORD_WEBHOOK_URL_RANKING")
REGION = os.getenv("REGION")  # Pour les API spécifiques au serveur (ex: euw1)
SUMMONERS = ["midlaner agité#huge", "DZ De Norvège#huge", "wizaX28#EUW", "sinistre#fling"]  # pseudos avec taglines

# Définir la région continentale basée sur la région du serveur
REGION_ROUTING = {
    "euw1": "europe",
    "na1": "americas",
    "kr": "asia",
    # Ajoutez d'autres correspondances au besoin
}
CONTINENT_REGION = REGION_ROUTING.get(REGION, "europe")  # Par défaut europe si non trouvé

print(f"Riot API key: {RIOT_API_KEY}")
print(f"Region: {REGION}")
print(f"Continent: {CONTINENT_REGION}")
print(f"Webhook URL Games: {WEBHOOK_URL_GAMES}")
print(f"Webhook URL Ranking: {WEBHOOK_URL_RANKING}")

# Emoji pour les rangs
RANK_EMOJIS = {
    "IRON": "<:iron:1363233534017536192>",
    "BRONZE": "<:bronze:1363233379960750201>",
    "SILVER": "<:silver:1363233675566780576>",
    "GOLD": "<:gold:1363233469668262049>",
    "PLATINUM": "<:plat:1363233615349157998>",
    "DIAMOND": ":diamond:",
    "MASTER": ":master:",
    "GRANDMASTER": ":grandmaster:",
    "CHALLENGER": ":challenger:",
    "UNRANKED": ":unranked:"
}

# eviter les répétitions de parties
last_matches = {}
# Pour stocker les informations de rang des joueurs
player_ranks = {}
# Timestamp du dernier envoi de classement
last_ranking_sent = None

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

def riot_key_manager():
    """Gère la vérification et la mise à jour de la clé Riot."""
    while True:
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

        # Vérifier toutes les 24 heures
        time.sleep(86400)  # 24 * 60 * 60 secondes

def get_puuid_by_riot_id(riot_id):
    try:
        # Séparer le nom de jeu et le tag
        game_name, tag_line = riot_id.split("#")
        
        # Utiliser l'API ACCOUNT-V1 avec la région continentale correcte
        url = f"https://{CONTINENT_REGION}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
        headers = {"X-Riot-Token": RIOT_API_KEY}
        
        res = requests.get(url, headers=headers)
        
        if res.status_code == 200:
            data = res.json()
            print(f"PUUID trouvé pour {riot_id}: {data['puuid'][:8]}...")
            return data["puuid"]
        else:
            print(f"Erreur lors de la récupération du PUUID pour {riot_id}: {res.status_code}")
            print(f"Détails: {res.text}")
            return None
            
    except Exception as e:
        print(f"Exception lors de la récupération du PUUID pour {riot_id}: {e}")
        return None

def get_summoner_id_by_puuid(puuid):
    """Récupérer le summoner ID à partir du PUUID"""
    url = f"https://{REGION}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    
    res = requests.get(url, headers=headers)
    
    if res.status_code == 200:
        return res.json()["id"]
    else:
        print(f"Erreur lors de la récupération du summoner ID pour PUUID {puuid[:8]}...: {res.status_code}")
        return None

def get_player_rank(summoner_id):
    """Récupérer le rang du joueur"""
    url = f"https://{REGION}.api.riotgames.com/lol/league/v4/entries/by-summoner/{summoner_id}"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    
    res = requests.get(url, headers=headers)
    
    if res.status_code == 200:
        # Filtrer pour obtenir uniquement les données de ranked solo
        ranked_solo = None
        for queue in res.json():
            if queue["queueType"] == "RANKED_SOLO_5x5":
                ranked_solo = queue
                break
        
        if ranked_solo:
            return {
                "tier": ranked_solo["tier"],
                "rank": ranked_solo["rank"],
                "lp": ranked_solo["leaguePoints"]
            }
        else:
            # Si pas de rang en solo queue
            return {
                "tier": "UNRANKED",
                "rank": "",
                "lp": 0
            }
    else:
        print(f"Erreur lors de la récupération du rang pour summoner ID {summoner_id}: {res.status_code}")
        return None

def get_latest_match_id(puuid):
    # Utiliser la région continentale pour l'API match-v5
    url = f"https://{CONTINENT_REGION}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count=1"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    
    res = requests.get(url, headers=headers)
    
    if res.status_code == 200 and res.json():
        return res.json()[0]
    else:
        print(f"Erreur ou pas de match récent pour PUUID {puuid[:8]}...: {res.status_code}")
        return None

def get_match_details(match_id):
    # Utiliser la région continentale pour l'API match-v5
    url = f"https://{CONTINENT_REGION}.api.riotgames.com/lol/match/v5/matches/{match_id}"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    
    res = requests.get(url, headers=headers)
    
    if res.status_code == 200:
        return res.json()
    else:
        print(f"Erreur lors de la récupération des détails du match {match_id}: {res.status_code}")
        return None

def send_to_discord(content, webhook_type="games"):
    """Envoyer un message à Discord en fonction du type de webhook"""
    webhook_url = WEBHOOK_URL_GAMES if webhook_type == "games" else WEBHOOK_URL_RANKING
    
    data = {"content": content}
    response = requests.post(webhook_url, json=data)
    
    if response.status_code in (200, 204):
        print(f"Message envoyé avec succès à Discord ({webhook_type})")
    else:
        print(f"Erreur lors de l'envoi à Discord ({webhook_type}): {response.status_code}, {response.text}")

def update_player_ranks():
    """Mettre à jour les rangs de tous les joueurs"""
    for riot_id in SUMMONERS:
        try:
            # Extraction du nom de joueur
            player_name = riot_id.split("#")[0]
            
            # Récupérer le PUUID avec la nouvelle fonction
            puuid = get_puuid_by_riot_id(riot_id)
            if not puuid:
                continue
                
            summoner_id = get_summoner_id_by_puuid(puuid)
            if not summoner_id:
                continue
                
            rank_info = get_player_rank(summoner_id)
            if rank_info:
                # Stocker les informations de rang avec le nom du joueur
                player_ranks[player_name] = rank_info
                print(f"Rang mis à jour pour {player_name}: {rank_info['tier']} {rank_info['rank']} {rank_info['lp']} LP")
        except Exception as e:
            print(f"Erreur lors de la mise à jour du rang pour {riot_id}: {e}")

def get_tier_value(tier):
    """Convertir le tier en valeur numérique pour le tri"""
    tier_values = {
        "CHALLENGER": 9,
        "GRANDMASTER": 8,
        "MASTER": 7,
        "DIAMOND": 6,
        "PLATINUM": 5,
        "GOLD": 4,
        "SILVER": 3,
        "BRONZE": 2,
        "IRON": 1,
        "UNRANKED": 0
    }
    return tier_values.get(tier, 0)

def get_rank_value(rank):
    """Convertir le rang en valeur numérique pour le tri"""
    rank_values = {
        "I": 4,
        "II": 3,
        "III": 2,
        "IV": 1,
        "": 0
    }
    return rank_values.get(rank, 0)

def get_win_streak(puuid, max_matches=10):
    url = f"https://{CONTINENT_REGION}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count={max_matches}"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    res = requests.get(url, headers=headers)

    if res.status_code != 200:
        print(f"Erreur récupération des matchs pour streak: {res.status_code}")
        return 0

    match_ids = res.json()
    streak = 0

    for match_id in match_ids:
        match_data = get_match_details(match_id)
        if not match_data:
            continue

        for p in match_data["info"]["participants"]:
            if p["puuid"] == puuid:
                if p["win"]:
                    streak += 1
                else:
                    return streak  # streak brisée
                break

    return streak

def export_ranking_data():
    """Exporte les données de classement dans un fichier JSON pour l'interface web"""
    if not player_ranks:
        print("Aucun rang disponible, impossible d'exporter les données")
        return False
        
    # Trier les joueurs
    sorted_players = sorted(
        player_ranks.items(),
        key=lambda x: (
            get_tier_value(x[1]["tier"]),
            get_rank_value(x[1]["rank"]),
            x[1]["lp"]
        ),
        reverse=True
    )
    
    # Construire les données à exporter pour le site web
    export_data = {
        "rankings": [],
        "last_games": last_games_info,
        "updated_at": int(time.time())
    }
    
    # Charger l'historique des LP s'il existe
    lp_history = {}
    try:
        if os.path.exists("lp_history.json"):
            with open("lp_history.json", "r", encoding="utf-8") as f:
                lp_history = json.load(f)
    except Exception as e:
        print(f"Erreur lors du chargement de l'historique LP: {e}")
        lp_history = {}
    
    # Date du jour au format YYYY-MM-DD
    today = time.strftime("%Y-%m-%d")
    
    for i, (player_name, rank_info) in enumerate(sorted_players):
        # Définir la médaille en fonction du rang
        medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}"
        
        # Obtenir l'emoji du rang
        emoji = RANK_EMOJIS.get(rank_info["tier"], "")
        
        # Formater l'affichage du rang
        tier_display = "Fer" if rank_info["tier"] == "IRON" else rank_info["tier"].capitalize()
        rank_display = "Non classé" if rank_info["tier"] == "UNRANKED" else f"{tier_display} {rank_info['rank']} - {rank_info['lp']} LP"
        
        # Charger les infos de la winstreak si disponible
        puuid = None
        for riot_id in SUMMONERS:
            if riot_id.split("#")[0] == player_name:
                puuid = get_puuid_by_riot_id(riot_id)
                break
                
        streak = get_win_streak(puuid) if puuid else 0
        
        # Mettre à jour l'historique des LP pour ce joueur
        if player_name not in lp_history:
            lp_history[player_name] = []
        
        # Vérifier si nous avons déjà une entrée pour aujourd'hui
        today_entry = next((entry for entry in lp_history[player_name] if entry["date"] == today), None)
        
        if today_entry:
            # Mettre à jour l'entrée existante
            today_entry["lp"] = rank_info["lp"]
        else:
            # Ajouter une nouvelle entrée
            lp_history[player_name].append({
                "date": today,
                "lp": rank_info["lp"]
            })
        
        # Limiter l'historique à 30 jours
        lp_history[player_name] = lp_history[player_name][-30:]
        
        player_data = {
            "name": player_name,
            "rank": rank_display,
            "tier": rank_info["tier"],
            "emoji": emoji,
            "medal": medal,
            "division": rank_info["rank"],
            "lp": rank_info["lp"],
            "win_streak": streak,
            "position": i + 1  # Classement (1er, 2ème, etc.)
        }
        
        export_data["rankings"].append(player_data)
    
    # Ajouter l'historique des LP aux données exportées
    export_data["lp_history"] = lp_history
    
    # Sauvegarder l'historique des LP
    try:
        with open("lp_history.json", "w", encoding="utf-8") as f:
            json.dump(lp_history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erreur lors de la sauvegarde de l'historique LP: {e}")

    # Sauvegarder le fichier ranking.json
    try:
        # Sauvegarder dans le répertoire principal
        with open("ranking.json", "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        # Sauvegarder dans le répertoire web
        os.makedirs("web", exist_ok=True)  # S'assurer que le répertoire web existe
        with open("web/ranking.json", "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        print("Données exportées avec succès")
        return True
    except Exception as e:
        print(f"Erreur d'exportation: {e}")
        return False

def load_ranking_state():
    if not os.path.exists(STATE_FILE):
        return {"message_id": None, "last_sent": None}
    with open(STATE_FILE, "r") as f:
        return json.load(f)

def save_ranking_state(message_id, last_sent):
    with open(STATE_FILE, "w") as f:
        json.dump({
            "message_id": message_id,
            "last_sent": int(last_sent.timestamp())
        }, f)
        print("État du classement sauvegardé")

def save_last_matches():
    with open(LAST_MATCHES_FILE, "w", encoding="utf-8") as f:
        json.dump(last_matches, f)

def send_ranking():
    """Envoyer ou mettre à jour le classement via embed Discord + historique"""
    global last_ranking_sent

    update_player_ranks()

    if not player_ranks:
        print("Aucun rang disponible, impossible d'envoyer le classement")
        return

    export_ranking_data()
    sync_to_github()  # Synchroniser avec GitHub

    # Chargement état précédent (message_id et timestamp)
    state = load_ranking_state()
    message_id = state.get("message_id")
    last_sent_ts = state.get("last_sent")

    # Trie des joueurs
    sorted_players = sorted(
        player_ranks.items(),
        key=lambda x: (
            get_tier_value(x[1]["tier"]),
            get_rank_value(x[1]["rank"]),
            x[1]["lp"]
        ),
        reverse=True
    )

    now = datetime.datetime.now()
    unix_timestamp = int(now.timestamp())

    # Couleurs pour les rangs
    rank_colors = {
        "IRON": 0x5D5D5D,       # Gris foncé
        "BRONZE": 0x8B4513,     # Marron
        "SILVER": 0xC0C0C0,     # Argent
        "GOLD": 0xFFD700,       # Or
        "PLATINUM": 0x00CED1,   # Turquoise
        "DIAMOND": 0x1E90FF,    # Bleu clair
        "MASTER": 0x9932CC,     # Violet
        "GRANDMASTER": 0xFF4500, # Rouge orangé
        "CHALLENGER": 0xFFD700,  # Or
        "UNRANKED": 0x808080    # Gris
    }

    # Déterminer la couleur de l'embed en fonction du joueur en tête
    top_player_tier = sorted_players[0][1]["tier"] if sorted_players else "UNRANKED"
    embed_color = rank_colors.get(top_player_tier, 0x00ffae)

    # Embed principal (classement)
    embed_main = {
        "title": "🏆 Classement des joueurs",
        "description": f"Mis à jour <t:{unix_timestamp}:R>\n\n**Classement actuel des invocateurs**",
        "color": embed_color,
        "thumbnail": {
            "url": "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-static-assets/global/default/images/ranked-mini-regalia/gold.png"
        },
        "fields": [],
        "footer": {
            "text": f"Mise à jour du {now.strftime('%d/%m/%Y à %H:%M:%S')}",
            "icon_url": "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-static-assets/global/default/images/ranked-emblem.png"
        }
    }

    # Créer une description stylisée pour chaque joueur
    for i, (player_name, rank_info) in enumerate(sorted_players):
        # Médailles pour les 3 premiers, numéro pour les autres
        position_display = {
            0: "🥇 **1er**",
            1: "🥈 **2ème**",
            2: "🥉 **3ème**"
        }.get(i, f"**{i+1}.**")
        
        # Emoji du rang
        emoji = RANK_EMOJIS.get(rank_info["tier"], "")
        
        # Formater l'affichage du rang
        tier_display = "Fer" if rank_info["tier"] == "IRON" else rank_info["tier"].capitalize()
        rank_display = "Non classé" if rank_info["tier"] == "UNRANKED" else f"{tier_display} {rank_info['rank']}"
        
        # Récupérer la winstreak
        puuid = None
        for riot_id in SUMMONERS:
            if riot_id.split("#")[0] == player_name:
                puuid = get_puuid_by_riot_id(riot_id)
                break
        
        streak = get_win_streak(puuid) if puuid else 0
        streak_display = f" | 🔥 **{streak} win streak**" if streak > 1 else ""
        
        # Créer une barre de progression pour les LP
        lp_bar_length = 10
        lp_filled = min(lp_bar_length, int(rank_info["lp"] / 100 * lp_bar_length)) if rank_info["tier"] != "UNRANKED" else 0
        lp_bar = "▰" * lp_filled + "▱" * (lp_bar_length - lp_filled)
        
        # Construire le champ pour ce joueur
        field_value = (
            f"{emoji} **{rank_display}** - {rank_info['lp']} LP\n"
            f"{lp_bar} {streak_display}"
        )
        
        embed_main["fields"].append({
            "name": f"{position_display} {player_name}",
            "value": field_value,
            "inline": False
        })

    # === PATCH EXISTANT ===
    if message_id:
        data = {"embeds": [embed_main]}
        edit_url = f"{WEBHOOK_URL_RANKING}/messages/{message_id}"
        response = requests.patch(edit_url, json=data)

        if response.status_code in (200, 204):
            print("Classement mis à jour avec succès")
            save_ranking_state(message_id, now)
        else:
            print(f"Erreur lors de la mise à jour : {response.status_code}, {response.text}")
        return

    # === PREMIER ENVOI : AVEC HISTORIQUE ===
    try:
        with open("last_player_ranks.json", "r") as f:
            previous_ranks = json.load(f)
    except FileNotFoundError:
        previous_ranks = {}

    embed_history = {
        "title": "📈 Évolution des joueurs",
        "color": 0x7289da,
        "description": "Comparaison depuis la dernière mise à jour du classement",
        "thumbnail": {
            "url": "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-static-assets/global/default/images/challenges-images/progression.png"
        },
        "fields": [],
        "footer": {
            "text": "Suivez la progression de vos invocateurs préférés"
        }
    }

    has_changes = False
    for player_name, rank_info in player_ranks.items():
        previous = previous_ranks.get(player_name)
        if not previous:
            continue

        lp_diff = rank_info["lp"] - previous["lp"]
        tier_changed = rank_info["tier"] != previous["tier"]
        rank_changed = rank_info["rank"] != previous["rank"]
        
        # Ne pas afficher les joueurs sans changement
        if lp_diff == 0 and not tier_changed and not rank_changed:
            continue
            
        has_changes = True

        # Emoji pour la direction du changement
        direction_emoji = "📈" if lp_diff > 0 else "📉" if lp_diff < 0 else "➖"
        
        # Formater l'affichage des LP
        lp_sign = "+" if lp_diff > 0 else ""
        lp_change = f"{direction_emoji} **{lp_sign}{lp_diff} LP**"
        
        # Formater l'affichage des rangs
        old_tier = "Fer" if previous["tier"] == "IRON" else previous["tier"].capitalize()
        new_tier = "Fer" if rank_info["tier"] == "IRON" else rank_info["tier"].capitalize()
        
        old_display = "Non classé" if previous["tier"] == "UNRANKED" else f"{old_tier} {previous['rank']}"
        new_display = "Non classé" if rank_info["tier"] == "UNRANKED" else f"{new_tier} {rank_info['rank']}"
        
        # Emoji pour la promotion/rétrogradation
        rank_change_emoji = ""
        if tier_changed or rank_changed:
            if get_tier_value(rank_info["tier"]) > get_tier_value(previous["tier"]) or \
               (rank_info["tier"] == previous["tier"] and get_rank_value(rank_info["rank"]) > get_rank_value(previous["rank"])):
                rank_change_emoji = "🔼"
            else:
                rank_change_emoji = "🔽"
                
        rank_change_text = f"{rank_change_emoji} **{old_display}** → **{new_display}**" if (tier_changed or rank_changed) else ""
        
        # Construire le champ pour ce joueur
        field_value = f"{lp_change}\n{rank_change_text}" if rank_change_text else lp_change
        
        embed_history["fields"].append({
            "name": player_name,
            "value": field_value,
            "inline": True
        })

    # Si aucun changement, ajouter un message
    if not has_changes:
        embed_history["fields"].append({
            "name": "Aucun changement",
            "value": "Aucun joueur n'a changé de rang ou de LP depuis la dernière mise à jour.",
            "inline": False
        })

    data = {"embeds": [embed_main, embed_history]}
    response = requests.post(WEBHOOK_URL_RANKING, json=data)

    if response.status_code in (200, 204):
        print("Classement envoyé avec historique")
        if response.status_code == 200:
            message_id = response.json()["id"]

        save_ranking_state(message_id, now)

        with open("last_player_ranks.json", "w") as f:
            json.dump(player_ranks, f)
    else:
        print(f"Erreur à l'envoi initial : {response.status_code}, {response.text}")

def format_time_since(timestamp):
    """Formater le temps écoulé depuis un timestamp"""
    if timestamp is None:
        return "jamais"
        
    now = datetime.datetime.now()
    delta = now - timestamp
    
    if delta.days > 0:
        return f"{delta.days} jour{'s' if delta.days > 1 else ''}"
    elif delta.seconds >= 3600:
        hours = delta.seconds // 3600
        return f"{hours} heure{'s' if hours > 1 else ''}"
    elif delta.seconds >= 60:
        minutes = delta.seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''}"
    else:
        return f"{delta.seconds} seconde{'s' if delta.seconds > 1 else ''}"

def ranking_scheduler():
    """Planificateur pour envoyer le classement toutes les heures"""
    while True:
        send_ranking()
        # Exporter les données pour le site web également
        export_ranking_data()
        sync_to_github()  # Synchroniser avec GitHub
        # Attendre une heure
        time.sleep(1800)  # 30 * 60 secondes = 30 minutes

def track_players():
    print("Début du suivi des joueurs...")
    
    while True:
        for riot_id in SUMMONERS:
            try:
                print(f"Vérification pour {riot_id}...")
                
                # Définir player_name avant de l'utiliser
                player_name = riot_id.split("#")[0]
                
                # Récupérer le PUUID avec la nouvelle fonction
                puuid = get_puuid_by_riot_id(riot_id)
                
                if not puuid:
                    print(f"Impossible de trouver le PUUID pour {riot_id}, on passe au joueur suivant")
                    continue
                
                # Stocker les informations de rang AVANT le match
                previous_rank_info = player_ranks.get(player_name, None)
                
                # Récupérer le dernier match
                latest_match = get_latest_match_id(puuid)
                
                if not latest_match:
                    print(f"Pas de match récent trouvé pour {riot_id}")
                    continue
                
                # Vérifier si c'est un nouveau match
                if riot_id in last_matches and last_matches[riot_id] == latest_match:
                    print(f"Pas de nouveau match pour {riot_id}")
                    continue
                
                print(f"Nouveau match trouvé pour {riot_id}: {latest_match}")
                
                # Récupérer les détails du match
                match_data = get_match_details(latest_match)
                
                if not match_data:
                    print(f"Impossible d'obtenir les détails du match pour {riot_id}")
                    continue
                
                # Récupérer la durée du match
                game_duration_seconds = match_data["info"]["gameDuration"]
                game_duration_minutes = game_duration_seconds // 60
                game_duration_seconds %= 60
                game_duration_formatted = f"{game_duration_minutes}m {game_duration_seconds}s"
                
                # Mettre à jour le rang du joueur APRÈS le match - AVANT de créer l'embed
                summoner_id = get_summoner_id_by_puuid(puuid)
                if summoner_id:
                    rank_info = get_player_rank(summoner_id)
                    if rank_info:
                        player_ranks[player_name] = rank_info
                    else:
                        rank_info = None
                else:
                    rank_info = None
                
                # Trouver le joueur dans les participants
                player_found = False
                for p in match_data["info"]["participants"]:
                    if p["puuid"] == puuid:
                        player_found = True
                        champ = p["championName"]
                        kills = p["kills"]
                        deaths = p["deaths"]
                        assists = p["assists"]
                        win = p["win"]
                        
                        # Calculer le KDA
                        kda = (kills + assists) / max(1, deaths)  # Éviter division par zéro
                        kda_formatted = f"{kda:.2f}"

                        # Calcul de la win streak
                        streak = get_win_streak(puuid)
                        streak_text = f"{streak} win{'s' if streak > 1 else ''} de suite !" if streak > 1 else "Aucune winstreak..."

                        # Formater le nom du champion correctement
                        champion_image_name = champ.replace(" ", "").replace("'", "")
                        champion_icon_url = f"https://ddragon.leagueoflegends.com/cdn/14.8.1/img/champion/{champion_image_name}.png"

                        # Construire l'embed Discord
                        embed = {
                            "embeds": [
                                {
                                    "title": f"🎮 {player_name} a terminé une partie !",
                                    "color": 0x57F287 if win else 0xFF4C4C,  # Vert si victoire, rouge si défaite
                                    "thumbnail": {"url": champion_icon_url},
                                    "description": f"**{champ}** | {game_duration_formatted} de jeu",
                                    "fields": [
                                        {
                                            "name": "Résultat",
                                            "value": "✅ **VICTOIRE**" if win else "❌ **DÉFAITE**",
                                            "inline": True
                                        },
                                        {
                                            "name": "KDA",
                                            "value": f"**{kills}** / **{deaths}** / **{assists}**\n*{kda_formatted}* KDA",
                                            "inline": True
                                        },
                                        {
                                            "name": "Farm & Dégâts",
                                            "value": f"🧟 **{p['totalMinionsKilled'] + p['neutralMinionsKilled']}** CS\n⚔️ **{p['totalDamageDealtToChampions']:,}** dégâts",
                                            "inline": True
                                        },
                                        {
                                            "name": "Statistiques supplémentaires",
                                            "value": (
                                                f"🏆 **{p['doubleKills']}** Double | **{p['tripleKills']}** Triple | **{p['quadraKills']}** Quadra | **{p['pentaKills']}** Penta\n"
                                                f"👁️ **{p['visionScore']}** Score de vision | 🛡️ **{p['totalDamageTaken']:,}** Dégâts subis"
                                            ),
                                            "inline": False
                                        }
                                    ],
                                    "footer": {
                                        "text": f"Match ID: {latest_match.split('_')[1]}",
                                        "icon_url": "https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-static-assets/global/default/images/ranked-mini-regalia/gold.png"
                                    },
                                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
                                }
                            ]
                        }

                        # Ajouter le champ LP si les infos d'avant et après sont disponibles
                        if previous_rank_info and rank_info:
                            # Récupérer les informations de rang
                            old_tier = "Fer" if previous_rank_info["tier"] == "IRON" else previous_rank_info["tier"].capitalize()
                            old_rank = previous_rank_info["rank"]
                            old_lp = previous_rank_info["lp"]
                            
                            new_tier = "Fer" if rank_info["tier"] == "IRON" else rank_info["tier"].capitalize()
                            new_rank = rank_info["rank"]
                            new_lp = rank_info["lp"]
                            
                            # Récupérer les emojis de rang
                            old_rank_emoji = RANK_EMOJIS.get(previous_rank_info["tier"], "")
                            new_rank_emoji = RANK_EMOJIS.get(rank_info["tier"], "")
                            
                            # Créer les barres de progression LP
                            lp_bar_length = 10
                            old_lp_filled = min(lp_bar_length, int(old_lp / 100 * lp_bar_length))
                            old_lp_bar = "▰" * old_lp_filled + "▱" * (lp_bar_length - old_lp_filled)
                            
                            new_lp_filled = min(lp_bar_length, int(new_lp / 100 * lp_bar_length))
                            new_lp_bar = "▰" * new_lp_filled + "▱" * (lp_bar_length - new_lp_filled)
                            
                            # Emoji pour la direction du changement
                            lp_diff = new_lp - old_lp
                            lp_emoji = "📈" if lp_diff > 0 else "📉" if lp_diff < 0 else "➖"
                            lp_sign = "+" if lp_diff > 0 else ""
                            
                            # Emoji pour la promotion/rétrogradation
                            tier_move_emoji = ""
                            if rank_info["tier"] != previous_rank_info["tier"] or rank_info["rank"] != previous_rank_info["rank"]:
                                if get_tier_value(rank_info["tier"]) > get_tier_value(previous_rank_info["tier"]) or \
                                   (rank_info["tier"] == previous_rank_info["tier"] and get_rank_value(rank_info["rank"]) > get_rank_value(previous_rank_info["rank"])):
                                    tier_move_emoji = " 🔼"
                                else:
                                    tier_move_emoji = " 🔽"

                            lp_field = {
                                "name": "📊 Évolution du rang",
                                "value": (
                                    f"{lp_emoji} **{lp_sign}{lp_diff} LP**{tier_move_emoji}\n"
                                    f"**Avant:** {old_tier} {old_rank} - {old_lp} LP {old_rank_emoji}\n{old_lp_bar}\n"
                                    f"**Après:** {new_tier} {new_rank} - {new_lp} LP {new_rank_emoji}\n{new_lp_bar}"
                                ),
                                "inline": False
                            }

                            # Insérer le champ LP en deuxième position (après le résultat)
                            embed["embeds"][0]["fields"].insert(3, lp_field)
                            
                            # Ajouter l'image du rang dans l'embed
                            tier_lowercase = rank_info["tier"].lower()
                            if tier_lowercase != "unranked":
                                embed["embeds"][0]["image"] = {
                                    "url": f"https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-static-assets/global/default/images/ranked-mini-crests/{tier_lowercase}.png"
                                }

                        # Envoyer au webhook
                        response = requests.post(WEBHOOK_URL_GAMES, json=embed)

                        if response.status_code in (200, 204):
                            print(f"Game de {riot_id} envoyée avec succès à Discord")
                        else:
                            print(f"Erreur lors de l'envoi de l'embed de partie : {response.status_code}, {response.text}")
                        
                        last_games_info[player_name] = {
                            "champion": champ,
                            "kills": kills,
                            "deaths": deaths,
                            "assists": assists,
                            "win": win,
                            "kda": kda_formatted,
                            "cs": p['totalMinionsKilled'] + p['neutralMinionsKilled'],
                            "damage": p['totalDamageDealtToChampions'],
                            "timestamp": int(time.time()),
                            "champion_icon": champion_icon_url,
                            "match_id": latest_match
                        }

                        # ✅ Exporter le classement mis à jour
                        export_ranking_data()

                        # 🔄 Mise à jour du match
                        last_matches[riot_id] = latest_match
                        break
                
                if not player_found:
                    print(f"Joueur {riot_id} non trouvé dans les participants du match")
                
            except Exception as e:
                print(f"Erreur pour {riot_id} : {e}")
        
        print("Attente avant prochaine vérification...")
        time.sleep(120)  # vérifie toutes les 60 secondes

def sync_to_github():
    """Synchronise les fichiers JSON avec le dépôt GitHub"""
    try:
        # Configuration Git pour Replit
        subprocess.run(["git", "config", "--global", "user.email", "bot@example.com"], check=True)
        subprocess.run(["git", "config", "--global", "user.name", "LOL Bot"], check=True)
        
        # Fichiers à synchroniser
        files_to_sync = ["ranking.json", "lp_history.json", "last_player_ranks.json", "web/ranking.json"]
        
        # Ajouter les fichiers modifiés
        subprocess.run(["git", "add"] + files_to_sync, check=True)
        
        # Créer un commit avec un message incluant l'horodatage
        commit_message = f"Mise à jour des données - {time.strftime('%Y-%m-%d %H:%M:%S')}"
        subprocess.run(["git", "commit", "-m", commit_message], check=False)  # Ignorer les erreurs si rien à committer
        
        # Configurer l'authentification GitHub avec un token (à définir dans les secrets Replit)
        github_token = os.getenv("GITHUB_TOKEN")
        repo_url = os.getenv("GITHUB_REPO_URL", "https://github.com/username/lol-bot-discord.git")
        if github_token:
            auth_url = repo_url.replace("https://", f"https://{github_token}@")
            subprocess.run(["git", "remote", "set-url", "origin", auth_url], check=True)
        
        # Pousser les modifications
        subprocess.run(["git", "push", "--force"], check=True)
        
        print("Synchronisation GitHub réussie")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors de la synchronisation GitHub: {e}")
        return False
    except Exception as e:
        print(f"Erreur inattendue lors de la synchronisation GitHub: {e}")
        return False

if __name__ == "__main__":
    print("Bot lancé...")

    # Initialiser les rangs des joueurs au démarrage
    print("Initialisation des rangs des joueurs...")
    update_player_ranks()
    print("Rangs initialisés")

    # Démarrer le planificateur de classement dans un thread séparé
    ranking_thread = threading.Thread(target=ranking_scheduler, daemon=True)
    ranking_thread.start()

    # Démarrer le gestionnaire de clé Riot dans un thread séparé
    riot_key_thread = threading.Thread(target=riot_key_manager, daemon=True)
    riot_key_thread.start()

    # Démarrer le suivi des joueurs dans le thread principal
    track_players()