"""Envio de mensagens pelo Telegram."""
import html
import json
import os
import re
import urllib.error
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
        try:
            _mandar(token, chat, p, html_mode=True)
        except urllib.error.HTTPError as e:
            detalhe = e.read().decode("utf-8", "replace")[:300]
            print(f"[telegram] HTML recusado ({e.code}): {detalhe} — reenviando como texto simples")
            simples = html.unescape(re.sub(r"<[^>]+>", "", p))
            _mandar(token, chat, simples, html_mode=False)
    return True


def _mandar(token, chat, texto, html_mode):
    campos = {"chat_id": chat, "text": texto, "disable_web_page_preview": "true"}
    if html_mode:
        campos["parse_mode"] = "HTML"
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                 data=urllib.parse.urlencode(campos).encode())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        if not html_mode:
            raise RuntimeError(f"Telegram recusou: {e.code} {e.read().decode('utf-8', 'replace')[:300]}") from e
        raise
    if not resp.get("ok"):
        raise RuntimeError(f"Telegram recusou a mensagem: {resp}")
