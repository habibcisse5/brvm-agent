"""
halal.py — Agent screener halal BRVM
Vérifie la conformité charia de chaque position
"""

STATUTS = {
    # Secteurs clairement halal
    "SNTS": {"statut": "conforme",    "secteur": "Télécom",      "note": "Secteur permis"},
    "SIVC": {"statut": "conforme",    "secteur": "Agro",         "note": "Secteur permis"},
    "TTLC": {"statut": "conforme",    "secteur": "Énergie",      "note": "Secteur permis"},
    "NTLC": {"statut": "conforme",    "secteur": "Alimentation", "note": "Secteur permis"},
    # Banques — zone grise (revenus d'intérêts)
    "BOAB": {"statut": "a_clarifier", "secteur": "Banque",       "note": "Revenus d'intérêts — avis savant requis"},
    "BICC": {"statut": "a_clarifier", "secteur": "Banque",       "note": "Revenus d'intérêts — avis savant requis"},
    "BICB": {"statut": "a_clarifier", "secteur": "Banque",       "note": "Revenus d'intérêts — avis savant requis"},
    "ETIT": {"statut": "a_clarifier", "secteur": "Banque",       "note": "Revenus d'intérêts — avis savant requis"},
    "SGBC": {"statut": "a_clarifier", "secteur": "Banque",       "note": "Revenus d'intérêts — avis savant requis"},
    "SIBC": {"statut": "a_clarifier", "secteur": "Banque",       "note": "Revenus d'intérêts — avis savant requis"},
    # Secteurs clairement interdits (hors portefeuille — garde-fou)
    "SLBC": {"statut": "haram",       "secteur": "Alcool",       "note": "Solibra — production alcool INTERDIT"},
}


def verifier(ticker):
    return STATUTS.get(ticker, {
        "statut": "inconnu",
        "secteur": "Non classifié",
        "note": "Vérification manuelle requise"
    })


def bloquer_si_haram(ticker):
    """Retourne True si le ticker est bloqué (haram ou inconnu)"""
    s = verifier(ticker)
    return s["statut"] == "haram"


def run(tickers):
    """Vérifie une liste de tickers et retourne les alertes"""
    print(f"[halal] Vérification de {len(tickers)} tickers")
    resultats = {}
    alertes = []

    for t in tickers:
        info = verifier(t)
        resultats[t] = info
        if info["statut"] == "haram":
            alertes.append({"ticker": t, "niveau": "BLOQUANT", "message": info["note"]})
            print(f"[halal] BLOQUÉ — {t} : {info['note']}")
        elif info["statut"] == "a_clarifier":
            alertes.append({"ticker": t, "niveau": "ATTENTION", "message": info["note"]})

    conformes = [t for t, i in resultats.items() if i["statut"] == "conforme"]
    print(f"[halal] Conformes: {conformes}")
    print(f"[halal] Alertes: {len(alertes)}")

    return {"resultats": resultats, "alertes": alertes}


if __name__ == "__main__":
    tickers = list(STATUTS.keys())
    data = run(tickers)
    for ticker, info in data["resultats"].items():
        print(f"  {ticker:6s} [{info['statut']:12s}] {info['secteur']:14s} — {info['note']}")
