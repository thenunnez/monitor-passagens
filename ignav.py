"""Link direto de compra via Ignav (opcional; só funciona com IGNAV_API_KEY).

Para cada trecho que vai aparecer na mensagem, busca o voo mais barato no
mercado brasileiro (preço em R$) e pede o link de compra (companhia ou agência).
"""
import json
import os
import urllib.request
from datetime import datetime, timezone

API = "https://ignav.com/api/fares"


def ativo() -> bool:
    return bool(os.environ.get("IGNAV_API_KEY", "").strip())


def _post(caminho, corpo):
    req = urllib.request.Request(
        f"{API}/{caminho}", data=json.dumps(corpo).encode(),
        headers={"X-Api-Key": os.environ["IGNAV_API_KEY"].strip(),
                 "Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _url(u: str) -> str:
    u = (u or "").strip()
    return u if u.startswith("http") else "https://" + u


def comprar(origem: str, destino: str, data: str):
    """-> {preco, moeda, cia, saida, url, loja, tipo} ou None."""
    busca = _post("one-way", {"origin": origem, "destination": destino,
                              "departure_date": data, "adults": 1, "market": "BR"})
    its = [i for i in busca.get("itineraries") or [] if (i.get("price") or {}).get("amount") is not None]
    if not its:
        return None
    melhor = min(its, key=lambda i: i["price"]["amount"])
    out = melhor.get("outbound") or {}
    segs = out.get("segments") or [{}]
    res = {"preco": float(melhor["price"]["amount"]), "moeda": melhor["price"].get("currency", ""),
           "cia": out.get("carrier", ""), "saida": (segs[0].get("departure_time_local") or "")[11:16],
           "url": None, "loja": None, "tipo": None,
           "quando": datetime.now(timezone.utc).isoformat()}
    if melhor.get("ignav_id"):
        bl = _post("booking-links", {"ignav_id": melhor["ignav_id"]})
        links = [l for op in bl.get("booking_options") or [] for l in op.get("links") or [] if l.get("url")]
        # prefere comprar direto na companhia; depois o mais barato
        links.sort(key=lambda l: (l.get("provider_type") != "airline",
                                  (l.get("price") or {}).get("amount") or 1e9))
        if links:
            l = links[0]
            res.update(url=_url(l["url"]), loja=l.get("provider_name"), tipo=l.get("provider_type"))
            if (l.get("price") or {}).get("amount") is not None:
                res["preco"] = float(l["price"]["amount"])
                res["moeda"] = l["price"].get("currency", res["moeda"])
    return res
