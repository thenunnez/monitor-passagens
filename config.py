"""Configuração do monitor. Edite aqui as rotas, datas e limites."""
from datetime import date

ORIGEM = "CNF"  # Confins

# ---------------------------------------------------------------
# Viagens nacionais de fim de semana / feriado
# ---------------------------------------------------------------
NACIONAL = {
    # nome da cidade -> aeroportos considerados
    "Rio de Janeiro": ["GIG", "SDU"],
    "São Paulo": ["GRU", "CGH", "VCP"],
    "Vitória": ["VIX"],
}
LIMITE_TRECHO = 240.00        # R$ por trecho (ida e volta, cada um)
NACIONAL_A_PARTIR_DE = date(2027, 1, 1)  # só fins de semana a partir desta data
HORIZONTE_DIAS = 330          # até quantos dias à frente olhar (Google vai até ~11 meses)
VOLTA_DIA_SEGUINTE = True     # também testa voltar no dia seguinte (ex.: segunda cedo)
CONSIDERAR_PONTE = True       # feriado na quinta/terça: inclui a "ponte" (sexta/segunda)

# Feriados extras além dos nacionais (ex.: municipais de BH). Formato date(AAAA, M, D)
FERIADOS_EXTRAS = [
    date(2026, 12, 8),   # Imaculada Conceição (BH)
    date(2027, 8, 15),   # Assunção de Nossa Senhora (BH)
]

# ---------------------------------------------------------------
# Viagens de ida e volta (lista as combinações mais baratas)
#   origem/destino: aeroportos (a volta é destino -> origem)
#   ida_de / ida_ate: datas possíveis de ida (ida_ate=None -> até onde o Google mostra)
#   dias_min/dias_max: duração da viagem   OU   voltas: datas fixas de volta
#   mesmo_aeroporto: True = volta do mesmo aeroporto/cidade em que chegou
#   atualizar_dias: de quantos em quantos dias reconsultar cada data
# ---------------------------------------------------------------
IDA_E_VOLTA = [
    {"nome": "Argentina (Buenos Aires)", "emoji": "🇦🇷",
     "origem": ["CNF"], "destino": ["EZE", "AEP"],
     "ida_de": date(2027, 4, 1), "ida_ate": date(2027, 9, 30),
     "dias_min": 5, "dias_max": 10, "mesmo_aeroporto": False, "atualizar_dias": 5},
    {"nome": "Chile (Santiago)", "emoji": "🇨🇱",
     "origem": ["CNF"], "destino": ["SCL"],
     "ida_de": date(2027, 4, 1), "ida_ate": date(2027, 9, 30),
     "dias_min": 5, "dias_max": 10, "mesmo_aeroporto": False, "atualizar_dias": 5},
    {"nome": "Cuiabá ↔ Confins (saindo de Cuiabá)", "emoji": "🌾",
     "origem": ["CGB"], "destino": ["CNF"],
     "ida_de": date(2027, 1, 1), "ida_ate": None,
     "dias_min": 5, "dias_max": 10, "mesmo_aeroporto": False, "atualizar_dias": 5},
    {"nome": "Confins → Sinop/Cuiabá (dezembro)", "emoji": "🎄",
     "origem": ["CNF"], "destino": ["OPS", "CGB"],
     "idas": [date(2026, 12, 18), date(2026, 12, 19), date(2026, 12, 20)],
     "voltas": [date(2026, 12, 24), date(2026, 12, 25), date(2026, 12, 26)],
     "mesmo_aeroporto": True, "atualizar_dias": 1},
]
TOP_IDA_E_VOLTA = 5            # quantas combinações mostrar por rota

# ---------------------------------------------------------------
# Ritmo das buscas
# ---------------------------------------------------------------
BUSCAS_POR_EXECUCAO = 600      # limite de consultas por rodada (evita bloqueio)
ATUALIZAR_A_CADA_DIAS = {
    "nacional_proximo": 1,     # fins de semana nos próximos 45 dias
    "nacional_longe": 3,
}
DIAS_NACIONAL_PROXIMO = 45
PAUSA_ENTRE_BUSCAS = (1.0, 2.5)  # segundos (aleatório)
QUEDA_MINIMA_REALERTA = 10.00    # só avisa de novo se cair pelo menos R$ 10
IGNAV_MAX_TRECHOS = 25           # máx. de trechos por rodada buscando link direto (cada um = 2 consultas na Ignav)
