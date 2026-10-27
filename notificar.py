"""Envio de mensagens pelo Telegram (robusto a limites de tamanho/formatação)."""
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

LIMITE_VISIVEL = 3000      # Telegram: 4096 caracteres por mensagem
LIMITE_BRUTO = 4000        # tamanho do HTML enviado (com os links), por segurança
LIMITE_FORMATACOES = 60    # Telegram: até 100 links/negritos por mensagem

_ERROS_HTML = []


def _visivel(t):
    return len(html.unescape(re.sub(r"<[^>]+>", "", t)).encode("utf-16-le")) // 2


def _formatacoes(t):
    return len(re.findall(r"<(a|b|i|code)[\s>]", t))


def _dividir(linhas, cabe):
    partes, atual = [], []
    for linha in linhas:
        if atual and not cabe(atual + [linha]):
            partes.append(atual)
            atual = []
        atual.append(linha)
    if atual:
        partes.append(atual)
    return ["\n".join(p) for p in partes if "\n".join(p).strip()]


def _cabe_html(ls):
    t = "\n".join(ls)
    return _visivel(t) <= LIMITE_VISIVEL and len(t) <= LIMITE_BRUTO and _formatacoes(t) <= LIMITE_FORMATACOES


def _cabe_texto(ls):
    return _visivel("\n".join(ls)) <= LIMITE_VISIVEL


def _para_texto(t):
    t = re.sub(r'<a href="([^"]*)">([^<]*)</a>', r"\2: \1", t)
    return html.unescape(re.sub(r"<[^>]+>", "", t))


def _mandar(token, chat, texto, html_mode):
    time.sleep(1.2)  # Telegram: no máx. ~1 mensagem por segundo no mesmo chat
    campos = {"chat_id": chat, "text": texto, "disable_web_page_preview": "true"}
    if html_mode:
        campos["parse_mode"] = "HTML"
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                 data=urllib.parse.urlencode(campos).encode())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", "replace")
        try:
            desc = json.loads(corpo).get("description", corpo)
        except ValueError:
            desc = corpo
        raise RuntimeError(f"{e.code} {desc}"[:300]) from e
    if not resp.get("ok"):
        raise RuntimeError(f"Telegram recusou a mensagem: {resp}")


def _enviar_html(token, chat, texto):
    """Tenta em HTML; se recusar, divide ao meio e tenta de novo; no fim, texto simples."""
    erro = ""
    if not _ERROS_HTML or "too long" in _ERROS_HTML[-1]:
        try:
            _mandar(token, chat, texto, html_mode=True)
            return
        except RuntimeError as e:
            print(f"[telegram] HTML recusado: {e}")
            _ERROS_HTML.append(str(e))
            erro = str(e)
    linhas = texto.split("\n")
    if "too long" in erro and len(linhas) > 3:
        meio = len(linhas) // 2
        for pedaco in ("\n".join(linhas[:meio]), "\n".join(linhas[meio:])):
            if pedaco.strip():
                _enviar_html(token, chat, pedaco)
        return
    for p in _dividir(_para_texto(texto).split("\n"), _cabe_texto):
        _mandar(token, chat, p, html_mode=False)


def enviar(texto):
    """texto: uma string ou uma lista (cada item vira uma mensagem separada)."""
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        print("---- (Telegram não configurado; mensagem abaixo) ----")
        print("\n\n=====\n\n".join(texto) if isinstance(texto, list) else texto)
        return False
    _ERROS_HTML.clear()
    mensagens = texto if isinstance(texto, list) else [texto]
    for msg in mensagens:
        for p in _dividir(msg.split("\n"), _cabe_html):
            _enviar_html(token, chat, p)
    if _ERROS_HTML:
        _mandar(token, chat, "ℹ️ Aviso técnico (para o ajuste do monitor): o Telegram recusou parte da "
                "formatação — " + _ERROS_HTML[0], html_mode=False)
    return True
