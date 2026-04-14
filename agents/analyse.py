"""
analyse.py — Agent analyste technique BRVM
Calcule les signaux d'entrée/sortie pour chaque position et cible
"""

from datetime import datetime


# ─────────────────────────────────────────────
# DONNÉES DE RÉFÉRENCE — cours historiques
# Mis à jour à chaque run par l'agent veille
# ─────────────────────────────────────────────

CONTEXTE_TECHNIQUE = {
    "BICB": {
        "support":    5100,
        "resistance": 5700,
        "tendance":   "laterale",
        "note":       "Consolidation post-IPO — ordre limite 5 700 FCFA recommandé",
        "catalyseur": "Fusion SG Bénin potentielle + dividende généreux annoncé",
    },
    "BOAB": {
        "support":    7200,
        "resistance": 7800,
        "tendance":   "haussiere",
        "note":       "Forte PV latente — ex-div 5 mai 2026",
        "catalyseur": "Dividende 594.5 FCFA net/titre",
    },
    "SGBC": {
        "support":    32000,
        "resistance": 36000,
        "tendance":   "haussiere",
        "note":       "Meilleure performance du portefeuille en valeur absolue",
        "catalyseur": "Résultats solides secteur bancaire CI",
    },
    "SNTS": {
        "support":    27500,
        "resistance": 30000,
        "tendance":   "laterale",
        "note":       "Position légèrement en MV — titre fondamentalement solide",
        "catalyseur": "Dividende attendu T2 2026",
    },
    "SIVC": {
        "support":    2800,
        "resistance": 3500,
        "tendance":   "haussiere",
        "note":       "+117% sur CMP — momentum fort confirmé",
        "catalyseur": "Cycle haussier agro-industrie UEMOA",
    },
    "ETIT": {
        "support":    30,
        "resistance": 38,
        "tendance":   "laterale",
        "note":       "Cours stagnant depuis plusieurs semaines",
        "catalyseur": "Expansion réseau Afrique subsaharienne",
    },
    # Cibles
    "NTLC": {
        "support":    11500,
        "resistance": 13000,
        "tendance":   "correction",
        "note":       "Correction de -7% depuis 12 900 — zone d'entrée attractive",
        "catalyseur": "Fondamentaux solides, marque premium",
    },
    "TTLC": {
        "support":    2600,
        "resistance": 3000,
        "tendance":   "haussiere",
        "note":       "Rebond en cours — entrée après liquidation BICB partielle",
        "catalyseur": "Prix pétrole + expansion réseau CI",
    },
}


def signal_entree(ticker, cours_actuel):
    """
    Calcule le signal d'entrée pour un ticker.
    Retourne : ACHETER / ATTENDRE / VENDRE / NEUTRE
    """
    ctx = CONTEXTE_TECHNIQUE.get(ticker)
    if not ctx:
        return {"signal": "INCONNU", "raison": "Pas de contexte technique disponible"}

    support    = ctx["support"]
    resistance = ctx["resistance"]
    tendance   = ctx["tendance"]

    # Zone d'entrée : cours proche du support (dans les 5%)
    pct_vs_support    = (cours_actuel - support) / support * 100
    pct_vs_resistance = (resistance - cours_actuel) / resistance * 100

    if tendance == "correction" and pct_vs_support < 10:
        return {
            "signal": "ACHETER",
            "force": "forte",
            "raison": f"Correction en cours — cours à {pct_vs_support:.1f}% du support",
            "note": ctx["note"],
        }
    elif tendance == "haussiere" and pct_vs_support < 5:
        return {
            "signal": "ACHETER",
            "force": "normale",
            "raison": f"Tendance haussière — rebond sur support",
            "note": ctx["note"],
        }
    elif pct_vs_resistance < 3:
        return {
            "signal": "ATTENDRE",
            "force": "normale",
            "raison": f"Proche résistance ({resistance:,} FCFA) — risque de rejet",
            "note": ctx["note"],
        }
    elif tendance == "laterale":
        return {
            "signal": "NEUTRE",
            "force": "faible",
            "raison": f"Consolidation latérale entre {support:,} et {resistance:,} FCFA",
            "note": ctx["note"],
        }
    else:
        return {
            "signal": "ATTENDRE",
            "force": "normale",
            "raison": f"Pas de signal clair — surveiller le support à {support:,} FCFA",
            "note": ctx["note"],
        }


def analyser_cibles(cours):
    """Analyse spécifique des cibles d'achat halal"""
    cibles = ["NTLC", "TTLC", "SIVC"]
    resultats = {}

    for ticker in cibles:
        c = cours.get(ticker)
        if not c:
            continue
        signal = signal_entree(ticker, c)
        ctx = CONTEXTE_TECHNIQUE.get(ticker, {})
        resultats[ticker] = {
            "cours": c,
            "signal": signal,
            "support": ctx.get("support"),
            "resistance": ctx.get("resistance"),
            "catalyseur": ctx.get("catalyseur", ""),
            "tendance": ctx.get("tendance", ""),
        }

    return resultats


def analyser_positions(cours, positions):
    """Analyse technique des positions existantes"""
    resultats = {}

    for p in positions:
        ticker = p["ticker"]
        c = cours.get(ticker, p["cours"])
        signal = signal_entree(ticker, c)
        ctx = CONTEXTE_TECHNIQUE.get(ticker, {})

        resultats[ticker] = {
            "cours": c,
            "signal": signal,
            "pv": p["pv"],
            "poids": p["poids"],
            "support": ctx.get("support"),
            "resistance": ctx.get("resistance"),
            "catalyseur": ctx.get("catalyseur", ""),
        }

    return resultats


def run(cours, positions):
    """Point d'entrée principal"""
    print(f"[analyse] Analyse technique de {len(positions)} positions + cibles...")

    analyse_positions = analyser_positions(cours, positions)
    analyse_cibles    = analyser_cibles(cours)

    # Log des signaux forts
    for ticker, data in {**analyse_positions, **analyse_cibles}.items():
        s = data["signal"]["signal"]
        if s == "ACHETER":
            print(f"  [SIGNAL] {ticker} : ACHETER — {data['signal']['raison']}")

    print(f"[analyse] Analyse terminée")

    return {
        "positions": analyse_positions,
        "cibles":    analyse_cibles,
        "date":      datetime.now().strftime("%Y-%m-%d"),
    }


if __name__ == "__main__":
    # Test avec données du 14 avril 2026
    cours_test = {
        "BOAB": 7450, "BICC": 23010, "BICB": 5120, "ETIT": 34,
        "SGBC": 33900, "SIBC": 7000, "SNTS": 28800, "SIVC": 3215,
        "NTLC": 12000, "TTLC": 2795,
    }
    positions_test = [
        {"ticker": "BICB", "cours": 5120, "pv": -115000, "poids": 35.9},
        {"ticker": "BOAB", "cours": 7450, "pv":  373000, "poids": 18.1},
        {"ticker": "SNTS", "cours": 28800, "pv": -29000,  "poids": 14.7},
        {"ticker": "SIVC", "cours": 3215, "pv":  440000,  "poids": 2.8},
        {"ticker": "NTLC", "cours": 12000, "pv": 0,       "poids": 0},
        {"ticker": "TTLC", "cours": 2795, "pv": 0,        "poids": 0},
    ]

    data = run(cours_test, positions_test)

    print("\n─── Signaux cibles ───")
    for ticker, info in data["cibles"].items():
        print(f"  {ticker} : {info['signal']['signal']} — {info['signal']['raison']}")
