"""Monitor diário de passagens (Confins, Cuiabá, Sinop e exterior).

Variáveis de ambiente:
  TELEGRAM_TOKEN / TELEGRAM_CHAT_ID  -> para receber os avisos
  MODO = normal | teste | resumo      -> teste: poucas buscas e sempre manda mensagem
                                          resumo: manda o resumo completo mesmo sem novidade
  FAKE=1                              -> usa preços simulados (sem internet)
"""
import html
import json
import os
import random
import sys
import time
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import config as C
from datas import janelas_fim_de_semana
import ignav
import milhas
from fetcher import SemVoos, link_google, link_kayak, link_maxmilhas, link_skyscanner, menor_preco
from notificar import enviar

ESTADO = Path(__file__).parent / "data" / "estado.json"
DIAS_SEM = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
BRT = timezone(timedelta(hours=-3))


def hoje() -> date:
    return datetime.now(BRT).date()


def fmt_data(d) -> str:
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return f"{DIAS_SEM[d.weekday()]} {d.day:02d}/{d.month:02d}"


def fmt_reais(v: float) -> str:
    return "R$ " + f"{v:,.0f}".replace(",", ".")


def chave(o, d, data):
    return f"{o}-{d}-{data}"


def carregar_estado():
    if ESTADO.exists():
        return json.loads(ESTADO.read_text())
    return {"cotacoes": {}, "alertas": {}, "melhor_rota": {}}


def salvar_estado(est):
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(est, ensure_ascii=False, indent=1, sort_keys=True))


# ------------------------------------------------------------------ consultas
def freq(cat):
    if cat.startswith("rt:"):
        r = next((r for r in C.IDA_E_VOLTA if r["nome"] == cat[3:]), None)
        return (r or {}).get("atualizar_dias", 5)
    return C.ATUALIZAR_A_CADA_DIAS[cat]


def datas_rota(r, h):
    """Lista de (data_ida, [datas_volta]) válidas a partir de amanhã."""
    amanha = h + timedelta(days=1)
    limite = h + timedelta(days=C.HORIZONTE_DIAS)
    if r.get("idas"):
        idas = [d for d in r["idas"] if d >= amanha]
    else:
        ini = max(r["ida_de"], amanha)
        fim = min(r["ida_ate"] or limite, limite)
        idas = [ini + timedelta(days=i) for i in range((fim - ini).days + 1)]
    pares = []
    for d in idas:
        if r.get("voltas"):
            vs = [v for v in r["voltas"] if v > d]
        else:
            vs = [d + timedelta(days=n) for n in range(r["dias_min"], r["dias_max"] + 1)]
        if vs:
            pares.append((d, vs))
    return pares


def montar_consultas():
    h = hoje()
    consultas = []
    inicio_nac = max(h + timedelta(days=1), C.NACIONAL_A_PARTIR_DE)
    janelas = janelas_fim_de_semana(
        inicio_nac, h + timedelta(days=C.HORIZONTE_DIAS),
        extras=C.FERIADOS_EXTRAS, ponte=C.CONSIDERAR_PONTE,
        volta_dia_seguinte=C.VOLTA_DIA_SEGUINTE, ida_dia_anterior=C.IDA_DIA_ANTERIOR)
    for j in janelas:
        perto = (j["ida"] - h).days <= C.DIAS_NACIONAL_PROXIMO
        cat = "nacional_proximo" if perto else "nacional_longe"
        for aeros in C.NACIONAL.values():
            for a in aeros:
                for i in j["idas"]:
                    consultas.append((C.ORIGEM, a, i.isoformat(), cat))
                for v in j["voltas"]:
                    consultas.append((a, C.ORIGEM, v.isoformat(), cat))
    for r in C.IDA_E_VOLTA:
        cat = "rt:" + r["nome"]
        voltas = set()
        for d, vs in datas_rota(r, h):
            for o in r["origem"]:
                for a in r["destino"]:
                    consultas.append((o, a, d.isoformat(), cat))
            voltas.update(vs)
        for v in voltas:
            for o in r["origem"]:
                for a in r["destino"]:
                    consultas.append((a, o, v.isoformat(), cat))
    # remove duplicadas mantendo a categoria atualizada com mais frequência
    unicas = {}
    for o, d, data, cat in consultas:
        k = chave(o, d, data)
        if k not in unicas or freq(cat) < freq(unicas[k][3]):
            unicas[k] = (o, d, data, cat)
    return list(unicas.values()), janelas


def escolher_pendentes(consultas, cotacoes, limite):
    agora = datetime.now(timezone.utc)
    pontuadas = []
    for o, d, data, cat in consultas:
        c = cotacoes.get(chave(o, d, data))
        if not c:
            idade = 999.0
        else:
            idade = (agora - datetime.fromisoformat(c["quando"])).total_seconds() / 86400
        razao = idade / freq(cat)
        if razao >= 1:
            pontuadas.append((razao, data, (o, d, data, cat)))
    pontuadas.sort(key=lambda x: (-min(x[0], 50), x[1]))
    return [p[2] for p in pontuadas[:limite]], len(pontuadas)


def executar_buscas(pendentes, cotacoes):
    ok = sem = erros = seguidos = 0
    ultimo_erro = ""
    for i, (o, d, data, _cat) in enumerate(pendentes):
        try:
            r = menor_preco(o, d, data)
            r["quando"] = datetime.now(timezone.utc).isoformat()
            cotacoes[chave(o, d, data)] = r
            ok += 1
            seguidos = 0
        except SemVoos:
            cotacoes[chave(o, d, data)] = {"preco": None, "quando": datetime.now(timezone.utc).isoformat()}
            sem += 1
            seguidos = 0
        except Exception as e:
            erros += 1
            seguidos += 1
            ultimo_erro = f"{type(e).__name__}: {e}"[:300]
            print(f"[erro] {o}->{d} {data}: {ultimo_erro}")
            if seguidos >= 12:
                print("[parando] muitos erros seguidos — possível bloqueio")
                break
        if os.environ.get("FAKE") != "1" and i < len(pendentes) - 1:
            time.sleep(random.uniform(*C.PAUSA_ENTRE_BUSCAS))
    return ok, sem, erros, ultimo_erro, seguidos >= 12


# ------------------------------------------------------------------ análise
def preco(cotacoes, o, d, data):
    c = cotacoes.get(chave(o, d, data))
    return c if c and c.get("preco") is not None else None


def analisar_nacional(janelas, cotacoes, todos=False):
    """todos=True devolve todas as janelas com preço (para o ranking por estado)."""
    achados = []
    for j in janelas:
        for cidade, aeros in C.NACIONAL.items():
            idas = [(preco(cotacoes, C.ORIGEM, a, i.isoformat()), a, i) for a in aeros for i in j["idas"]]
            idas = [x for x in idas if x[0]]
            voltas = [(preco(cotacoes, a, C.ORIGEM, v.isoformat()), a, v) for a in aeros for v in j["voltas"]]
            voltas = [x for x in voltas if x[0]]
            if not idas or not voltas:
                continue
            bi = min(idas, key=lambda x: x[0]["preco"])
            bv = min(voltas, key=lambda x: x[0]["preco"])
            if todos or (bi[0]["preco"] <= C.LIMITE_TRECHO and bv[0]["preco"] <= C.LIMITE_TRECHO):
                achados.append({
                    "id": f"N|{cidade}|{j['ida'].isoformat()}",
                    "cidade": cidade, "rotulo": j["rotulo"],
                    "ida": bi, "volta": bv,
                    "total": bi[0]["preco"] + bv[0]["preco"],
                })
    return sorted(achados, key=lambda x: x["ida"][2])


def analisar_ida_volta(cotacoes):
    res = {}
    h = hoje()
    for r in C.IDA_E_VOLTA:
        pares = datas_rota(r, h)
        combos, cobertas = [], 0
        for ida, voltas in pares:
            # melhor ida por aeroporto de destino
            idas = {}
            for o in r["origem"]:
                for a in r["destino"]:
                    p = preco(cotacoes, o, a, ida.isoformat())
                    if p and (a not in idas or p["preco"] < idas[a][0]["preco"]):
                        idas[a] = (p, o, a)
            if not idas:
                continue
            cobertas += 1
            for v in voltas:
                for a_ida, bi in idas.items():
                    vols = []
                    for a in r["destino"]:
                        if r.get("mesmo_aeroporto") and a != a_ida:
                            continue
                        for o in r["origem"]:
                            p = preco(cotacoes, a, o, v.isoformat())
                            if p:
                                vols.append((p, a, o))
                    if not vols:
                        continue
                    bv = min(vols, key=lambda x: x[0]["preco"])
                    combos.append({"ida_data": ida, "volta_data": v, "ida": bi, "volta": bv,
                                   "total": bi[0]["preco"] + bv[0]["preco"], "dias": (v - ida).days})
        combos.sort(key=lambda c: c["total"])
        vistos, top = set(), []
        for c in combos:  # no máximo 1 combinação por data de ida
            if c["ida_data"] in vistos:
                continue
            vistos.add(c["ida_data"])
            top.append(c)
            if len(top) >= C.TOP_IDA_E_VOLTA:
                break
        res[r["nome"]] = {"rota": r, "top": top,
                          "cobertura": cobertas / len(pares) if pares else 0, "vazia": not pares}
    return res


# ------------------------------------------------------------------ mensagens
def info_voo(c):
    p, o, d = c[0], c[1], c[2] if len(c) > 2 else None
    cia = html.escape(p.get("cia") or "")
    paradas = p.get("paradas")
    escala = "" if not isinstance(paradas, int) else (" direto" if paradas == 0 else f" {paradas} parada(s)")
    return f"{cia}{escala}".strip() or "cia não informada"


COMPRA = {}  # chave do trecho -> resultado da Ignav (link direto de compra)


def links_html(o, d, data):
    data = data.isoformat() if hasattr(data, "isoformat") else data
    partes = []
    c = COMPRA.get(chave(o, d, data))
    if c and c.get("url"):
        preco = fmt_reais(c["preco"]) if c.get("moeda") == "BRL" else f"{c['preco']:.0f} {c.get('moeda', '')}"
        partes.append(f"🛒 <a href=\"{html.escape(c['url'])}\">Comprar na {html.escape(c.get('loja') or 'loja')}"
                      f" ({preco})</a>")
    partes.append(f"<a href=\"{html.escape(link_google(o, d, data))}\">Google</a>")
    partes.append(f"<a href=\"{html.escape(link_kayak(o, d, data))}\">Kayak</a>")
    partes.append(f"<a href=\"{html.escape(link_skyscanner(o, d, data))}\">Sky</a>")
    partes.append(f"<a href=\"{html.escape(link_maxmilhas(o, d, data))}\">MaxMilhas</a>")
    return " · ".join(partes)


def preparar_compra(est, trechos):
    """Busca link direto (Ignav) para os trechos que vão na mensagem."""
    if not ignav.ativo() or os.environ.get("FAKE") == "1":
        return
    cache = est.setdefault("compra", {})
    agora = datetime.now(timezone.utc)
    feitos = 0
    for o, d, data in trechos:
        data = data.isoformat() if hasattr(data, "isoformat") else data
        k = chave(o, d, data)
        c = cache.get(k)
        if c and (agora - datetime.fromisoformat(c["quando"])).total_seconds() < 20 * 3600:
            COMPRA[k] = c
            continue
        if feitos >= C.IGNAV_MAX_TRECHOS:
            continue
        feitos += 1
        try:
            r = ignav.comprar(o, d, data)
        except Exception as e:
            print(f"[ignav] {k}: {type(e).__name__}: {e}")
            continue
        if r:
            cache[k] = COMPRA[k] = r
    for k in [k for k in cache if k[-10:] < hoje().isoformat()]:
        del cache[k]


def linha_trecho(rot, cot, o, d, data):
    return (f"  {rot} {fmt_data(data)} {o}→{d}: {fmt_reais(cot['preco'])} "
            f"({info_voo((cot, o, d))})\n      {links_html(o, d, data)}")


def bloco_nacional(achados):
    linhas = ["🏖️ <b>Fins de semana com os 2 trechos até "
              f"{fmt_reais(C.LIMITE_TRECHO)}</b>"]
    if len(achados) > 15:
        linhas.append(f"<i>(mostrando os 15 mais baratos de {len(achados)})</i>")
        achados = sorted(sorted(achados, key=lambda x: x["total"])[:15], key=lambda x: x["ida"][2])
    for a in achados:
        (ci, ai, di), (cv, av, dv) = a["ida"], a["volta"]
        linhas.append(f"\n📍 <b>{a['cidade']}</b> — {html.escape(a['rotulo'])} "
                      f"(total {fmt_reais(a['total'])})")
        linhas.append(linha_trecho("Ida  ", ci, C.ORIGEM, ai, di))
        linhas.append(linha_trecho("Volta", cv, av, C.ORIGEM, dv))
    return "\n".join(linhas)


def bloco_por_estado(todas):
    linhas = ["🗺️ <b>Mais baratos por estado (ida e volta somadas, fins de semana/feriados 2027)</b>"]
    for estado in C.NACIONAL:
        l = sorted([a for a in todas if a["cidade"] == estado], key=lambda x: x["total"])
        vistos, top = set(), []
        for a in l:
            if a["id"] in vistos:
                continue
            vistos.add(a["id"])
            top.append(a)
            if len(top) >= C.TOP_POR_ESTADO:
                break
        if not top:
            linhas.append(f"\n📍 <b>{estado}</b>: ainda sem dados")
            continue
        linhas.append(f"\n📍 <b>{estado}</b>")
        for a in top:
            (ci, ai, di), (cv, av, dv) = a["ida"], a["volta"]
            linhas.append(f"  • <b>{fmt_reais(a['total'])}</b> — {html.escape(a['rotulo'])}")
            linhas.append(linha_trecho("Ida  ", ci, C.ORIGEM, ai, di))
            linhas.append(linha_trecho("Volta", cv, av, C.ORIGEM, dv))
    return "\n".join(linhas)


def bloco_ida_volta(res, so=None):
    linhas = ["✈️ <b>Ida e volta — combinações mais baratas</b>"]
    for nome, r in res.items():
        if r["vazia"] or (so is not None and nome not in so):
            continue
        rota = r["rota"]
        detalhe = (f"{rota['dias_min']}–{rota['dias_max']} dias" if rota.get("dias_min") else "datas fixas")
        linhas.append(f"\n{rota.get('emoji', '🌎')} <b>{html.escape(nome)}</b> <i>({detalhe}"
                      + (f"; datas pesquisadas: {r['cobertura']:.0%}" if r["cobertura"] < 0.99 else "") + ")</i>")
        if not r["top"]:
            linhas.append("  ainda sem dados suficientes")
            continue
        for i, c in enumerate(r["top"], 1):
            (pi, oi, ai), (pv, av, ov) = c["ida"], c["volta"]
            linhas.append(
                f"  {i}. <b>{fmt_reais(c['total'])}</b> — {fmt_data(c['ida_data'])} → "
                f"{fmt_data(c['volta_data'])} ({c['dias']} dias)\n"
                f"     Ida {fmt_data(c['ida_data'])} {oi}→{ai} {fmt_reais(pi['preco'])} {info_voo(c['ida'])}\n"
                f"      {links_html(oi, ai, c['ida_data'])}\n"
                f"     Volta {fmt_data(c['volta_data'])} {av}→{ov} {fmt_reais(pv['preco'])} {info_voo(c['volta'])}\n"
                f"      {links_html(av, ov, c['volta_data'])}")
    return "\n".join(linhas)


# ------------------------------------------------------------------ main
def main():
    modo = (os.environ.get("MODO") or "normal").strip().lower()
    est = carregar_estado()
    cot = est.setdefault("cotacoes", {})
    alertas = est.setdefault("alertas", {})
    est.pop("melhor_intl", None)
    melhor_rota = est.setdefault("melhor_rota", {})

    # limpa datas que já passaram
    h = hoje().isoformat()
    for k in [k for k in cot if k[-10:] < h]:
        del cot[k]
    for k in [k for k in alertas if k.split("|")[-1] < h]:
        del alertas[k]

    consultas, janelas = montar_consultas()
    if modo == "teste":
        nac = [q for q in consultas if q[3].startswith("nacional")][:2]
        intl = sorted([q for q in consultas if q[3].startswith("rt:")], key=lambda q: q[2])[:2]
        pendentes, faltando = nac + intl, len(consultas)
    else:
        pendentes, faltando = escolher_pendentes(consultas, cot, C.BUSCAS_POR_EXECUCAO)
    print(f"{len(consultas)} consultas no total; {faltando} precisando atualizar; fazendo {len(pendentes)} agora")

    ok, sem, erros, ultimo_erro, bloqueado = executar_buscas(pendentes, cot)
    print(f"ok={ok} sem_voos={sem} erros={erros}")
    salvar_estado(est)

    nacional = analisar_nacional(janelas, cot)
    rotas = analisar_ida_volta(cot)

    import copy
    backup = copy.deepcopy({k: est.get(k) for k in ("alertas", "melhor_rota", "melhor_milhas")})
    novos_nac = []
    for a in nacional:
        ant = alertas.get(a["id"])
        if ant is None or a["total"] <= ant - C.QUEDA_MINIMA_REALERTA:
            novos_nac.append(a)
        alertas[a["id"]] = min(a["total"], ant) if ant is not None else a["total"]

    novidades = set()
    for nome, r in rotas.items():
        if r["top"]:
            t = r["top"][0]["total"]
            ant = melhor_rota.get(nome)
            if ant is None or t <= ant - C.QUEDA_MINIMA_REALERTA:
                novidades.add(nome)
            melhor_rota[nome] = t if ant is None else min(t, ant)
    salvar_estado(est)

    resumo = modo in ("teste", "resumo") or datetime.now(BRT).weekday() == 0  # segunda = resumo semanal

    # trechos que vão aparecer na mensagem -> link direto de compra
    trechos = []
    # (nacionais ficam de fora da Ignav para não gastar a cota grátis)
    for nome, r in rotas.items():
        if resumo or nome in novidades:
            for c in r["top"]:
                trechos += [(c["ida"][1], c["ida"][2], c["ida_data"]), (c["volta"][1], c["volta"][2], c["volta_data"])]
    if modo == "teste":
        trechos = [(o, d, data) for o, d, data, _ in pendentes]
    preparar_compra(est, trechos)
    salvar_estado(est)

    partes = []
    if modo == "teste":
        linhas = ["🧪 <b>Teste do monitor</b>",
                  f"Buscas feitas: {ok} com preço, {sem} sem voo, {erros} com erro."]
        for o, d, data, _ in pendentes:
            c = cot.get(chave(o, d, data))
            if c and c.get("preco") is not None:
                linhas.append(f"• {o}→{d} {fmt_data(data)}: {fmt_reais(c['preco'])} "
                              f"({info_voo((c, o, d))}, cotado em {c.get('moeda_original', '?')})\n"
                              f"   {links_html(o, d, data)}")
            elif c:
                linhas.append(f"• {o}→{d} {fmt_data(data)}: sem voos")
        if erros:
            linhas.append(f"⚠️ Último erro: <code>{html.escape(ultimo_erro)}</code>")
        else:
            linhas.append("✅ Tudo funcionando. A rodada diária vai preencher o resto nos próximos dias.")
        linhas.append("🛒 Link direto de compra (Ignav): " + (
            f"ativo ({sum(1 for k in COMPRA if COMPRA[k].get('url'))} links obtidos)" if ignav.ativo()
            else "desligado — crie o secret IGNAV_API_KEY para ativar"))
        partes.append("\n".join(linhas))
    else:
        if novos_nac:
            partes.append(bloco_nacional(novos_nac))
        if resumo:
            partes.append(bloco_por_estado(analisar_nacional(janelas, cot, todos=True)))
        if resumo:
            partes.append(bloco_ida_volta(rotas))
        elif novidades:
            partes.append("🔔 <b>Novo menor preço!</b>\n" + bloco_ida_volta(rotas, so=novidades))

    # ---- milhas (opcional: Seats.aero Pro)
    if milhas.ativo():
        try:
            pares = {r["nome"]: datas_rota(r, hoje()) for r in C.IDA_E_VOLTA}
            rm, n = milhas.analisar(C, janelas, pares)
            print(f"[milhas] {n} chamadas ao Seats.aero")
            melhor_mi = est.setdefault("melhor_milhas", {})
            novas = set()
            grupos = {"nacional": rm["nacional"], **rm["rotas"]}
            for nome, lista in grupos.items():
                for prog in milhas.PROGRAMAS:
                    l = [c for c in lista if c["prog"] == prog]
                    if not l:
                        continue
                    k, t = f"{nome}|{prog}", l[0]["total"]
                    if k not in melhor_mi or t < melhor_mi[k] * 0.97:
                        novas.add(nome)
                    melhor_mi[k] = min(t, melhor_mi.get(k, t))
            salvar_estado(est)
            if modo == "teste":
                partes.append(milhas.bloco(rm, fmt_data, n_nac=3, n_rota=1))
            elif resumo:
                partes.append(milhas.bloco(rm, fmt_data))
            elif novas:
                partes.append("🔔 <b>Novo menor preço em milhas!</b>\n" + milhas.bloco(rm, fmt_data, so=novas))
        except Exception as e:
            partes.append(f"⚠️ Busca de milhas falhou: <code>{html.escape(f'{type(e).__name__}: {e}'[:300])}</code>")
    elif modo == "teste":
        partes.append("🎟️ Milhas (Seats.aero): desligado — crie o secret SEATS_AERO_KEY para ativar")

    if bloqueado:
        partes.append("⚠️ Muitas buscas falharam seguidas hoje (o Google pode estar bloqueando). "
                      f"Último erro: <code>{html.escape(ultimo_erro)}</code>")

    if partes:
        try:
            enviar("\n\n".join(partes))
        except Exception:
            # não marca como "já avisado" se a mensagem não chegou: reenvia amanhã
            for k, v in backup.items():
                if v is None:
                    est.pop(k, None)
                else:
                    est[k] = v
            salvar_estado(est)
            raise
    else:
        print("Sem novidades hoje; nenhuma mensagem enviada.")
    if modo == "teste" and ok == 0:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        tb = traceback.format_exc()
        print(tb)
        try:
            enviar("❌ O monitor de passagens falhou hoje:\n<code>" + html.escape(tb[-1500:]) + "</code>")
        finally:
            sys.exit(1)
