import json
import os
import requests
import time
import datetime
import threading
from dotenv import load_dotenv

STATE_FILE = "ranking_state.json"

load_dotenv(dotenv_path=".\config.env")  # charger le fichier .env

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
    
    # Construire les données à exporter
    export_data = {
        "updated_at": datetime.datetime.now().isoformat(),
        "players": []
    }
    
    for i, (player_name, rank_info) in enumerate(sorted_players):
        # Charger les infos de la winstreak si disponible
        puuid = None
        for riot_id in SUMMONERS:
            if riot_id.split("#")[0] == player_name:
                puuid = get_puuid_by_riot_id(riot_id)
                break
                
        streak = get_win_streak(puuid) if puuid else 0
        
        tier_display = "Fer" if rank_info["tier"] == "IRON" else rank_info["tier"].capitalize()
        rank_display = "Non classé" if rank_info["tier"] == "UNRANKED" else f"{tier_display} {rank_info['rank']}"
        
        player_data = {
            "name": player_name,
            "rank": rank_display,
            "tier": rank_info["tier"],
            "division": rank_info["rank"],
            "lp": rank_info["lp"],
            "win_streak": streak,
            "position": i + 1  # Classement (1er, 2ème, etc.)
        }
        
        export_data["players"].append(player_data)
    
    # Sauvegarder dans le dossier web
    try:
        with open("../web/ranking.json", "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        print("Données de classement exportées pour l'interface web")
        return True
    except Exception as e:
        print(f"Erreur lors de l'exportation des données: {e}")
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

def send_ranking():
    """Envoyer ou mettre à jour le classement via embed Discord + historique"""
    global last_ranking_sent

    update_player_ranks()

    if not player_ranks:
        print("Aucun rang disponible, impossible d'envoyer le classement")
        return

    export_ranking_data()

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

    # Embed principal (classement)
    embed_main = {
        "title": "📊 Classement des joueurs",
        "description": f"Mis à jour : <t:{unix_timestamp}:R>",
        "color": 0x00ffae,
        "fields": [],
        "footer": {
            "text": f"Mise à jour du {now.strftime('%d/%m/%Y à %H:%M:%S')}"
        }
    }

    for i, (player_name, rank_info) in enumerate(sorted_players):
        medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "🏅"
        tier_display = "Fer" if rank_info["tier"] == "IRON" else rank_info["tier"].capitalize()
        emoji = RANK_EMOJIS.get(rank_info["tier"], "")
        value = "Non classé" if rank_info["tier"] == "UNRANKED" else f"{tier_display} {rank_info['rank']} - {rank_info['lp']} LP"

        embed_main["fields"].append({
            "name": f"{medal} {player_name}",
            "value": f"{emoji} {value}",
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
        "title": "📈 Historique des progressions",
        "color": 0x7289da,
        "fields": [],
        "footer": {
            "text": "Comparaison depuis la dernière mise à jour"
        }
    }

    for player_name, rank_info in player_ranks.items():
        previous = previous_ranks.get(player_name)
        if not previous:
            continue

        lp_diff = rank_info["lp"] - previous["lp"]
        rank_changed = rank_info["rank"] != previous["rank"] or rank_info["tier"] != previous["tier"]

        lp_color = "🟢" if lp_diff > 0 else "🔴" if lp_diff < 0 else "⚪"
        lp_sign = "+" if lp_diff > 0 else ""
        change_msg = f"{lp_color} {lp_sign}{lp_diff} LP"

        if rank_changed:
            change_msg += f"\n🔼 {previous['tier'].capitalize()} {previous['rank']} → {rank_info['tier'].capitalize()} {rank_info['rank']}"

        embed_history["fields"].append({
            "name": player_name,
            "value": change_msg,
            "inline": False
        })

    data = {"embeds": [embed_main, embed_history]}
    response = requests.post(WEBHOOK_URL_RANKING, json=data)

    if response.status_code in (200, 204):
        print("Classement envoyé avec historique")
        if response.status_code == 200:
            message_id = response.json()["id"]

        save_ranking_state(message_id, now)
        last_ranking_sent = now

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
                                    "title": f"{player_name} a terminé une partie !",
                                    "color": 0xFF4C4C if not win else 0x57F287,  # Rouge si défaite, vert si win
                                    "thumbnail": {"url": champion_icon_url},
                                    "fields": [
                                        {"name": "Résultat", "value": "✅ **Victoire**" if win else "❌ **Défaite**", "inline": True},
                                        {"name": "Champion", "value": champ, "inline": True},
                                        {"name": "KDA / CS", "value": f"{kills}/{deaths}/{assists} ({kda_formatted}) — {p['totalMinionsKilled'] + p['neutralMinionsKilled']} CS <:minion:1363261808538026166>", "inline": False},
                                        {"name": "Streak 🔥", "value": streak_text, "inline": False},  # Ajout de la streak
                                        {"name": "Dégâts infligés", "value": f"{p['totalDamageDealtToChampions']:,} ⚔️", "inline": True},
                                    ],
                                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
                                }
                            ]
                        }

                        # Ajouter le champ LP si les infos d'avant et après sont disponibles
                        if previous_rank_info and rank_info:
                            old_tier = previous_rank_info["tier"].capitalize().replace("Unranked", "Non classé")
                            old_rank = previous_rank_info["rank"]
                            old_lp = previous_rank_info["lp"]

                            new_tier = rank_info["tier"].capitalize().replace("Unranked", "Non classé")
                            new_rank = rank_info["rank"]
                            new_lp = rank_info["lp"]

                            lp_diff = new_lp - old_lp
                            lp_sign = "+" if lp_diff >= 0 else ""
                            lp_emoji = "📈" if lp_diff > 0 else "📉" if lp_diff < 0 else "➖"

                            tier_changed = old_tier != new_tier
                            rank_changed = old_rank != new_rank
                            tier_move_emoji = ""

                            if tier_changed or rank_changed:
                                if get_tier_value(rank_info["tier"]) > get_tier_value(previous_rank_info["tier"]) or \
                                   (rank_info["tier"] == previous_rank_info["tier"] and get_rank_value(rank_info["rank"]) > get_rank_value(previous_rank_info["rank"])):
                                    tier_move_emoji = " 🆙"
                                elif get_tier_value(rank_info["tier"]) < get_tier_value(previous_rank_info["tier"]) or \
                                     (rank_info["tier"] == previous_rank_info["tier"] and get_rank_value(rank_info["rank"]) < get_rank_value(previous_rank_info["rank"])):
                                    tier_move_emoji = " 🪂"

                            lp_field = {
                                "name": "Évolution LP 📊",
                                "value": f"{lp_emoji} {lp_sign}{lp_diff} LP\n{old_tier} {old_rank} {old_lp} LP → {new_tier} {new_rank} {new_lp} LP{tier_move_emoji}",
                                "inline": False
                            }


                            embed["embeds"][0]["fields"].append(lp_field)

                        # Envoyer au webhook
                        response = requests.post(WEBHOOK_URL_GAMES, json=embed)

                        if response.status_code in (200, 204):
                            print(f"Game de {riot_id} envoyée avec succès à Discord")
                        else:
                            print(f"Erreur lors de l'envoi de l'embed de partie : {response.status_code}, {response.text}")
                        
                        # Mettre à jour le dernier match
                        last_matches[riot_id] = latest_match
                        break
                
                if not player_found:
                    print(f"Joueur {riot_id} non trouvé dans les participants du match")
                
            except Exception as e:
                print(f"Erreur pour {riot_id} : {e}")
        
        print("Attente avant prochaine vérification...")
        time.sleep(120)  # vérifie toutes les 60 secondes


if __name__ == "__main__":
    print("Bot lancé...")
    
    # Initialiser les rangs des joueurs au démarrage
    print("Initialisation des rangs des joueurs...")
    update_player_ranks()
    print("Rangs initialisés")
    
    # Démarrer le planificateur de classement dans un thread séparé
    ranking_thread = threading.Thread(target=ranking_scheduler, daemon=True)
    ranking_thread.start()
    
    # Démarrer le suivi des joueurs dans le thread principal
    track_players()