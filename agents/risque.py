"""
risque.py — Agent gestion de risque portefeuille BRVM
Surveille la concentration, les stop-loss et les alertes de rééquilibrage
"""

from datetime import datetime


# ─────────────────────────────────────────────
# PARAMÈTRES DE RISQUE (configurables)
# ─────────────────────────────────────────────

LIMITES = {
    "concentration_max_pct":    25.0,   # Aucune position > 25% du portefeuille
    "concentration_critique":   35.0,   # Alerte critique si > 35%
    "stop_loss_pct":           -15.0,   # Coupe si PV < -15% sur le cours d'achat
    "take_profit_pct":         100.0,   # Alerte prise de bénéfices si > 100% sur CMP
    "halal_min_pct":            30.0,   # Part halal minimum visée dans le portefeuille
    "secteur_max_pct":          60.0,   # Un seul secteur ne doit pas dépasser 60%
}

# Stop-loss personnalisés par ticker
STOP_LOSS_CUSTOM = {
    "BICB": 4800,   # Si BIIC BN tombe sous 4 800 FCFA → couper la position
    "ETIT": 28,     # Si Ecobank tombe sous 28 FCFA → couper
    "SNTS": 26000,  # Si Sonatel tombe sous 26 000 FCFA → couper
}


# ─────────────────────────────────────────────
# FONCTIONS D'ANALYSE
# ─────────────────────────────────────────────

def verifier_concentration(positions):
    """Détecte les positions surconcentrées"""
    alertes = []

    for p in positions:
        poids = p["poids"]
        ticker = p["ticker"]

        if poids >= LIMITES["concentration_critique"]:
            alertes.append({
                "ticker": ticker,
                "niveau": "CRITIQUE",
                "type": "concentration",
                "message": f"{ticker} à {poids}% du portefeuille — dépasse le seuil critique de {LIMITES['concentration_critique']}%",
                "action": f"Vendre partiellement pour ramener sous {LIMITES['concentration_max_pct']}%",
            })
        elif poids >= LIMITES["concentration_max_pct"]:
            alertes.append({
                "ticker": ticker,
                "niveau": "ATTENTION",
                "type": "concentration",
                "message": f"{ticker} à {poids}% — dépasse le seuil recommandé de {LIMITES['concentration_max_pct']}%",
                "action": "Surveiller — alléger si opportunité se présente",
            })

    return alertes


def verifier_stop_loss(positions, cours):
    """Vérifie les stop-loss sur toutes les positions"""
    alertes = []

    for p in positions:
        ticker = p["ticker"]
        cours_actuel = cours.get(ticker, p["cours"])
        cmp = p["cmp"]

        # Stop-loss custom
        if ticker in STOP_LOSS_CUSTOM:
            niveau_stop = STOP_LOSS_CUSTOM[ticker]
            if cours_actuel <= niveau_stop:
                alertes.append({
                    "ticker": ticker,
                    "niveau": "URGENT",
                    "type": "stop_loss",
                    "message": f"{ticker} à {cours_actuel:,} FCFA — sous le stop-loss à {niveau_stop:,} FCFA",
                    "action": "VENDRE IMMÉDIATEMENT",
                })
            continue

        # Stop-loss en % sur CMP
        variation_pct = (cours_actuel - cmp) / cmp * 100
        if variation_pct <= LIMITES["stop_loss_pct"]:
            alertes.append({
                "ticker": ticker,
                "niveau": "URGENT",
                "type": "stop_loss",
                "message": f"{ticker} en baisse de {variation_pct:.1f}% sur CMP — stop-loss déclenché ({LIMITES['stop_loss_pct']}%)",
                "action": "VENDRE — stopper la perte",
            })

    return alertes


def verifier_take_profit(positions, cours):
    """Détecte les positions en fort gain où une prise de bénéfices est recommandée"""
    alertes = []

    for p in positions:
        ticker = p["ticker"]
        cours_actuel = cours.get(ticker, p["cours"])
        cmp = p["cmp"]

        variation_pct = (cours_actuel - cmp) / cmp * 100
        if variation_pct >= LIMITES["take_profit_pct"]:
            alertes.append({
                "ticker": ticker,
                "niveau": "INFO",
                "type": "take_profit",
                "message": f"{ticker} en hausse de +{variation_pct:.0f}% sur CMP — prise de bénéfices partielle recommandée",
                "action": f"Envisager de vendre 30-50% de la position",
            })

    return alertes


def verifier_diversification(positions, halal_data):
    """Vérifie la diversification sectorielle et la part halal"""
    alertes = []

    # Calcul part halal
    poids_halal = sum(
        p["poids"] for p in positions
        if halal_data.get(p["ticker"], {}).get("verdict") == "CONFORME"
    )

    if poids_halal < LIMITES["halal_min_pct"]:
        alertes.append({
            "ticker": "PORTEFEUILLE",
            "niveau": "ATTENTION",
            "type": "diversification_halal",
            "message": f"Part halal : {poids_halal:.1f}% — sous l'objectif de {LIMITES['halal_min_pct']}%",
            "action": "Renforcer NTLC, TTLC, SIVC pour rééquilibrer",
        })

    # Calcul concentration sectorielle
    secteurs = {}
    for p in positions:
        secteur = halal_data.get(p["ticker"], {}).get("secteur", "inconnu")
        secteurs[secteur] = secteurs.get(secteur, 0) + p["poids"]

    for secteur, poids in secteurs.items():
        if poids >= LIMITES["secteur_max_pct"]:
            alertes.append({
                "ticker": "PORTEFEUILLE",
                "niveau": "ATTENTION",
                "type": "concentration_sectorielle",
                "message": f"Secteur '{secteur}' représente {poids:.1f}% du portefeuille",
                "action": "Diversifier vers d'autres secteurs",
            })

    return alertes, poids_halal


def calculer_score_risque(alertes):
    """Calcule un score de risque global de 0 (faible) à 100 (critique)"""
    score = 0
    for a in alertes:
        if a["niveau"] == "URGENT":
            score += 30
        elif a["niveau"] == "CRITIQUE":
            score += 20
        elif a["niveau"] == "ATTENTION":
            score += 10
        elif a["niveau"] == "INFO":
            score += 2

    return min(score, 100)


def run(cours, positions, halal_data=None):
    """Point d'entrée principal"""
    print(f"[risque] Analyse de risque sur {len(positions)} positions...")

    if halal_data is None:
        halal_data = {}

    # Reconstituer le format attendu par verifier_diversification
    halal_format = {}
    for ticker, data in halal_data.items():
        if isinstance(data, dict):
            halal_format[ticker] = {
                "verdict": data.get("verdict", "INCONNU"),
                "secteur": data.get("secteur", "inconnu"),
            }

    alertes_concentration = verifier_concentration(positions)
    alertes_stop          = verifier_stop_loss(positions, cours)
    alertes_profit        = verifier_take_profit(positions, cours)
    alertes_diversif, poids_halal = verifier_diversification(positions, halal_format)

    toutes_alertes = (
        alertes_concentration +
        alertes_stop +
        alertes_profit +
        alertes_diversif
    )

    score = calculer_score_risque(toutes_alertes)

    # Tri par niveau d'urgence
    ordre = {"URGENT": 0, "CRITIQUE": 1, "ATTENTION": 2, "INFO": 3}
    toutes_alertes.sort(key=lambda x: ordre.get(x["niveau"], 4))

    # Log
    for a in toutes_alertes:
        emoji = "🚨" if a["niveau"] in ("URGENT", "CRITIQUE") else "⚠️"
        print(f"  [{a['niveau']}] {a['ticker']} : {a['message']}")

    print(f"[risque] Score de risque : {score}/100 — {len(toutes_alertes)} alertes")

    return {
        "alertes": toutes_alertes,
        "score_risque": score,
        "poids_halal": round(poids_halal, 1),
        "date": datetime.now().strftime("%Y-%m-%d"),
    }


if __name__ == "__main__":
    cours_test = {
        "BOAB": 7450, "BICC": 23010, "BICB": 5120, "ETIT": 34,
        "SGBC": 33900, "SIBC": 7000, "SNTS": 28800, "SIVC": 3215,
    }
    positions_test = [
        {"ticker": "BICB", "cours": 5120, "cmp": 5250, "pv": -115000, "poids": 35.9},
        {"ticker": "BOAB", "cours": 7450, "cmp": 6334, "pv":  373000, "poids": 18.1},
        {"ticker": "SGBC", "cours": 33900,"cmp": 22460,"pv":  572000, "poids": 11.7},
        {"ticker": "ETIT", "cours": 34,   "cmp": 32,   "pv":  104000, "poids": 11.6},
        {"ticker": "SNTS", "cours": 28800,"cmp": 28392,"pv":  -29000, "poids": 14.7},
        {"ticker": "SIVC", "cours": 3215, "cmp": 1014, "pv":  440000, "poids": 2.8},
        {"ticker": "BICC", "cours": 23010,"cmp": 15919,"pv":  213000, "poids": 4.8},
        {"ticker": "SIBC", "cours": 7000, "cmp": 4437, "pv":   18000, "poids": 0.3},
    ]
    halal_test = {
        "SNTS": {"verdict": "CONFORME",     "secteur": "telecom"},
        "SIVC": {"verdict": "CONFORME",     "secteur": "agro"},
        "BICB": {"verdict": "NON_CONFORME", "secteur": "banque"},
        "BOAB": {"verdict": "NON_CONFORME", "secteur": "banque"},
        "SGBC": {"verdict": "NON_CONFORME", "secteur": "banque"},
        "ETIT": {"verdict": "NON_CONFORME", "secteur": "banque"},
        "SNTS": {"verdict": "CONFORME",     "secteur": "telecom"},
        "BICC": {"verdict": "NON_CONFORME", "secteur": "banque"},
        "SIBC": {"verdict": "NON_CONFORME", "secteur": "banque"},
    }

    data = run(cours_test, positions_test, halal_test)
    print(f"\nScore risque final : {data['score_risque']}/100")
    print(f"Part halal : {data['poids_halal']}%")
