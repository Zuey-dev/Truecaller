import http.server
import socketserver
import os

# Utiliser des chemins absolus pour éviter les problèmes
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "web")

# Changer le répertoire de travail vers le dossier web
print(f"Changement de répertoire vers: {WEB_DIR}")
os.chdir(WEB_DIR)

PORT = 8080
Handler = http.server.SimpleHTTPRequestHandler

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Serveur lancé sur http://localhost:{PORT}")
    httpd.serve_forever()