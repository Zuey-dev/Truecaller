import http.server
import socketserver
import os

# Changer le répertoire de travail vers le dossier web
os.chdir("../web")

PORT = 8080
Handler = http.server.SimpleHTTPRequestHandler

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Serveur lancé sur http://localhost:{PORT}")
    httpd.serve_forever()