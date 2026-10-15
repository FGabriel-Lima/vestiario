"""python -m vestiario: sobe o servidor local e abre o navegador. Se ele já estiver aberto, só abre o navegador."""
import socket
import threading
import webbrowser

import uvicorn

from .api import app

URL_HOST, PORTA = "127.0.0.1", 8765
URL = f"http://{URL_HOST}:{PORTA}"

with socket.socket() as s:
    ja_aberto = s.connect_ex((URL_HOST, PORTA)) == 0

if ja_aberto:
    webbrowser.open(URL)
else:
    threading.Timer(1.5, webbrowser.open, [URL]).start()
    uvicorn.run(app, host=URL_HOST, port=PORTA)
