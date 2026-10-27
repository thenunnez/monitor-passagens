"""Envio de mensagens pelo Telegram."""
import json
import os
import urllib.parse
import urllib.request


def enviar(texto: str):
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        print("---- (Telegram não configurado; mensagem abaixo) ----")
        print(texto)
        return False
    partes, atual = [], ""
    for linha in texto.split("\n"):
        if len(atual) + len(linha) + 1 > 3800:
            partes.append(atual)
            atual = ""
        atual += linha + "\n"
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
