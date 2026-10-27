"""Feriados nacionais e janelas de viagem de fim de semana/feriado."""
from datetime import date, timedelta

NOMES = {}


def pascoa(ano: int) -> date:
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def feriados(ano: int, extras=()) -> dict:
    p = pascoa(ano)
    f = {
        date(ano, 1, 1): "Confraternização Universal",
        p - timedelta(days=48): "Carnaval",
        p - timedelta(days=47): "Carnaval",
        p - timedelta(days=2): "Sexta-feira Santa",
        date(ano, 4, 21): "Tiradentes",
        date(ano, 5, 1): "Dia do Trabalho",
        p + timedelta(days=60): "Corpus Christi",
        date(ano, 9, 7): "Independência",
        date(ano, 10, 12): "Nossa Senhora Aparecida",
        date(ano, 11, 2): "Finados",
        date(ano, 11, 15): "Proclamação da República",
        date(ano, 11, 20): "Consciência Negra",
        date(ano, 12, 25): "Natal",
    }
    for d in extras:
        if d.year == ano:
            f.setdefault(d, "Feriado local")
    return f


def janelas_fim_de_semana(inicio: date, fim: date, extras=(), ponte=True, volta_dia_seguinte=True):
    """Retorna lista de janelas: {ida, voltas:[...], rotulo}.

    Um bloco = dias seguidos de folga (sáb, dom, feriados e, se ponte=True,
    um dia útil espremido entre folgas). Ida no dia útil anterior ao bloco;
    volta no último dia do bloco (e no dia seguinte, se configurado).
    """
    fer = {}
    for ano in range(inicio.year, fim.year + 2):
        fer.update(feriados(ano, extras))

    def folga(d):
        return d.weekday() >= 5 or d in fer

    dias = [inicio + timedelta(days=i) for i in range((fim - inicio).days + 15)]
    off = {d for d in dias if folga(d)}
    if ponte:
        for d in dias:
            if d not in off and (d - timedelta(days=1)) in off and (d + timedelta(days=1)) in off:
                # só conta como ponte se um dos lados for feriado (não fim de semana comum)
                if (d - timedelta(days=1)) in fer or (d + timedelta(days=1)) in fer:
                    off.add(d)

    janelas = []
    d = inicio
    while d <= fim + timedelta(days=10):
        if d in off and (d - timedelta(days=1)) not in off:
            ini = d
            while (d + timedelta(days=1)) in off:
                d += timedelta(days=1)
            ultimo = d
            ida = ini - timedelta(days=1)
            if inicio <= ida <= fim:
                nomes = sorted({fer[x] for x in fer if ini <= x <= ultimo})
                rotulo = " + ".join(nomes) if nomes else "Fim de semana"
                voltas = [ultimo] + ([ultimo + timedelta(days=1)] if volta_dia_seguinte else [])
                janelas.append({"ida": ida, "voltas": voltas, "rotulo": rotulo,
                                "dias_folga": (ultimo - ini).days + 1})
        d += timedelta(days=1)
    return janelas
