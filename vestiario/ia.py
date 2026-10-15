"""Único ponto do Vestiário que fala com a IA (Gemini). Recebe fatos prontos e devolve JSON validado pelo esquema."""
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

# Só Flash ou abaixo: o plano do usuário (Plus) não dá acesso aos modelos Pro. São aliases estáveis do Google (apontam
# para a versão mais nova); se o Flash estiver sobrecarregado (503) ou sem cota (429), vai o Flash-Lite.
MODELOS = ("gemini-flash-latest", "gemini-flash-lite-latest")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"


class IAIndisponivel(Exception):
    """Mensagem pronta para mostrar ao usuário."""


def chave() -> str:
    if k := os.environ.get("VESTIARIO_GEMINI_KEY"):
        return k.strip()
    arq = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Vestiario" / "gemini.key"
    if arq.is_file() and (k := arq.read_text(encoding="utf8").strip()):
        return k
    raise IAIndisponivel(f"Chave do Gemini não configurada. Defina VESTIARIO_GEMINI_KEY ou crie {arq}.")


def responder(sistema: str, fatos: dict, esquema: dict) -> dict:
    """Manda as instruções e os fatos (em JSON) e devolve a resposta no formato do esquema."""
    corpo = json.dumps({
        "systemInstruction": {"parts": [{"text": sistema}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(fatos, ensure_ascii=False)}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": esquema},
    }).encode()
    k = chave()
    for i, modelo in enumerate(MODELOS):
        req = urllib.request.Request(URL.format(modelo), data=corpo,
                                     headers={"x-goog-api-key": k, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                resposta = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and i + 1 < len(MODELOS):  # sobrecarga ou cota: tenta o próximo modelo
                time.sleep(1)
                continue
            if e.code in (429, 503):
                raise IAIndisponivel("O Gemini está sobrecarregado agora. Tente de novo em alguns minutos.") from e
            raise IAIndisponivel(f"O Gemini recusou o pedido (erro {e.code}).") from e
        except TimeoutError as e:  # resposta longa demais (muitos posts) ou servidor lento: tenta o próximo modelo
            if i + 1 < len(MODELOS):
                continue
            raise IAIndisponivel("O Gemini demorou demais para responder. Tente de novo em instantes.") from e
        except urllib.error.URLError as e:
            if isinstance(e.reason, TimeoutError) and i + 1 < len(MODELOS):
                continue
            raise IAIndisponivel("Sem conexão com o Gemini. Confira a internet e tente de novo.") from e
    try:
        return json.loads(resposta["candidates"][0]["content"]["parts"][0]["text"])
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise IAIndisponivel("O Gemini devolveu uma resposta vazia. Tente de novo.") from e
