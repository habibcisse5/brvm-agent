"""
opportunites.py v2 — Agent de détection d'opportunités BRVM
Sources de données (par ordre de priorité) :
  1. TOP 10 BNI Finances (extrait automatiquement du rapport hebdo)
  2. Cours scrapés sur brvm.org
  3. Données fondamentales de référence (mises à jour annuellement)

Filtres appliqués dans l'ordre :
  1. Filtre halal (secteur + ratios)
  2. Filtre portefeuille (pas déjà en portefeuille)
  3. Signal BNI (dans le TOP 10 = signal fort)
  4. Filtre technique (cours vs support)
  5. Filtre fondamental (PER, dividende, croissance)
"""

import json
import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup


# ─────────────────────────────────────────────
# UNIVERS BRVM — éligible au scan
# ─────────────────────────────────────────────

UNIVERS = {
    # Agro-industrie / Alimentaire
    "SIVC": {"nom": "Sucrivoire CI",           "secteur": "agro",         "halal": True},
    "SCRC": {"nom": "Sucrivoire CI (SCRC)",    "secteur": "agro",         "halal": True},
    "PALC": {"nom": "Palm CI",                 "secteur": "agro",         "halal": True},
    "SOGC": {"nom": "SOGB CI",                 "secteur": "agro",         "halal": True},
    "NTLC": {"nom": "Nestle CI",               "secteur": "alimentation", "halal": True},
    "UNLC": {"nom": "Unilever CI",             "secteur": "alimentation", "halal": True},
    "SAPH": {"nom": "SAPH CI",                 "secteur": "agro",         "halal": True},
    # Energie
    "TTLC": {"nom": "TotalEnergies CI",        "secteur": "energie",      "halal": True},
    "TTLS": {"nom": "TotalEnergies SN",        "secteur": "energie",      "halal": True},
    "SMBC": {"nom": "SMB CI",                  "secteur": "energie",      "halal": True},
    # Télécom
    "SNTS": {"nom": "Sonatel SN",              "secteur": "telecom",      "halal": True},
    "ONTBF":{"nom": "Onatel BF",               "secteur": "telecom",      "halal": True},
    # Services publics
    "CIEC": {"nom": "CIE CI",                  "secteur": "utilitaire",   "halal": True},
    "SDCC": {"nom": "SODECI CI",               "secteur": "utilitaire",   "halal": True},
    # Industrie / BTP
    "FTSC": {"nom": "Filtisac CI",             "secteur": "industrie",    "halal": True},
    "STAC": {"nom": "Setao CI",                "secteur": "btp",          "halal": True},
    "SICC": {"nom": "SICOR CI",                "secteur": "industrie",    "halal": True},
    "CFAC": {"nom": "CFAO CI",                 "secteur": "distribution", "halal": True},
    # Assurance (revenus mixtes — surveillance)
    "SAFC": {"nom": "SAFCA CI",                "secteur": "assurance",    "halal": None},
    # NON CONFORMES — banques et alcool
    "BOAB": {"nom": "Bank of Africa BN",       "secteur": "banque",       "halal": False},
    "BICC": {"nom": "BICI CI",                 "secteur": "banque",       "halal": False},
    "BICB": {"nom": "BIIC BN",                 "secteur": "banque",       "halal": False},
    "ETIT": {"nom": "Ecobank ETI",             "secteur": "banque",       "halal": False},
    "SGBC": {"nom": "Societe Generale CI",     "secteur": "banque",       "halal": False},
    "SIBC": {"nom": "SIB CI",                  "secteur": "banque",       "halal": False},
    "SLBC": {"nom": "Solibra CI",              "secteur": "alcool",       "halal": False},
}

# Tickers déjà en portefeuille — exclus des nouvelles propositions
# (mis à jour automatiquement depuis portefeuille.json)
PORTEFEUILLE_ACTUEL = {"BOAB", "BICC", "BICB", "ETIT", "SGBC", "SIBC", "SNTS", "SIVC", "TTLC", "NTLC"}

# Fondamentaux de référence — source : rapports annuels BRVM 2024/2025
FONDAMENTAUX = {
    "SCRC": {"per": 8.0,  "div_yield": 3.5,  "croissance_bnf": 12.0, "note": "Fort momentum BNI"},
    "STAC": {"per": 7.0,  "div_yield": 5.2,  "croissance_bnf": 4.0,  "note": "+200% 6 mois — attention au momentum"},
    "CIEC": {"per": 17.0, "div_yield": 3.8,  "croissance_bnf": 8.0,  "note": "TOP 10 BNI +28% — utilitaire défensif"},
    "NTLC": {"per": 14.0, "div_yield": 3.2,  "croissance_bnf": 8.0,  "note": "Déjà en portef. — surveillance"},
    "TTLC": {"per": 19.0, "div_yield": 4.1,  "croissance_bnf": 6.0,  "note": "Déjà en portef. — surveillance"},
    "PALC": {"per": 8.0,  "div_yield": 5.5,  "croissance_bnf": 4.0,  "note": "PER attractif — agro"},
    "SNTS": {"per": 6.9,  "div_yield": 6.1,  "croissance_bnf": 5.0,  "note": "Déjà en portef. — référence"},
    "FTSC": {"per": 1.7,  "div_yield": 4.8,  "croissance_bnf": 3.0,  "note": "PER très bas — valeur cachée ?"},
    "SAPH": {"per": 7.5,  "div_yield": 4.0,  "croissance_bnf": 3.0,  "note": "Secteur agro stable"},
    "SMBC": {"per": 10.0, "div_yield": 4.0,  "croissance_bnf": 5.0,  "note": "Énergie — défensif"},
    "UNLC": {"per": 22.0, "div_yield": 2.8,  "croissance_bnf": 10.0, "note": "PER élevé mais croissance forte"},
    "ONTBF":{"per": 12.7, "div_yield": 5.0,  "croissance_bnf": 7.0,  "note": "Télécom BF — défensif halal"},
    "TTLS": {"per": 15.0, "div_yield": 4.5,  "croissance_bnf": 6.0,  "note": "TotalEnergies SN"},
    "SICC": {"per": 131.0,"div_yield": 0.0,  "croissance_bnf": 0.0,  "note": "PER très élevé — spéculatif"},
    "SOGC": {"per": 13.0, "div_yield": 4.8,  "croissance_bnf": 7.0,  "note": "Agro BCI — défensif"},
    "CFAC": {"per": 59.0, "div_yield": 3.8,  "croissance_bnf": 6.0,  "note": "PER trop élevé"},
    "SDCC": {"per": 16.0, "div_yield": 4.0,  "croissance_bnf": 5.0,  "note": "SODECI — eau CI"},
}

# Données techniques de référence
TECHNIQUE = {
    "SCRC": {"support": 1800, "resistance": 2200, "tendance": "haussiere",  "var_hebdo": +0.74},
    "STAC": {"support": 2400, "resistance": 3600, "tendance": "correction", "var_hebdo": -20.14},
    "CIEC": {"support": 2800, "resistance": 3400, "tendance": "haussiere",  "var_hebdo": -2.97},
    "PALC": {"support": 7500, "resistance": 9000, "tendance": "laterale",   "var_hebdo": -5.81},
    "FTSC": {"support": 2000, "resistance": 2400, "tendance": "laterale",   "var_hebdo": -4.56},
    "SAPH": {"support": 6800, "resistance": 8000, "tendance": "correction", "var_hebdo": -1.95},
    "SMBC": {"support": 10500,"resistance": 12500,"tendance": "laterale",   "var_hebdo": -0.56},
    "UNLC": {"support": 52000,"resistance": 65000,"tendance": "haussiere",  "var_hebdo": -0.86},
    "ONTBF":{"support": 2500, "resistance": 3000, "tendance": "laterale",   "var_hebdo": -2.51},
    "TTLS": {"support": 2900, "resistance": 3600, "tendance": "haussiere",  "var_hebdo": +3.96},
    "SOGC": {"support": 7000, "resistance": 9000, "tendance": "haussiere",  "var_hebdo": -1.25},
    "SDCC": {"support": 6500, "resistance": 8000, "tendance": "haussiere",  "var_hebdo": -1.52},
    "SICC": {"support": 3800, "resistance": 5000, "tendance": "haussiere",  "var_hebdo": +5.63},
}


# ─────────────────────────────────────────────
# SOURCE 1 — TOP 10 BNI FINANCES
# Chargé depuis le dernier rapport analysé
# ─────────────────────────────────────────────

def charger_top10_bni(suivi_data=None):
    """
    Retourne le TOP 10 BNI si disponible dans les données du rapport.
    Format : { "SCRC": {"rang": 1, "perf_6m": 57.59, "cours": 2025} }
    """
    if not suivi_data:
        return {}

    top10_raw = suivi_data.get("top10_bni", [])
    if not top10_raw:
        return {}

    top10 = {}
    for item in top10_raw:
        if item and item.get("ticker"):
            top10[item["ticker"].upper()] = {
                "rang":    item.get("rang"),
                "perf_6m": item.get("performance_6mois_pct"),
                "cours":   item.get("cours"),
            }
    print(f"[opportunites] TOP 10 BNI chargé : {list(top10.keys())}")
    return top10


# ─────────────────────────────────────────────
# SOURCE 2 — COURS BRVM (scraping brvm.org)
# ─────────────────────────────────────────────

def scraper_cours_brvm():
    """Récupère les cours depuis brvm.org"""
    url = "https://www.brvm.org/fr/cours-actions/0"
    headers = {"User-Agent": "Mozilla/5.0"}
    cours = {}

    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        for ticker in UNIVERS.keys():
            idx = r.text.find(ticker)
            if idx > 0:
                fragment = r.text[idx:idx+80]
                nombres = re.findall(r"\d[\d\s]{2,}\d", fragment)
                for n in nombres:
                    val = int(n.replace(" ", ""))
                    if 100 < val < 200000:
                        cours[ticker] = val
                        break

    except Exception as e:
        print(f"[opportunites] Scraping BRVM échoué : {e}")

    # Fallback : derniers cours connus (Weekly BNI semaine 16)
    fallback = {
        "SCRC": 2040,  "STAC": 2755,  "CIEC": 3100,  "PALC": 8100,
        "FTSC": 2200,  "SAPH": 7300,  "SMBC": 11535, "UNLC": 57500,
        "ONTBF": 2720, "TTLS": 3280,  "SICC": 4220,  "SOGC": 7870,
        "SDCC": 7140,  "CFAC": 1545,  "NTLC": 12000, "TTLC": 2795,
        "SNTS": 28495, "SIVC": 2040,
    }
    for t, v in fallback.items():
        if t not in cours:
            cours[t] = v

    return cours


# ─────────────────────────────────────────────
# FILTRES
# ─────────────────────────────────────────────

def filtre_halal(ticker):
    info = UNIVERS.get(ticker, {})
    h = info.get("halal")
    if h is False:
        return False, f"Secteur interdit : {info.get('secteur')}"
    if h is None:
        return False, f"Statut halal incertain : {info.get('secteur')}"
    return True, "Halal confirmé"


def filtre_portefeuille(ticker):
    if ticker in PORTEFEUILLE_ACTUEL:
        return False, "Déjà en portefeuille"
    return True, "Nouvelle ligne"


def filtre_technique(ticker, cours):
    tech = TECHNIQUE.get(ticker)
    if not tech:
        return True, "Pas de données techniques — neutre", 1

    support   = tech["support"]
    tendance  = tech["tendance"]
    var_hebdo = tech.get("var_hebdo", 0)

    pct_vs_support = (cours - support) / support * 100

    if tendance == "correction" and pct_vs_support < 15:
        return True, f"Correction {var_hebdo:+.1f}% — proche support {support:,}", 3
    elif tendance == "haussiere" and pct_vs_support < 12:
        return True, f"Tendance haussière — rebond sur support", 2
    elif tendance == "laterale" and pct_vs_support < 8:
        return True, f"Consolidation — entrée envisageable", 1
    elif tendance == "correction" and var_hebdo < -15:
        return False, f"Correction trop violente {var_hebdo:+.1f}% — attendre stabilisation", 0
    else:
        return True, f"Neutre — surveiller support à {support:,}", 1


def filtre_fondamental(ticker):
    fond = FONDAMENTAUX.get(ticker)
    if not fond:
        return True, "Fondamentaux non disponibles", 1

    per       = fond.get("per", 99)
    div_yield = fond.get("div_yield", 0)
    croissance = fond.get("croissance_bnf", 0)

    score = 0
    notes = []

    if per <= 10:
        score += 3
        notes.append(f"PER très attractif {per}x")
    elif per <= 15:
        score += 2
        notes.append(f"PER raisonnable {per}x")
    elif per <= 20:
        score += 1
        notes.append(f"PER correct {per}x")
    else:
        notes.append(f"PER élevé {per}x")

    if div_yield >= 5:
        score += 2
        notes.append(f"Dividende élevé {div_yield}%")
    elif div_yield >= 3:
        score += 1
        notes.append(f"Dividende {div_yield}%")

    if croissance >= 10:
        score += 2
        notes.append(f"Forte croissance +{croissance}%")
    elif croissance >= 5:
        score += 1
        notes.append(f"Croissance +{croissance}%")

    return True, " · ".join(notes) or "Fondamentaux neutres", score


# ─────────────────────────────────────────────
# SCORING FINAL
# ─────────────────────────────────────────────

def conviction_label(score):
    if score >= 9:  return 5, "Très forte ★★★★★"
    if score >= 7:  return 4, "Forte ★★★★☆"
    if score >= 5:  return 3, "Modérée ★★★☆☆"
    if score >= 3:  return 2, "Faible ★★☆☆☆"
    return 1, "Très faible ★☆☆☆☆"


# ─────────────────────────────────────────────
# POINT D'ENTRÉE PRINCIPAL
# ─────────────────────────────────────────────

def run(cours=None, suivi_data=None, portefeuille_data=None):
    """
    cours          : dict {ticker: prix} depuis veille.py
    suivi_data     : contenu de suivi.json (pour TOP 10 BNI)
    portefeuille_data : contenu de portefeuille.json (pour exclure positions)
    """
    print(f"[opportunites v2] Scan BRVM — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Mise à jour du portefeuille actuel si fourni
    global PORTEFEUILLE_ACTUEL
    if portefeuille_data:
        PORTEFEUILLE_ACTUEL = {
            p["ticker"] for p in portefeuille_data.get("positions", [])
        }
        print(f"[opportunites] Portefeuille actuel : {PORTEFEUILLE_ACTUEL}")

    # Sources de données
    if not cours:
        cours = scraper_cours_brvm()

    top10_bni = charger_top10_bni(suivi_data)

    opportunites = []
    rejets = {"halal": [], "portefeuille": [], "technique": [], "total": 0}

    for ticker, info in UNIVERS.items():
        rejets["total"] += 1
        cours_actuel = cours.get(ticker)
        if not cours_actuel:
            continue

        # Filtre 1 — halal
        ok, raison_halal = filtre_halal(ticker)
        if not ok:
            rejets["halal"].append(ticker)
            continue

        # Filtre 2 — portefeuille
        ok, _ = filtre_portefeuille(ticker)
        if not ok:
            rejets["portefeuille"].append(ticker)
            continue

        # Signal BNI (bonus de score)
        bonus_bni = 0
        signal_bni = None
        if ticker in top10_bni:
            bni = top10_bni[ticker]
            rang = bni.get("rang", 10)
            perf = bni.get("perf_6m", 0)
            bonus_bni = max(0, 5 - rang)  # rang 1 = +4, rang 5 = 0
            signal_bni = f"TOP {rang} BNI — +{perf:.1f}% sur 6 mois"
            print(f"  [BNI] {ticker} dans le TOP {rang}")

        # Filtre 3 — technique
        ok_tech, signal_tech, score_tech = filtre_technique(ticker, cours_actuel)
        if not ok_tech:
            rejets["technique"].append(ticker)
            continue

        # Filtre 4 — fondamental
        _, signal_fond, score_fond = filtre_fondamental(ticker)

        # Score total
        score_total = score_tech + score_fond + bonus_bni
        note, label_conv = conviction_label(score_total)

        fond = FONDAMENTAUX.get(ticker, {})
        tech = TECHNIQUE.get(ticker, {})

        opportunites.append({
            "ticker":      ticker,
            "nom":         info["nom"],
            "secteur":     info["secteur"],
            "cours":       cours_actuel,
            "signal_bni":  signal_bni,
            "bonus_bni":   bonus_bni,
            "signal_tech": signal_tech,
            "signal_fond": signal_fond,
            "tendance":    tech.get("tendance", ""),
            "support":     tech.get("support"),
            "resistance":  tech.get("resistance"),
            "per":         fond.get("per"),
            "div_yield":   fond.get("div_yield"),
            "croissance":  fond.get("croissance_bnf"),
            "note_fond":   fond.get("note", ""),
            "score_total": score_total,
            "note":        note,
            "conviction":  label_conv,
            "halal":       "conforme",
        })

    # Tri : TOP 10 BNI en premier, puis par score décroissant
    opportunites.sort(key=lambda x: (-x["bonus_bni"], -x["score_total"]))
    top5 = opportunites[:5]

    print(f"\n[opportunites v2] {len(opportunites)} opportunités — TOP 5 :")
    print("─" * 55)
    for i, o in enumerate(top5, 1):
        bni_str = f" [{o['signal_bni']}]" if o["signal_bni"] else ""
        print(f"  {i}. {o['ticker']} — {o['nom']}{bni_str}")
        print(f"     Cours : {o['cours']:,} FCFA | Score : {o['score_total']} | {o['conviction']}")
        print(f"     Tech  : {o['signal_tech']}")
        print(f"     Fond  : {o['signal_fond']}")

    print(f"\n  Exclus — halal: {rejets['halal']}")
    print(f"           portef: {rejets['portefeuille']}")
    print(f"           tech  : {rejets['technique']}")

    return {
        "opportunites":     top5,
        "toutes":           opportunites,
        "top10_bni_actif":  bool(top10_bni),
        "nb_bni_detectes":  len([o for o in top5 if o["bonus_bni"] > 0]),
        "rejets":           rejets,
        "date":             datetime.now().strftime("%Y-%m-%d"),
    }


# ─────────────────────────────────────────────
# TEST DIRECT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    # Simule un suivi_data avec le TOP 10 BNI du 13/04/2026
    suivi_test = {
        "top10_bni": [
            {"rang": 1, "ticker": "SCRC", "performance_6mois_pct": 57.59, "cours": 2025},
            {"rang": 2, "ticker": "STAC", "performance_6mois_pct": 200.0, "cours": 3450},
            {"rang": 3, "ticker": "SIVC", "performance_6mois_pct": 356.72,"cours": 3060},
            {"rang": 4, "ticker": "BOABF","performance_6mois_pct": 46.02, "cours": 5680},
            {"rang": 5, "ticker": "SIBC", "performance_6mois_pct": 25.58, "cours": 7095},
            {"rang": 7, "ticker": "SNTS", "performance_6mois_pct": 10.77, "cours": 28800},
            {"rang": 8, "ticker": "TTLC", "performance_6mois_pct": 12.45, "cours": 2800},
            {"rang": 9, "ticker": "CIEC", "performance_6mois_pct": 28.06, "cours": 3195},
        ]
    }

    data = run(suivi_data=suivi_test)

    print("\n" + "═" * 55)
    print("  OPPORTUNITÉS DE LA SEMAINE — PORTEFEUILLE HALAL")
    print("═" * 55)
    for i, o in enumerate(data["opportunites"], 1):
        print(f"\n  {i}. {o['ticker']} — {o['nom']}")
        print(f"     Secteur    : {o['secteur']}")
        print(f"     Cours      : {o['cours']:,} FCFA")
        print(f"     Conviction : {o['conviction']}")
        if o["signal_bni"]:
            print(f"     Signal BNI : {o['signal_bni']} ← SOURCE PRIORITAIRE")
        print(f"     Technique  : {o['signal_tech']}")
        print(f"     Fondamental: {o['signal_fond']}")
        if o["per"]:
            print(f"     PER {o['per']}x | Div {o['div_yield']}% | Croiss. +{o['croissance']}%")
        if o["note_fond"]:
            print(f"     Note       : {o['note_fond']}")

    print(f"\n  Sources BNI actives : {data['top10_bni_actif']}")
    print(f"  Valeurs BNI dans le top : {data['nb_bni_detectes']}/5")
