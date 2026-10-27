"""Busca o menor preço de um trecho só de ida no Google Flights (via fast-flights)."""
import inspect
import json
import os
import random
import re
import urllib.request

_FX_CACHE = {}


class SemVoos(Exception):
    pass


def taxa_para_brl(moeda: str) -> float:
    """Converte qualquer moeda para BRL usando uma API pública gratuita."""
    if moeda == "BRL":
        return 1.0
    if moeda in _FX_CACHE:
        return _FX_CACHE[moeda]
    try:
        with urllib.request.urlopen(f"https://open.er-api.com/v6/latest/{moeda}", timeout=20) as r:
            taxa = float(json.load(r)["rates"]["BRL"])
    except Exception as e:  # fallback conservador
        print(f"[aviso] não consegui a cotação {moeda}->BRL ({e}); usando valor aproximado")
        taxa = {"USD": 5.6, "EUR": 6.1}.get(moeda, 5.6)
    _FX_CACHE[moeda] = taxa
    return taxa


def ler_preco(texto: str):
    """'R$ 1.234' / '$123' / 'BRL 1,234' -> (valor_em_reais, moeda_original)."""
    if not texto:
        return None
    t = texto.strip()
    if "R$" in t or "BRL" in t:
        moeda = "BRL"
    elif "€" in t or "EUR" in t:
        moeda = "EUR"
    elif "$" in t or "USD" in t:
        moeda = "USD"
    else:
        return None
    num = re.sub(r"[^\d.,]", "", t)
    if not num:
        return None
    if re.search(r"[.,]\d{2}$", num):  # tem centavos
        inteiro, cent = num[:-3], num[-2:]
        valor = float(re.sub(r"[.,]", "", inteiro) + "." + cent)
    else:
        valor = float(re.sub(r"[.,]", "", num))
    return round(valor * taxa_para_brl(moeda), 2), moeda


_PRIMP_OK = False
_NAVEGADORES = ["chrome_133", "chrome_131", "chrome_130", "chrome_128", "chrome_127",
                "chrome", "chrome_126", "random", None]


def _corrigir_primp():
    """O fast-flights pede impersonate='chrome_126', que versões novas do primp
    não aceitam. Troca o Client do primp por um que tenta versões válidas.
    Precisa rodar ANTES de importar fast_flights."""
    global _PRIMP_OK
    if _PRIMP_OK:
        return
    import primp

    original = primp.Client
    escolhido = {}

    class ClienteBrasil:
        """Repassa tudo ao Client real, mas força preços em R$ vendidos no Brasil."""
        def __init__(self, c):
            self._c = c

        def __getattr__(self, nome):
            return getattr(self._c, nome)

        def get(self, url, *args, **kwargs):
            if "google." in str(url) and "/travel/flights" in str(url):
                params = dict(kwargs.get("params") or {})
                params["curr"] = "BRL"
                params["gl"] = "BR"
                kwargs["params"] = params
            return self._c.get(url, *args, **kwargs)

    def client_compat(*args, **kwargs):
        return ClienteBrasil(_criar(*args, **kwargs))

    def _criar(*args, **kwargs):
        if "imp" in escolhido:
            if escolhido["imp"] is None:
                kwargs.pop("impersonate", None)
            else:
                kwargs["impersonate"] = escolhido["imp"]
            return original(*args, **kwargs)
        pedido = kwargs.get("impersonate")
        ultimo = None
        for imp in [pedido] + [n for n in _NAVEGADORES if n != pedido]:
            kw = dict(kwargs)
            if imp is None:
                kw.pop("impersonate", None)
            else:
                kw["impersonate"] = imp
            try:
                c = original(*args, **kw)
                escolhido["imp"] = imp
                print(f"[primp {getattr(primp, '__version__', '?')}] usando impersonate={imp}")
                return c
            except Exception as e:  # BuilderError: Invalid impersonate
                ultimo = e
        raise ultimo

    primp.Client = client_compat
    import sys
    for nome, mod in list(sys.modules.items()):  # caso fast_flights já tenha importado
        if nome.startswith("fast_flights") and getattr(mod, "Client", None) is original:
            mod.Client = client_compat
    _PRIMP_OK = True


def _buscar_real(origem: str, destino: str, data: str):
    _corrigir_primp()
    from fast_flights import FlightData, Passengers, get_flights

    kwargs = dict(
        flight_data=[FlightData(date=data, from_airport=origem, to_airport=destino)],
        trip="one-way",
        seat="economy",
        passengers=Passengers(adults=1),
    )
    params = inspect.signature(get_flights).parameters
    if "fetch_mode" in params:
        kwargs["fetch_mode"] = "fallback"
    if "currency" in params:
        kwargs["currency"] = "BRL"
    try:
        resultado = get_flights(**kwargs)
    except Exception as e:
        if "no flights" in str(e).lower():
            raise SemVoos() from e
        raise

    melhor = None
    for f in getattr(resultado, "flights", []) or []:
        p = ler_preco(getattr(f, "price", ""))
        if not p:
            continue
        if melhor is None or p[0] < melhor["preco"]:
            melhor = {
                "preco": p[0],
                "moeda_original": p[1],
                "cia": getattr(f, "name", "") or "",
                "saida": getattr(f, "departure", "") or "",
                "paradas": getattr(f, "stops", None) if isinstance(getattr(f, "stops", None), int) else None,
            }
    if melhor is None:
        raise SemVoos()
    return melhor


def _buscar_falso(origem, destino, data):
    """Preços simulados para testar a lógica sem internet (FAKE=1)."""
    rnd = random.Random(f"{origem}{destino}{data}")
    if rnd.random() < 0.05:
        raise SemVoos()
    internacional = destino in ("EZE", "AEP", "SCL") or origem in ("EZE", "AEP", "SCL")
    base = rnd.uniform(650, 1900) if internacional else rnd.uniform(150, 650)
    return {"preco": round(base, 2), "moeda_original": "BRL",
            "cia": rnd.choice(["Azul", "GOL", "LATAM"]), "saida": "07:30", "paradas": rnd.choice([0, 0, 1])}


def menor_preco(origem: str, destino: str, data: str):
    if os.environ.get("FAKE") == "1":
        return _buscar_falso(origem, destino, data)
    return _buscar_real(origem, destino, data)


def link_google(origem: str, destino: str, data: str) -> str:
    q = f"Flights from {origem} to {destino} on {data} one way"
    return "https://www.google.com/travel/flights?hl=pt-BR&curr=BRL&gl=BR&q=" + urllib.request.quote(q)


def link_kayak(origem: str, destino: str, data: str) -> str:
    return f"https://www.kayak.com.br/flights/{origem}-{destino}/{data}?sort=price_a"


def link_skyscanner(origem: str, destino: str, data: str) -> str:
    aammdd = data[2:4] + data[5:7] + data[8:10]
    return (f"https://www.skyscanner.com.br/transporte/passagens-aereas/{origem.lower()}/"
            f"{destino.lower()}/{aammdd}/?adultsv2=1&cabinclass=economy&rtn=0")


def link_maxmilhas(origem: str, destino: str, data: str) -> str:
    return f"https://www.maxmilhas.com.br/busca-passagens-aereas/OW/{origem}/{destino}/{data}/1/0/0/EC"
