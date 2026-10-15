import http.server
import socketserver
import webbrowser
import os

PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def do_GET(self):
        if self.path == '/' or self.path == '/heart':
            self.path = '/cardiomate.html'
        return super().do_GET()

print(f"Server root directory: {BASE_DIR}")
print(f"Starting Python Interactive Heart App at http://127.0.0.1:{PORT}")
webbrowser.open(f"http://127.0.0.1:{PORT}")

with socketserver.TCPServer(("", PORT), CustomHandler) as httpd:
    httpd.serve_forever()