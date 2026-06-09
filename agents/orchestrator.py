"""
orchestrator.py v3 — Orchestrateur principal agent BRVM
Pipeline complet 6 agents :
  1. veille.py       — cours BRVM en direct
  2. halal.py        — screener charia 3 niveaux
  3. analyse.py      — signaux techniques
  4. risque.py       — concentration + stop-loss
  5. opportunites.py — suggestions nouvelles lignes (TOP 10 BNI + scraping)
  6. synthese.py     — rapport HTML + email
"""

import sys
import os
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

import veille
import halal
import analyse
import risque
import opportunites
import synthese


DATA_DIR = Path(__file__).parent.parent / "data"


def charger_json(nom):
    chemin = DATA_DIR / nom
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[orchestrateur] {nom} introuvable")
        return {}
    except json.JSONDecodeError as e:
        print(f"[orchestrateur] {nom} corrompu : {e}")
        return {}


def sep(titre=""):
    ligne = "─" * 55
    print(f"\n{ligne}")
    if titre:
        print(f"  {titre}")
        print(ligne)


def run():
    print("=" * 55)
    print(f"  AGENT BRVM v3 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 55)
    debut = datetime.now()

    # Données statiques
    portefeuille = charger_json("portefeuille.json")
    suivi        = charger_json("suivi.json")

    if suivi:
        en_attente = [a for a in suivi.get("actions", []) if a["statut"] == "en_attente"]
        print(f"\n[suivi] {len(en_attente)} action(s) en attente :")
        for a in en_attente[:3]:
            print(f"  → {a['id']} : {a['titre']}")

    # 1. Veille marché
    sep("1/6 — Veille marché")
    data_veille = veille.run()

    # 2. Screener halal
    sep("2/6 — Screener halal")
    tous_tickers = list(set(
        [p["ticker"] for p in data_veille["positions"]]
        + ["TTLC", "NTLC", "SCRC", "STAC", "CIEC", "PALC", "SAPH", "SMBC", "ONTBF"]
    ))
    data_halal = halal.run(tous_tickers)

    haram_detectes = [
        a["ticker"] for a in data_halal["alertes"]
        if a["niveau"] == "BLOQUANT"
        and data_halal["resultats"].get(a["ticker"], {}).get("statut") == "haram"
    ]
    if haram_detectes:
        print(f"\n[VETO HARAM] Bloqués : {haram_detectes}")

    # 3. Analyse technique
    sep("3/6 — Analyse technique")
    data_analyse = analyse.run(
        data_veille["cours"],
        data_veille["positions"]
    )

    # 4. Gestion de risque
    sep("4/6 — Gestion de risque")
    data_risque = risque.run(
        data_veille["cours"],
        data_veille["positions"],
        data_halal["resultats"],
    )
    if data_risque["score_risque"] >= 70:
        print(f"\n[ALERTE CRITIQUE] Score risque : {data_risque['score_risque']}/100")

    # 5. Opportunités — TOP 10 BNI + scraping
    sep("5/6 — Opportunités halal")
    data_opportunites = opportunites.run(
        cours=data_veille["cours"],
        suivi_data=suivi,
        portefeuille_data=portefeuille,
    )
    # Filtre final veto haram
    data_opportunites["opportunites"] = [
        o for o in data_opportunites["opportunites"]
        if o["ticker"] not in haram_detectes
    ]

    # 6. Synthèse et rapport
    sep("6/6 — Synthèse et rapport")
    donnees = {
        "veille":       data_veille,
        "halal":        data_halal,
        "analyse":      data_analyse,
        "risque":       data_risque,
        "opportunites": data_opportunites,
        "suivi":        suivi,
        "portefeuille": portefeuille,
        "date":         datetime.now().strftime("%d/%m/%Y"),
        "heure":        datetime.now().strftime("%H:%M"),
    }
    synthese.run(donnees)

    # Résumé
    duree = (datetime.now() - debut).seconds
    print("\n" + "=" * 55)
    print("  RÉSUMÉ")
    print("=" * 55)
    print(f"  Durée           : {duree}s")
    print(f"  Cours récupérés : {len(data_veille['cours'])}")
    print(f"  Score risque    : {data_risque['score_risque']}/100")
    print(f"  Part halal      : {data_risque['poids_halal']}%")
    print(f"  Alertes risque  : {len(data_risque['alertes'])}")
    print(f"  Alertes halal   : {len(data_halal['alertes'])}")

    signaux = [
        t for t, d in {
            **data_analyse.get("positions", {}),
            **data_analyse.get("cibles", {})
        }.items()
        if d["signal"]["signal"] == "ACHETER"
        and t not in haram_detectes
    ]
    if signaux:
        print(f"  Signaux ACHETER : {signaux}")

    if data_opportunites["opportunites"]:
        print(f"\n  TOP OPPORTUNITÉS HALAL :")
        for o in data_opportunites["opportunites"][:3]:
            bni = " [BNI]" if o.get("bonus_bni", 0) > 0 else ""
            print(f"  {'★' * o['note']} {o['ticker']} — {o['nom']}{bni}")
            print(f"    {o['conviction']} | {o['signal_tech']}")

    print(f"\n  Dashboard : https://habibcisse5.github.io/brvm-agent/")
    print("=" * 55)
    print("  TERMINÉ AVEC SUCCÈS")
    print("=" * 55)


if __name__ == "__main__":
    run()
