"""
veille.py — Agent de veille marché BRVM
Positions ET cours proviennent de data/portefeuille.json — SOURCE UNIQUE DE VÉRITÉ
(relevé BNI Finance Trade).

Le scraping brvm.org a été RETIRÉ : trop peu fiable (il attribuait parfois à un
titre le cours d'un autre, corrompant tout le portefeuille — total à 144M, faux
stop-loss, etc.). Pour rafraîchir les cours, mettre à jour 'cours_ref' dans
portefeuille.json depuis le relevé BNI.
"""

import json
from pathlib import Path
from datetime import datetime

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


def _cours(p):
    """Cours retenu = cours_ref du portefeuille (relevé BNI), sinon CMP."""
    return p.get("cours_ref", _cmp(p))


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
    """Point d'entrée principal — cours issus du relevé BNI (portefeuille.json)."""
    print(f"[veille] Lecture du portefeuille — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    porte          = charger_portefeuille()
    positions_data = porte.get("positions", [])
    cours          = {p["ticker"]: _cours(p) for p in positions_data}

    positions, total_val = calculer_positions(positions_data, cours)
    print(f"[veille] {len(positions)} positions — valeur : {total_val:,.0f} FCFA (cours : relevé BNI)")
    return {
        "cours":        cours,
        "positions":    positions,
        "total_valeur": total_val,
        "date":         datetime.now().strftime("%Y-%m-%d"),
        "heure":        datetime.now().strftime("%H:%M"),
    }


if __name__ == "__main__":
    data = run()
    for p in data["positions"]:
        signe = "+" if p["pv"] >= 0 else ""
        print(f"  {p['ticker']:6s} {p['cours']:8,d} FCFA  PV: {signe}{p['pv']:,.0f}  Poids: {p['poids']}%")
