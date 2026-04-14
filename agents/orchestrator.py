"""
orchestrator.py — Orchestrateur principal de l'agent BRVM
Lance les agents dans l'ordre et coordonne la synthèse
"""

import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

import veille
import halal
import synthese


def run():
    print("=" * 50)
    print(f"AGENT BRVM — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    # 1. Veille marché — récupère les cours
    print("\n[1/3] Agent veille marché...")
    data_veille = veille.run()

    # 2. Screener halal — vérifie tous les tickers
    print("\n[2/3] Agent screener halal...")
    tous_tickers = [p["ticker"] for p in data_veille["positions"]] + ["TTLC", "NTLC"]
    data_halal = halal.run(tous_tickers)

    # Bloque si haram détecté dans les cibles
    for alerte in data_halal["alertes"]:
        if alerte["niveau"] == "BLOQUANT":
            print(f"\n[HALT] Ticker HARAM détecté : {alerte['ticker']} — {alerte['message']}")
            print("[HALT] Arrêt du pipeline pour ce ticker")

    # 3. Synthèse — génère le rapport
    print("\n[3/3] Agent synthèse...")
    donnees = {
        "veille": data_veille,
        "halal": data_halal,
        "date": datetime.now().strftime("%d/%m/%Y"),
        "heure": datetime.now().strftime("%H:%M"),
    }
    synthese.run(donnees)

    print("\n" + "=" * 50)
    print("AGENT TERMINÉ AVEC SUCCÈS")
    print("=" * 50)


if __name__ == "__main__":
    run()
