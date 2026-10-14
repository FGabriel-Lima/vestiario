"""python -m vestiario: sobe o servidor local e abre o navegador."""
import threading
import webbrowser

import uvicorn

from .api import app

URL_HOST, PORTA = "127.0.0.1", 8765

threading.Timer(1.5, webbrowser.open, [f"http://{URL_HOST}:{PORTA}"]).start()
uvicorn.run(app, host=URL_HOST, port=PORTA)
