"""Monitor diário de passagens saindo de Confins.

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
from fetcher import SemVoos, link_google, menor_preco
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
    return {"cotacoes": {}, "alertas": {}, "melhor_intl": {}}


def salvar_estado(est):
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(est, ensure_ascii=False, indent=1, sort_keys=True))


# ------------------------------------------------------------------ consultas
def montar_consultas():
    h = hoje()
    consultas = []
    janelas = janelas_fim_de_semana(
        h + timedelta(days=1), h + timedelta(days=C.HORIZONTE_DIAS),
        extras=C.FERIADOS_EXTRAS, ponte=C.CONSIDERAR_PONTE,
        volta_dia_seguinte=C.VOLTA_DIA_SEGUINTE)
    for j in janelas:
        perto = (j["ida"] - h).days <= C.DIAS_NACIONAL_PROXIMO
        cat = "nacional_proximo" if perto else "nacional_longe"
        for aeros in C.NACIONAL.values():
            for a in aeros:
                consultas.append((C.ORIGEM, a, j["ida"].isoformat(), cat))
                for v in j["voltas"]:
                    consultas.append((a, C.ORIGEM, v.isoformat(), cat))
    ida = max(C.IDA_DE, h + timedelta(days=1))
    while ida <= C.IDA_ATE:
        for aeros in C.INTERNACIONAL.values():
            for a in aeros:
                consultas.append((C.ORIGEM, a, ida.isoformat(), "internacional"))
        ida += timedelta(days=1)
    volta = max(C.IDA_DE, h + timedelta(days=1)) + timedelta(days=C.DIAS_VIAGEM_MIN)
    while volta <= C.IDA_ATE + timedelta(days=C.DIAS_VIAGEM_MAX):
        for aeros in C.INTERNACIONAL.values():
            for a in aeros:
                consultas.append((a, C.ORIGEM, volta.isoformat(), "internacional"))
        volta += timedelta(days=1)
    # remove duplicadas mantendo a categoria mais urgente
    prio = {"nacional_proximo": 0, "nacional_longe": 1, "internacional": 2}
    unicas = {}
    for o, d, data, cat in consultas:
        k = chave(o, d, data)
        if k not in unicas or prio[cat] < prio[unicas[k][3]]:
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
        razao = idade / C.ATUALIZAR_A_CADA_DIAS[cat]
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


def analisar_nacional(janelas, cotacoes):
    achados = []
    for j in janelas:
        for cidade, aeros in C.NACIONAL.items():
            idas = [(preco(cotacoes, C.ORIGEM, a, j["ida"].isoformat()), a, j["ida"]) for a in aeros]
            idas = [x for x in idas if x[0]]
            voltas = [(preco(cotacoes, a, C.ORIGEM, v.isoformat()), a, v) for a in aeros for v in j["voltas"]]
            voltas = [x for x in voltas if x[0]]
            if not idas or not voltas:
                continue
            bi = min(idas, key=lambda x: x[0]["preco"])
            bv = min(voltas, key=lambda x: x[0]["preco"])
            if bi[0]["preco"] <= C.LIMITE_TRECHO and bv[0]["preco"] <= C.LIMITE_TRECHO:
                achados.append({
                    "id": f"N|{cidade}|{j['ida'].isoformat()}",
                    "cidade": cidade, "rotulo": j["rotulo"],
                    "ida": bi, "volta": bv,
                    "total": bi[0]["preco"] + bv[0]["preco"],
                })
    return sorted(achados, key=lambda x: x["ida"][2])


def analisar_internacional(cotacoes):
    res = {}
    for destino, aeros in C.INTERNACIONAL.items():
        def melhor(o_list, d_list, data):
            cands = [(preco(cotacoes, o, d, data), o, d) for o in o_list for d in d_list]
            cands = [c for c in cands if c[0]]
            return min(cands, key=lambda c: c[0]["preco"]) if cands else None

        combos, total_datas, cobertas = [], 0, 0
        ida = C.IDA_DE
        while ida <= C.IDA_ATE:
            total_datas += 1
            bi = melhor([C.ORIGEM], aeros, ida.isoformat())
            if bi:
                cobertas += 1
                for n in range(C.DIAS_VIAGEM_MIN, C.DIAS_VIAGEM_MAX + 1):
                    v = ida + timedelta(days=n)
                    bv = melhor(aeros, [C.ORIGEM], v.isoformat())
                    if bv:
                        combos.append({"ida_data": ida, "volta_data": v, "ida": bi, "volta": bv,
                                       "total": bi[0]["preco"] + bv[0]["preco"], "dias": n})
            ida += timedelta(days=1)
        combos.sort(key=lambda c: c["total"])
        # evita mostrar 5 variações da mesma ida: no máximo 1 combinação por data de ida
        vistos, top = set(), []
        for c in combos:
            if c["ida_data"] in vistos:
                continue
            vistos.add(c["ida_data"])
            top.append(c)
            if len(top) >= C.TOP_INTERNACIONAL:
                break
        res[destino] = {"top": top, "cobertura": cobertas / total_datas if total_datas else 0}
    return res


# ------------------------------------------------------------------ mensagens
def info_voo(c):
    p, o, d = c[0], c[1], c[2] if len(c) > 2 else None
    cia = html.escape(p.get("cia") or "")
    paradas = p.get("paradas")
    escala = "" if not isinstance(paradas, int) else (" direto" if paradas == 0 else f" {paradas} parada(s)")
    return f"{cia}{escala}".strip()


def linha_trecho(rot, cot, o, d, data):
    link = link_google(o, d, data.isoformat() if hasattr(data, "isoformat") else data)
    return (f"  {rot} {fmt_data(data)} {o}→{d}: <b>{fmt_reais(cot['preco'])}</b> "
            f"({info_voo((cot, o, d))}) <a href=\"{link}\">ver</a>")


def bloco_nacional(achados):
    linhas = ["🏖️ <b>Fins de semana com os 2 trechos até "
              f"{fmt_reais(C.LIMITE_TRECHO)}</b>"]
    for a in achados:
        (ci, ai, di), (cv, av, dv) = a["ida"], a["volta"]
        linhas.append(f"\n📍 <b>{a['cidade']}</b> — {html.escape(a['rotulo'])} "
                      f"(total {fmt_reais(a['total'])})")
        linhas.append(linha_trecho("Ida  ", ci, C.ORIGEM, ai, di))
        linhas.append(linha_trecho("Volta", cv, av, C.ORIGEM, dv))
    return "\n".join(linhas)


def bloco_internacional(intl):
    linhas = ["✈️ <b>Internacional — ida e volta, "
              f"{C.DIAS_VIAGEM_MIN}–{C.DIAS_VIAGEM_MAX} dias, abr–set</b>"]
    for destino, r in intl.items():
        linhas.append(f"\n🌎 <b>{destino}</b>"
                      + (f" <i>(datas pesquisadas: {r['cobertura']:.0%})</i>" if r["cobertura"] < 0.99 else ""))
        if not r["top"]:
            linhas.append("  ainda sem dados suficientes")
            continue
        for i, c in enumerate(r["top"], 1):
            ci, cv = c["ida"], c["volta"]
            li = link_google(C.ORIGEM, ci[2], c["ida_data"].isoformat())
            lv = link_google(cv[1], C.ORIGEM, c["volta_data"].isoformat())
            linhas.append(
                f"  {i}. <b>{fmt_reais(c['total'])}</b> — {fmt_data(c['ida_data'])} → "
                f"{fmt_data(c['volta_data'])} ({c['dias']} dias)\n"
                f"     ida {ci[2]} {fmt_reais(ci[0]['preco'])} {info_voo(ci)} <a href=\"{li}\">ver</a> · "
                f"volta {cv[1]} {fmt_reais(cv[0]['preco'])} {info_voo(cv)} <a href=\"{lv}\">ver</a>")
    return "\n".join(linhas)


# ------------------------------------------------------------------ main
def main():
    modo = (os.environ.get("MODO") or "normal").strip().lower()
    est = carregar_estado()
    cot = est.setdefault("cotacoes", {})
    alertas = est.setdefault("alertas", {})
    melhor_intl = est.setdefault("melhor_intl", {})

    # limpa datas que já passaram
    h = hoje().isoformat()
    for k in [k for k in cot if k[-10:] < h]:
        del cot[k]
    for k in [k for k in alertas if k.split("|")[-1] < h]:
        del alertas[k]

    consultas, janelas = montar_consultas()
    if modo == "teste":
        nac = [q for q in consultas if q[3] == "nacional_proximo"][:2]
        intl = [q for q in consultas if q[3] == "internacional"][:2]
        pendentes, faltando = nac + intl, len(consultas)
    else:
        pendentes, faltando = escolher_pendentes(consultas, cot, C.BUSCAS_POR_EXECUCAO)
    print(f"{len(consultas)} consultas no total; {faltando} precisando atualizar; fazendo {len(pendentes)} agora")

    ok, sem, erros, ultimo_erro, bloqueado = executar_buscas(pendentes, cot)
    print(f"ok={ok} sem_voos={sem} erros={erros}")
    salvar_estado(est)

    nacional = analisar_nacional(janelas, cot)
    intl = analisar_internacional(cot)

    novos_nac = []
    for a in nacional:
        ant = alertas.get(a["id"])
        if ant is None or a["total"] <= ant - C.QUEDA_MINIMA_REALERTA:
            novos_nac.append(a)
        alertas[a["id"]] = min(a["total"], ant) if ant is not None else a["total"]

    novidade_intl = False
    for destino, r in intl.items():
        if r["top"]:
            t = r["top"][0]["total"]
            ant = melhor_intl.get(destino)
            if ant is None or t <= ant - C.QUEDA_MINIMA_REALERTA:
                novidade_intl = True
            melhor_intl[destino] = t if ant is None else min(t, ant)
    salvar_estado(est)

    resumo = modo in ("teste", "resumo") or datetime.now(BRT).weekday() == 0  # segunda = resumo semanal
    partes = []
    if modo == "teste":
        linhas = ["🧪 <b>Teste do monitor</b>",
                  f"Buscas feitas: {ok} com preço, {sem} sem voo, {erros} com erro."]
        for o, d, data, _ in pendentes:
            c = cot.get(chave(o, d, data))
            if c and c.get("preco") is not None:
                linhas.append(f"• {o}→{d} {fmt_data(data)}: {fmt_reais(c['preco'])} "
                              f"({info_voo((c, o, d))}, cotado em {c.get('moeda_original', '?')})")
            elif c:
                linhas.append(f"• {o}→{d} {fmt_data(data)}: sem voos")
        if erros:
            linhas.append(f"⚠️ Último erro: <code>{html.escape(ultimo_erro)}</code>")
        else:
            linhas.append("✅ Tudo funcionando. A rodada diária vai preencher o resto nos próximos dias.")
        partes.append("\n".join(linhas))
    else:
        if novos_nac:
            partes.append(bloco_nacional(novos_nac))
        elif resumo and nacional:
            partes.append(bloco_nacional(nacional))
        elif resumo:
            partes.append(f"🏖️ Nenhum fim de semana com os 2 trechos até {fmt_reais(C.LIMITE_TRECHO)} por enquanto.")
        if novidade_intl or resumo:
            partes.append(("🔔 <b>Novo menor preço!</b>\n" if novidade_intl else "") + bloco_internacional(intl))

    if bloqueado:
        partes.append("⚠️ Muitas buscas falharam seguidas hoje (o Google pode estar bloqueando). "
                      f"Último erro: <code>{html.escape(ultimo_erro)}</code>")

    if partes:
        enviar("\n\n".join(partes))
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
