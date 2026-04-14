"""
orchestrator.py v2 — Orchestrateur principal agent BRVM
Pipeline complet : veille → halal → analyse → risque → synthèse
"""

import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

import veille
import halal
import analyse
import risque
import synthese


def charger_portefeuille():
    """Charge les données du portefeuille depuis data/portefeuille.json"""
    chemin = os.path.join(os.path.dirname(__file__), "..", "data", "portefeuille.json")
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print("[orchestrateur] data/portefeuille.json introuvable — utilisation des valeurs par défaut")
        return None


def charger_suivi():
    """Charge le fichier de suivi des actions"""
    chemin = os.path.join(os.path.dirname(__file__), "..", "data", "suivi.json")
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def run():
    print("=" * 55)
    print(f"  AGENT BRVM v2 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 55)

    # ── Chargement des données statiques ──────────────────
    portefeuille = charger_portefeuille()
    suivi        = charger_suivi()

    if suivi:
        actions_attente = [a for a in suivi.get("actions", []) if a["statut"] == "en_attente"]
        print(f"\n[suivi] {len(actions_attente)} action(s) en attente")

    # ── 1. VEILLE MARCHÉ ──────────────────────────────────
    print("\n[1/5] Agent veille marché...")
    data_veille = veille.run()

    # ── 2. SCREENER HALAL ────────────────────────────────
    print("\n[2/5] Agent screener halal...")
    tous_tickers = [p["ticker"] for p in data_veille["positions"]] + ["TTLC", "NTLC"]
    data_halal   = halal.run(tous_tickers)

    # Veto absolu sur les tickers haram
    haram_detectes = [
        a["ticker"] for a in data_halal["alertes"]
        if a["niveau"] == "BLOQUANT"
        and data_halal["resultats"].get(a["ticker"], {}).get("verdict") == "HARAM"
    ]
    if haram_detectes:
        print(f"\n[HALT] Tickers HARAM détectés : {haram_detectes}")
        print("[HALT] Ces tickers sont exclus de toute recommandation d'achat")

    # ── 3. ANALYSE TECHNIQUE ─────────────────────────────
    print("\n[3/5] Agent analyste technique...")
    data_analyse = analyse.run(data_veille["cours"], data_veille["positions"])

    # ── 4. GESTION DE RISQUE ─────────────────────────────
    print("\n[4/5] Agent gestion de risque...")
    data_risque = risque.run(
        data_veille["cours"],
        data_veille["positions"],
        data_halal["resultats"],
    )

    # Blocage si score de risque critique
    if data_risque["score_risque"] >= 70:
        print(f"\n[ALERTE RISQUE] Score {data_risque['score_risque']}/100 — portefeuille en zone critique")

    # ── 5. SYNTHÈSE ET RAPPORT ───────────────────────────
    print("\n[5/5] Agent synthèse...")
    donnees = {
        "veille":   data_veille,
        "halal":    data_halal,
        "analyse":  data_analyse,
        "risque":   data_risque,
        "suivi":    suivi,
        "date":     datetime.now().strftime("%d/%m/%Y"),
        "heure":    datetime.now().strftime("%H:%M"),
    }
    synthese.run(donnees)

    # ── RÉSUMÉ CONSOLE ───────────────────────────────────
    print("\n" + "=" * 55)
    print("  RÉSUMÉ DU RUN")
    print("=" * 55)
    print(f"  Cours récupérés    : {len(data_veille['cours'])}")
    print(f"  Score risque       : {data_risque['score_risque']}/100")
    print(f"  Part halal         : {data_risque['poids_halal']}%")
    print(f"  Alertes risque     : {len(data_risque['alertes'])}")
    print(f"  Alertes halal      : {len(data_halal['alertes'])}")

    signaux_achat = [
        t for t, d in {**data_analyse["positions"], **data_analyse["cibles"]}.items()
        if d["signal"]["signal"] == "ACHETER"
        and t not in haram_detectes
    ]
    if signaux_achat:
        print(f"  Signaux ACHETER    : {signaux_achat}")

    print("\n  Dashboard : https://habibcisse5.github.io/brvm-agent/")
    print("=" * 55)
    print("  AGENT TERMINÉ AVEC SUCCÈS")
    print("=" * 55)


if __name__ == "__main__":
    run()
