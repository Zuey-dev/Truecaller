import http.server
import socketserver
import os
import json
from http import HTTPStatus

# Utiliser des chemins absolus pour éviter les problèmes
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "web")

# Classe personnalisée pour gérer les requêtes API
class APIHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # Gérer les requêtes API
        if self.path == '/api/ranking':
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')  # CORS
            self.end_headers()
            
            try:
                with open(os.path.join(os.path.dirname(WEB_DIR), 'ranking.json'), 'rb') as f:
                    self.wfile.write(f.read())
            except Exception as e:
                self.wfile.write(json.dumps({"error": str(e)}).encode())
            return
        
        # Gérer les requêtes de fichiers statiques
        return super().do_GET()

# Changer le répertoire de travail vers le dossier web
print(f"Changement de répertoire vers: {WEB_DIR}")
os.chdir(WEB_DIR)

PORT = 8080
Handler = APIHandler

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Serveur démarré sur le port {PORT}")
    httpd.serve_forever()