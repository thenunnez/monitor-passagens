"""Passagens em milhas (Smiles e Azul Fidelidade) via Seats.aero — opcional.

Precisa de assinatura Seats.aero Pro com acesso à API e do secret SEATS_AERO_KEY.
Usa a "cached search": 1 chamada cobre um intervalo inteiro de datas, então gasta
~10 chamadas por dia (o limite do Pro é 1.000/dia).
"""
import html
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

URL = "https://seats.aero/partnerapi/search"
PROGRAMAS = {"smiles": "Smiles", "azul": "Azul Fidelidade"}
SITES = {"smiles": "https://www.smiles.com.br", "azul": "https://www.voeazul.com.br/br/pt/azul-fidelidade"}


def ativo() -> bool:
    return bool(os.environ.get("SEATS_AERO_KEY", "").strip())


def _get(params, bearer=False):
    chave = os.environ["SEATS_AERO_KEY"].strip()
    req = urllib.request.Request(
        URL + "?" + urllib.parse.urlencode(params),
        headers={"Partner-Authorization": ("Bearer " + chave) if bearer else chave,
                 "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


_USAR_BEARER = [False]


def buscar(origens, destinos, inicio: date, fim: date):
    """-> dict {(origem, destino, 'AAAA-MM-DD', programa): {milhas, cias, direto}} (econômica)."""
    params = {"origin_airport": ",".join(origens), "destination_airport": ",".join(destinos),
              "start_date": inicio.isoformat(), "end_date": fim.isoformat(),
              "sources": ",".join(PROGRAMAS), "order_by": "lowest_mileage", "take": 1000}
    res, paginas = {}, 0
    while True:
        try:
            dados = _get(params, _USAR_BEARER[0])
        except urllib.error.HTTPError as e:
            if e.code == 401 and not _USAR_BEARER[0]:
                _USAR_BEARER[0] = True
                continue
            raise
        for it in dados.get("data") or []:
            if not it.get("YAvailable"):
                continue
            try:
                milhas = int(float(str(it.get("YMileageCost") or "0").replace(",", "")))
            except ValueError:
                continue
            if milhas <= 0:
                continue
            rota = it.get("Route") or {}
            fonte = (it.get("Source") or rota.get("Source") or "").lower()
            dia = str(it.get("Date") or "")[:10]
            k = (rota.get("OriginAirport"), rota.get("DestinationAirport"), dia, fonte)
            if k not in res or milhas < res[k]["milhas"]:
                res[k] = {"milhas": milhas, "cias": it.get("YAirlines") or "",
                          "direto": bool(it.get("YDirect"))}
        paginas += 1
        if not dados.get("hasMore") or not dados.get("cursor") or paginas >= 5:
            break
        params["cursor"] = dados["cursor"]
    return res


def fmt_milhas(m: int) -> str:
    return f"{m:,}".replace(",", ".") + " mi"


def _dt(s):
    return date.fromisoformat(s) if isinstance(s, str) else s


def _melhor(tab, origens, destinos, dia, prog):
    c = [(v, o, d) for o in origens for d in destinos
         if (v := tab.get((o, d, dia, prog)))]
    return min(c, key=lambda x: x[0]["milhas"]) if c else None


def analisar(C, janelas, pares_por_rota):
    """Busca e monta as melhores combinações em milhas. Retorna (resultado, n_chamadas)."""
    tab, chamadas = {}, 0
    hoje = date.today()
    # nacional
    aeros_nac = [a for v in C.NACIONAL.values() for a in v]
    if janelas:
        ini = janelas[0]["ida"]
        fim = max(v for j in janelas for v in j["voltas"])
        tab.update(buscar([C.ORIGEM], aeros_nac, ini, fim))
        tab.update(buscar(aeros_nac, [C.ORIGEM], ini, fim))
        chamadas += 2
    # ida e volta
    for r in C.IDA_E_VOLTA:
        pares = pares_por_rota.get(r["nome"]) or []
        if not pares:
            continue
        i0, i1 = pares[0][0], pares[-1][0]
        v0 = min(v for _, vs in pares for v in vs)
        v1 = max(v for _, vs in pares for v in vs)
        tab.update(buscar(r["origem"], r["destino"], i0, i1))
        tab.update(buscar(r["destino"], r["origem"], v0, v1))
        chamadas += 2

    res = {"nacional": [], "rotas": {}}
    for prog in PROGRAMAS:
        for j in janelas:
            for cidade, aeros in C.NACIONAL.items():
                bi = _melhor(tab, [C.ORIGEM], aeros, j["ida"].isoformat(), prog)
                bvs = [(b, v) for v in j["voltas"] if (b := _melhor(tab, aeros, [C.ORIGEM], v.isoformat(), prog))]
                if bi and bvs:
                    bv, vd = min(bvs, key=lambda x: x[0][0]["milhas"])
                    res["nacional"].append({"prog": prog, "cidade": cidade, "rotulo": j["rotulo"],
                                            "ida_data": j["ida"], "volta_data": vd, "ida": bi, "volta": bv,
                                            "total": bi[0]["milhas"] + bv[0]["milhas"]})
        for r in C.IDA_E_VOLTA:
            for ida, voltas in pares_por_rota.get(r["nome"]) or []:
                bi = _melhor(tab, r["origem"], r["destino"], ida.isoformat(), prog)
                if not bi:
                    continue
                destinos_volta = [bi[2]] if r.get("mesmo_aeroporto") else r["destino"]
                for v in voltas:
                    bv = _melhor(tab, destinos_volta, r["origem"], v.isoformat(), prog)
                    if bv:
                        res["rotas"].setdefault(r["nome"], []).append(
                            {"prog": prog, "ida_data": ida, "volta_data": v, "ida": bi, "volta": bv,
                             "total": bi[0]["milhas"] + bv[0]["milhas"], "dias": (v - ida).days})
    res["nacional"].sort(key=lambda x: x["total"])
    for nome in res["rotas"]:
        res["rotas"][nome].sort(key=lambda x: x["total"])
    return res, chamadas


def _top_por_ida(lista, n):
    vistos, top = set(), []
    for c in lista:
        k = (c["prog"], c["ida_data"], c.get("cidade"))
        if k in vistos:
            continue
        vistos.add(k)
        top.append(c)
        if len(top) >= n:
            break
    return top


def bloco(res, fmt_data, so=None, n_nac=8, n_rota=3):
    linhas = ["🎟️ <b>Milhas — Smiles e Azul Fidelidade (econômica, sem taxas)</b>"]
    nac = _top_por_ida(res["nacional"], n_nac) if so is None or "nacional" in so else []
    if nac:
        linhas.append("\n🏖️ <b>Fins de semana/feriados 2027</b>")
        for c in nac:
            (pi, oi, ai), (pv, av, ov) = c["ida"], c["volta"]
            linhas.append(
                f"  • <b>{fmt_milhas(c['total'])}</b> {PROGRAMAS[c['prog']]} — {c['cidade']}, "
                f"{fmt_data(c['ida_data'])} → {fmt_data(c['volta_data'])} ({html.escape(c['rotulo'])})\n"
                f"     ida {oi}→{ai} {fmt_milhas(pi['milhas'])}{' direto' if pi['direto'] else ''} · "
                f"volta {av}→{ov} {fmt_milhas(pv['milhas'])}{' direto' if pv['direto'] else ''} · "
                f"<a href=\"{SITES[c['prog']]}\">emitir</a>")
    for nome, lista in res["rotas"].items():
        if so is not None and nome not in so:
            continue
        linhas.append(f"\n✈️ <b>{html.escape(nome)}</b>")
        for c in _top_por_ida(lista, n_rota):
            (pi, oi, ai), (pv, av, ov) = c["ida"], c["volta"]
            linhas.append(
                f"  • <b>{fmt_milhas(c['total'])}</b> {PROGRAMAS[c['prog']]} — "
                f"{fmt_data(c['ida_data'])} → {fmt_data(c['volta_data'])} ({c['dias']} dias)\n"
                f"     ida {oi}→{ai} {fmt_milhas(pi['milhas'])} · volta {av}→{ov} {fmt_milhas(pv['milhas'])} · "
                f"<a href=\"{SITES[c['prog']]}\">emitir</a>")
    if len(linhas) == 1:
        linhas.append("  nenhuma disponibilidade encontrada nas datas monitoradas")
    return "\n".join(linhas)
