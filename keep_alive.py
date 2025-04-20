from flask import Flask, send_from_directory
import threading
import os

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

@app.route('/api/ranking')
def ranking_api():
    # Retourner le fichier ranking.json pour les requêtes API
    try:
        with open('ranking.json', 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/web/<path:path>')
def serve_web(path):
    # Servir les fichiers statiques du dossier web
    return send_from_directory('web', path)

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = threading.Thread(target=run)
    t.daemon = True
    t.start()