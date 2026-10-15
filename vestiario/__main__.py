"""python -m vestiario [--rede]: sobe o servidor local e abre o navegador. Se ele já estiver aberto, só abre o
navegador. Com --rede, o servidor também atende o celular pelo Tailscale (a API só aceita o PC e os IPs do Tailscale)."""
import ipaddress
import os
import socket
import sys
import threading
import webbrowser

import uvicorn

from .api import app

URL_HOST, PORTA = "127.0.0.1", 8765
URL = f"http://{URL_HOST}:{PORTA}"


def ip_no_tailscale() -> str | None:
    """IP do PC na rede do Tailscale (100.64.0.0/10), se o Tailscale estiver ligado."""
    ips = {i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    return next((ip for ip in sorted(ips) if ipaddress.ip_address(ip) in ipaddress.ip_network("100.64.0.0/10")), None)


with socket.socket() as s:
    ja_aberto = s.connect_ex((URL_HOST, PORTA)) == 0

if ja_aberto:
    webbrowser.open(URL)
else:
    host = URL_HOST
    if "--rede" in sys.argv:
        if ip := ip_no_tailscale():
            host = "0.0.0.0"
            os.environ["VESTIARIO_REDE_URL"] = f"http://{ip}:{PORTA}"
            print(f"No celular, com o Tailscale ligado: http://{ip}:{PORTA}")
        else:
            print("Tailscale desligado: o Vestiário abre só neste PC.")
    threading.Timer(1.5, webbrowser.open, [URL]).start()
    uvicorn.run(app, host=host, port=PORTA)
