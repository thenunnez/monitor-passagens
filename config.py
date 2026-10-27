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
HORIZONTE_DIAS = 180          # olha fins de semana até ~6 meses à frente
VOLTA_DIA_SEGUINTE = True     # também testa voltar no dia seguinte (ex.: segunda cedo)
CONSIDERAR_PONTE = True       # feriado na quinta/terça: inclui a "ponte" (sexta/segunda)

# Feriados extras além dos nacionais (ex.: municipais de BH). Formato date(AAAA, M, D)
FERIADOS_EXTRAS = [
    date(2026, 12, 8),   # Imaculada Conceição (BH)
    date(2027, 8, 15),   # Assunção de Nossa Senhora (BH)
]

# ---------------------------------------------------------------
# Viagens internacionais (ida e volta, menor preço)
# ---------------------------------------------------------------
INTERNACIONAL = {
    "Argentina (Buenos Aires)": ["EZE", "AEP"],
    "Chile (Santiago)": ["SCL"],
    # Para incluir outras cidades, ex.: "Argentina (Bariloche)": ["BRC"],
}
IDA_DE = date(2027, 4, 1)
IDA_ATE = date(2027, 9, 30)
DIAS_VIAGEM_MIN = 5
DIAS_VIAGEM_MAX = 10
TOP_INTERNACIONAL = 5          # quantas combinações mostrar por destino

# ---------------------------------------------------------------
# Ritmo das buscas
# ---------------------------------------------------------------
BUSCAS_POR_EXECUCAO = 450      # limite de consultas por rodada (evita bloqueio)
ATUALIZAR_A_CADA_DIAS = {
    "nacional_proximo": 1,     # fins de semana nos próximos 45 dias
    "nacional_longe": 3,
    "internacional": 4,
}
DIAS_NACIONAL_PROXIMO = 45
PAUSA_ENTRE_BUSCAS = (1.0, 2.5)  # segundos (aleatório)
QUEDA_MINIMA_REALERTA = 10.00    # só avisa de novo se cair pelo menos R$ 10
