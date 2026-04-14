"""
veille.py — Agent de veille marché BRVM
Récupère les cours en temps réel depuis brvm.org
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime


TICKERS_PORTEFEUILLE = ["BOAB", "BICC", "BICB", "ETIT", "SGBC", "SIBC", "SNTS", "SIVC"]
TICKERS_CIBLES = ["TTLC", "NTLC", "SIVC"]
TOUS_TICKERS = list(set(TICKERS_PORTEFEUILLE + TICKERS_CIBLES))

COURS_REFERENCE = {
    "BOAB": {"nom": "Bank of Africa BN",     "cmp": 6334},
    "BICC": {"nom": "BICI CI",               "cmp": 15919},
    "BICB": {"nom": "BIIC BN",               "cmp": 5250},
    "ETIT": {"nom": "Ecobank ETI",           "cmp": 32},
    "SGBC": {"nom": "Societe Generale CI",   "cmp": 22460},
    "SIBC": {"nom": "SIB CI",               "cmp": 4437},
    "SNTS": {"nom": "Sonatel SN",           "cmp": 28392},
    "SIVC": {"nom": "Sucrivoire CI",         "cmp": 1014},
    "TTLC": {"nom": "TotalEnergies CI",      "cmp": None},
    "NTLC": {"nom": "Nestle CI",             "cmp": None},
}


def fetch_cours_brvm():
    """Scrape les cours depuis brvm.org"""
    url = "https://www.brvm.org/fr/cours-actions/0"
    headers = {"User-Agent": "Mozilla/5.0"}
    cours = {}

    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Cherche le ticker dans les données de la page
        texte = soup.get_text()
        for ticker in TOUS_TICKERS:
            idx = texte.find(ticker)
            if idx != -1:
                # Extrait les chiffres autour du ticker
                fragment = texte[idx:idx+60]
                nombres = []
                import re
                for m in re.finditer(r"[\d\s]+(?:,\d+)?", fragment):
                    val = m.group().replace(" ", "").replace(",", ".")
                    try:
                        nombres.append(float(val))
                    except ValueError:
                        pass
                if nombres:
                    cours[ticker] = int(nombres[0])

    except Exception as e:
        print(f"Erreur scraping BRVM: {e}")

    # Fallback : cours du 14 avril 2026 (derniers connus)
    fallback = {
        "BOAB": 7450, "BICC": 23010, "BICB": 5120, "ETIT": 34,
        "SGBC": 33900, "SIBC": 7000, "SNTS": 28800, "SIVC": 3215,
        "TTLC": 2795, "NTLC": 12000,
    }
    for t, v in fallback.items():
        if t not in cours:
            cours[t] = v

    return cours


def calculer_positions(cours):
    """Calcule PV/MV et pondérations pour chaque position"""
    positions = []
    total_valeur = sum(
        cours.get(t, 0) * COURS_REFERENCE[t]["cmp"] / COURS_REFERENCE[t]["cmp"]
        * COURS_REFERENCE[t].get("quantite", 0) if "quantite" in COURS_REFERENCE[t] else 0
        for t in TICKERS_PORTEFEUILLE
    )

    quantites = {
        "BOAB": 350, "BICC": 30, "BICB": 1000, "ETIT": 52049,
        "SGBC": 50, "SIBC": 7, "SNTS": 75, "SIVC": 200,
    }

    total_val = sum(cours.get(t, 0) * quantites.get(t, 0) for t in TICKERS_PORTEFEUILLE)

    for ticker in TICKERS_PORTEFEUILLE:
        c = cours.get(ticker, 0)
        qte = quantites.get(ticker, 0)
        cmp = COURS_REFERENCE[ticker]["cmp"]
        valeur = c * qte
        pv = (c - cmp) * qte
        poids = (valeur / total_val * 100) if total_val > 0 else 0

        positions.append({
            "ticker": ticker,
            "nom": COURS_REFERENCE[ticker]["nom"],
            "quantite": qte,
            "cours": c,
            "cmp": cmp,
            "valeur": valeur,
            "pv": pv,
            "poids": round(poids, 1),
            "variation_vs_cmp": round((c - cmp) / cmp * 100, 1) if cmp else 0,
        })

    return positions, total_val


def run():
    """Point d'entrée principal"""
    print(f"[veille] Récupération des cours BRVM — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    cours = fetch_cours_brvm()
    positions, total_val = calculer_positions(cours)
    print(f"[veille] {len(cours)} cours récupérés — valeur portefeuille : {total_val:,.0f} FCFA")
    return {
        "cours": cours,
        "positions": positions,
        "total_valeur": total_val,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "heure": datetime.now().strftime("%H:%M"),
    }


if __name__ == "__main__":
    data = run()
    for p in data["positions"]:
        signe = "+" if p["pv"] >= 0 else ""
        print(f"  {p['ticker']:6s} {p['cours']:8,d} FCFA  PV: {signe}{p['pv']:,.0f}  Poids: {p['poids']}%")
