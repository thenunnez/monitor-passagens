"""Envio de mensagens pelo Telegram."""
import html
import json
import os
import re
import urllib.parse
import urllib.request


def enviar(texto: str):
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        print("---- (Telegram não configurado; mensagem abaixo) ----")
        print(texto)
        return False
    def visivel(t):  # o limite do Telegram (4096) conta o texto sem as tags
        return len(html.unescape(re.sub(r"<[^>]+>", "", t)))

    partes, atual, tam = [], "", 0
    for linha in texto.split("\n"):
        v = visivel(linha) + 1
        if atual and (tam + v > 3500 or len(atual) + len(linha) > 60000):
            partes.append(atual)
            atual, tam = "", 0
        atual += linha + "\n"
        tam += v
    if atual.strip():
        partes.append(atual)
    for p in partes:
        dados = urllib.parse.urlencode({
            "chat_id": chat, "text": p, "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=dados)
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.load(r)
            if not resp.get("ok"):
                raise RuntimeError(f"Telegram recusou a mensagem: {resp}")
    return True
