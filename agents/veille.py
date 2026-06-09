"""
veille.py — Agent de veille marché BRVM
Récupère les cours en temps réel depuis brvm.org.
Les positions (tickers, quantités, CMP) sont chargées depuis
data/portefeuille.json — SOURCE UNIQUE DE VÉRITÉ (plus de doublon en dur).
"""

import re
import json
import requests
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup

DATA_DIR     = Path(__file__).parent.parent / "data"
PORTEFEUILLE = DATA_DIR / "portefeuille.json"


def charger_portefeuille():
    """Charge le portefeuille depuis portefeuille.json (source unique)."""
    try:
        with open(PORTEFEUILLE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[veille] Impossible de lire portefeuille.json : {e}")
        return {"positions": []}


def _cmp(p):
    """CMP d'une position — gère 'cmp' ou 'cmp_moyen' (lignes renforcées)."""
    return p.get("cmp", p.get("cmp_moyen", 0))


def fetch_cours_brvm(tickers, fallback):
    """Scrape les cours depuis brvm.org. Repli sur cours_ref du portefeuille."""
    url = "https://www.brvm.org/fr/cours-actions/0"
    headers = {"User-Agent": "Mozilla/5.0"}
    cours = {}

    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        texte = BeautifulSoup(r.text, "html.parser").get_text()
        for ticker in tickers:
            idx = texte.find(ticker)
            if idx != -1:
                fragment = texte[idx:idx + 60]
                for m in re.finditer(r"[\d\s]+(?:,\d+)?", fragment):
                    val = m.group().replace(" ", "").replace(",", ".")
                    try:
                        cours[ticker] = int(float(val))
                        break
                    except ValueError:
                        pass
    except Exception as e:
        print(f"[veille] Erreur scraping BRVM : {e}")

    # Repli : cours de référence du portefeuille (derniers connus)
    for t in tickers:
        if t not in cours:
            cours[t] = fallback.get(t, 0)

    return cours


def calculer_positions(positions_data, cours):
    """Calcule valeur, PV/MV et pondérations à partir des positions du portefeuille."""
    total_val = sum(
        cours.get(p["ticker"], 0) * p.get("quantite", 0) for p in positions_data
    )

    positions = []
    for p in positions_data:
        ticker = p["ticker"]
        c      = cours.get(ticker, 0)
        qte    = p.get("quantite", 0)
        cmp    = _cmp(p)
        valeur = c * qte
        pv     = (c - cmp) * qte
        poids  = (valeur / total_val * 100) if total_val > 0 else 0

        positions.append({
            "ticker":           ticker,
            "nom":              p.get("nom", ticker),
            "quantite":         qte,
            "cours":            c,
            "cmp":              cmp,
            "valeur":           valeur,
            "pv":               pv,
            "poids":            round(poids, 1),
            "variation_vs_cmp": round((c - cmp) / cmp * 100, 1) if cmp else 0,
        })

    return positions, total_val


def run():
    """Point d'entrée principal."""
    print(f"[veille] Récupération des cours BRVM — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    porte          = charger_portefeuille()
    positions_data = porte.get("positions", [])
    tickers        = [p["ticker"] for p in positions_data]
    fallback       = {p["ticker"]: p.get("cours_ref", _cmp(p)) for p in positions_data}

    cours              = fetch_cours_brvm(tickers, fallback)
    positions, total_val = calculer_positions(positions_data, cours)

    print(f"[veille] {len(positions)} positions — valeur portefeuille : {total_val:,.0f} FCFA")
    return {
        "cours":         cours,
        "positions":     positions,
        "total_valeur":  total_val,
        "date":          datetime.now().strftime("%Y-%m-%d"),
        "heure":         datetime.now().strftime("%H:%M"),
    }


if __name__ == "__main__":
    data = run()
    for p in data["positions"]:
        signe = "+" if p["pv"] >= 0 else ""
        print(f"  {p['ticker']:6s} {p['cours']:8,d} FCFA  PV: {signe}{p['pv']:,.0f}  Poids: {p['poids']}%")
