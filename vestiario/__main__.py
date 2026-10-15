"""python -m vestiario [--rede]: sobe o servidor local e abre o navegador. Se ele já estiver aberto, só abre o
navegador. Com --rede, o servidor também atende o celular: pelo Tailscale, ou direto quando o PC está no roteador
do celular (aí o celular é o gateway da rede, e só ele é liberado, além do PC), ou na rede de casa, se ela estiver
marcada como Privada no Windows (decisão do usuário). Numa rede Pública (o eduroam), a API recusa o resto da rede."""
import ipaddress
import re
import subprocess
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


def rota_padrao() -> tuple[str, str] | None:
    """(IP do PC, gateway) da rota padrão do Windows. No roteador do celular, o gateway é o próprio celular."""
    try:
        saida = subprocess.run(["route", "print", "-4", "0.0.0.0"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    ip = r"(\d+\.\d+\.\d+\.\d+)"
    m = re.search(rf"^\s*0\.0\.0\.0\s+0\.0\.0\.0\s+{ip}\s+{ip}", saida, re.M)
    return (m.group(2), m.group(1)) if m else None


def rede_privada() -> str | None:
    """A sub-rede da conexão com a internet, se o Windows a marca como Privada (ex.: "192.168.0.0/24")."""
    comando = ("$p = Get-NetConnectionProfile | Where-Object IPv4Connectivity -eq 'Internet' | Select-Object -First 1; "
               "if ($p.NetworkCategory -eq 'Private') { $i = Get-NetIPAddress -InterfaceIndex $p.InterfaceIndex "
               "-AddressFamily IPv4 | Select-Object -First 1; \"$($i.IPAddress)/$($i.PrefixLength)\" }")
    try:
        saida = subprocess.run(["powershell", "-NoProfile", "-Command", comando], capture_output=True, text=True,
                               timeout=20).stdout.strip()
        return str(ipaddress.ip_interface(saida).network) if saida else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


with socket.socket() as s:
    ja_aberto = s.connect_ex((URL_HOST, PORTA)) == 0

if ja_aberto:
    webbrowser.open(URL)
else:
    host = URL_HOST
    if "--rede" in sys.argv:
        host = "0.0.0.0"
        if ip := ip_no_tailscale():
            os.environ["VESTIARIO_REDE_URL"] = f"http://{ip}:{PORTA}"
        if rota := rota_padrao():
            # ponytail: só o gateway entra; num Wi-Fi de casa o celular não é o gateway e precisa do Tailscale
            os.environ["VESTIARIO_REDE_IPS"] = ",".join(rota)
            os.environ.setdefault("VESTIARIO_REDE_URL", f"http://{rota[0]}:{PORTA}")
        if subrede := rede_privada():
            os.environ["VESTIARIO_REDE_PRIVADA"] = subrede
        print(f"No celular: {os.environ.get('VESTIARIO_REDE_URL', 'sem rede')}")
    threading.Timer(1.5, webbrowser.open, [URL]).start()
    uvicorn.run(app, host=host, port=PORTA)
