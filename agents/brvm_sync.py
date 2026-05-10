"""
brvm_sync.py — Script Claude Code
Déclenché par GitHub Actions via repository_dispatch (Zapier → Drive → GitHub)
1. Télécharge le PDF BNI depuis Google Drive
2. Analyse le contenu avec l'API Anthropic
3. Met à jour suivi.json et portefeuille.json
4. Commit et push automatique
"""

import os
import json
import base64
import subprocess
from datetime import datetime
from pathlib import Path

import anthropic
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io


# ─────────────────────────────────────────────
# CONFIG — depuis les secrets GitHub Actions
# ─────────────────────────────────────────────

ANTHROPIC_API_KEY   = os.environ["ANTHROPIC_API_KEY"]
GOOGLE_CREDS_JSON   = os.environ["GOOGLE_CREDS_JSON"]    # JSON base64 du compte de service
DRIVE_FOLDER_ID     = os.environ["DRIVE_FOLDER_ID"]      # ID du dossier Drive BNI
REPORT_EMAIL        = os.environ.get("REPORT_EMAIL", "")

DATA_DIR = Path(__file__).parent.parent / "data"


# ─────────────────────────────────────────────
# 1. TÉLÉCHARGEMENT PDF DEPUIS GOOGLE DRIVE
# ─────────────────────────────────────────────

def get_drive_service():
    creds_data = json.loads(base64.b64decode(GOOGLE_CREDS_JSON).decode())
    creds = Credentials.from_service_account_info(
        creds_data,
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build("drive", "v3", credentials=creds)


def telecharger_dernier_pdf(service):
    """Récupère le PDF le plus récent dans le dossier Drive BNI"""
    results = service.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents and mimeType='application/pdf' and trashed=false",
        orderBy="createdTime desc",
        pageSize=1,
        fields="files(id, name, createdTime)"
    ).execute()

    fichiers = results.get("files", [])
    if not fichiers:
        raise FileNotFoundError("Aucun PDF trouvé dans le dossier Drive BNI")

    fichier = fichiers[0]
    print(f"[sync] PDF trouvé : {fichier['name']} ({fichier['createdTime']})")

    request = service.files().get_media(fileId=fichier["id"])
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    buffer.seek(0)
    return buffer.read(), fichier["name"]


# ─────────────────────────────────────────────
# 2. ANALYSE DU PDF AVEC CLAUDE
# ─────────────────────────────────────────────

PROMPT_ANALYSE = """
Tu es un assistant d'analyse financière spécialisé BRVM pour un investisseur halal.

Analyse ce rapport BNI Finances et extrais UNIQUEMENT les informations suivantes en JSON strict.
Ne retourne QUE le JSON, sans texte avant ou après, sans backticks.

{
  "type_rapport": "weekly|avis_opere|releve|top10|marche_primaire",
  "date": "YYYY-MM-DD",
  "marche": {
    "brvm_composite": null,
    "variation_hebdo": null,
    "tendance": "hausse|baisse|stable"
  },
  "dividendes": [
    {
      "ticker": "BOAB",
      "dividende_net": 594.53,
      "ex_div": "2026-05-05",
      "paiement": "2026-05-06",
      "rendement_pct": 6.91
    }
  ],
  "cours": [
    {
      "ticker": "SNTS",
      "cours": 28495,
      "variation_hebdo_pct": -1.06,
      "volume": 88217,
      "per": 6.89
    }
  ],
  "operations": [
    {
      "type": "achat|vente",
      "ticker": "TTLC",
      "quantite": 169,
      "cours": 2840,
      "montant_brut": 479960,
      "frais": 6719,
      "total": 486678,
      "date": "2026-04-15",
      "ordre": "148384"
    }
  ],
  "alertes": [
    {
      "ticker": "ETIT",
      "type": "baisse_forte|hausse|dividende|aga|age",
      "detail": "chute -23.53% semaine 16"
    }
  ],
  "top10_bni": [
    {
      "rang": 1,
      "ticker": "SCRC",
      "performance_6mois_pct": 57.59,
      "cours": 2025
    }
  ]
}

Si un champ n'est pas dans le document, mets null.
Pour "operations", n'inclus que les opérations réelles confirmées (avis d'opéré).
"""


def analyser_pdf(pdf_bytes):
    """Envoie le PDF à Claude pour extraction structurée"""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": PROMPT_ANALYSE
                    }
                ],
            }
        ],
    )

    texte = message.content[0].text.strip()
    # Nettoie les backticks éventuels
    if texte.startswith("```"):
        texte = texte.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    return json.loads(texte)


# ─────────────────────────────────────────────
# 3. MISE À JOUR DES FICHIERS JSON
# ─────────────────────────────────────────────

def charger_json(nom):
    chemin = DATA_DIR / nom
    if chemin.exists():
        with open(chemin, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def sauvegarder_json(nom, data):
    chemin = DATA_DIR / nom
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[sync] {nom} mis à jour")


def mettre_a_jour_suivi(donnees, suivi):
    """Met à jour le suivi.json avec les nouvelles données"""
    aujourd_hui = datetime.now().strftime("%Y-%m-%d")
    suivi["derniere_maj"] = aujourd_hui

    actions = suivi.get("actions", [])

    # Marque les opérations réalisées
    for op in donnees.get("operations", []) or []:
        if not op:
            continue
        ticker = op.get("ticker", "").upper()
        type_op = op.get("type", "")
        date_op = op.get("date", aujourd_hui)

        # Cherche une action en attente correspondante
        for action in actions:
            if (action["statut"] == "en_attente"
                    and ticker in action.get("detail", "").upper()
                    and type_op in action.get("titre", "").lower()):
                action["statut"] = "realise"
                action["date_realisation"] = date_op
                action["note"] = (
                    f"Auto-détecté : {op.get('quantite')} titres "
                    f"à {op.get('cours')} FCFA"
                )
                print(f"[sync] Action {action['id']} marquée réalisée")
                break

    # Ajoute les alertes comme nouvelles actions si importantes
    for alerte in donnees.get("alertes", []) or []:
        if not alerte:
            continue
        type_alerte = alerte.get("type", "")
        ticker = alerte.get("ticker", "")
        detail = alerte.get("detail", "")

        if type_alerte == "baisse_forte":
            # Vérifie qu'une alerte similaire n'existe pas déjà
            existe = any(
                a.get("statut") in ("en_attente", "en_cours")
                and ticker in a.get("detail", "")
                for a in actions
            )
            if not existe:
                nouvel_id = f"A{len(actions) + 1:03d}"
                actions.append({
                    "id": nouvel_id,
                    "titre": f"Surveiller {ticker}",
                    "detail": f"{ticker} — {detail}",
                    "statut": "en_attente",
                    "date_cible": None,
                    "date_realisation": None,
                    "note": f"Auto-ajouté le {aujourd_hui}"
                })
                print(f"[sync] Nouvelle alerte {nouvel_id} : {ticker}")

    # Met à jour le calendrier des dividendes
    divs_existants = {
        d["ticker"]: d
        for d in suivi.get("dividendes_a_venir", [])
    }
    for div in donnees.get("dividendes", []) or []:
        if not div or not div.get("ticker"):
            continue
        ticker = div["ticker"]
        divs_existants[ticker] = {
            "ticker":           ticker,
            "dividende_net":    div.get("dividende_net"),
            "ex_div":           div.get("ex_div"),
            "paiement":         div.get("paiement"),
            "rendement_pct":    div.get("rendement_pct"),
        }

    suivi["actions"] = actions
    suivi["dividendes_a_venir"] = list(divs_existants.values())
    return suivi


def mettre_a_jour_portefeuille(donnees, portefeuille):
    """Met à jour les cours de référence dans portefeuille.json"""
    cours_map = {
        c["ticker"]: c["cours"]
        for c in (donnees.get("cours") or [])
        if c and c.get("ticker") and c.get("cours")
    }

    for position in portefeuille.get("positions", []):
        ticker = position.get("ticker")
        if ticker in cours_map:
            position["cours_ref"] = cours_map[ticker]
            cmp = position.get("cmp") or position.get("cmp_initial")
            if cmp and cours_map[ticker]:
                position["pv_latente"] = (cours_map[ticker] - cmp) * position["quantite"]

    # Met à jour les opérations réalisées dans les positions
    for op in (donnees.get("operations") or []):
        if not op:
            continue
        ticker = op.get("ticker", "").upper()
        type_op = op.get("type", "")
        qte = op.get("quantite", 0)
        cours = op.get("cours", 0)

        if type_op == "achat":
            # Cherche si position existante
            existante = next(
                (p for p in portefeuille["positions"] if p["ticker"] == ticker),
                None
            )
            if existante:
                # Met à jour la quantité et le CMP
                q_avant = existante["quantite"]
                cmp_avant = existante.get("cmp") or existante.get("cmp_initial", cours)
                nouvelle_qte = q_avant + qte
                nouveau_cmp = (q_avant * cmp_avant + qte * cours) / nouvelle_qte
                existante["quantite"] = nouvelle_qte
                existante["cmp"] = round(nouveau_cmp)
                print(f"[sync] {ticker} renforcé : {q_avant} → {nouvelle_qte} titres")
            else:
                # Nouvelle position
                portefeuille["positions"].append({
                    "ticker":    ticker,
                    "nom":       ticker,
                    "quantite":  qte,
                    "cmp":       cours,
                    "cours_ref": cours,
                    "secteur":   "inconnu",
                    "halal":     "a_verifier",
                    "note":      f"Ouvert le {op.get('date', datetime.now().strftime('%Y-%m-%d'))}"
                })
                print(f"[sync] Nouvelle position : {ticker} {qte} titres")

        elif type_op == "vente":
            for p in portefeuille["positions"]:
                if p["ticker"] == ticker:
                    p["quantite"] = max(0, p["quantite"] - qte)
                    if p["quantite"] == 0:
                        portefeuille["positions"].remove(p)
                        print(f"[sync] {ticker} soldé")
                    break

    portefeuille["date_maj"] = datetime.now().strftime("%Y-%m-%d")
    return portefeuille


# ─────────────────────────────────────────────
# 4. GIT COMMIT + PUSH
# ─────────────────────────────────────────────

def git_push(message):
    """Configure git et pousse les changements"""
    cmds = [
        ["git", "config", "user.email", "brvm-agent@github-actions"],
        ["git", "config", "user.name", "BRVM Agent"],
        ["git", "add", "data/suivi.json", "data/portefeuille.json"],
        ["git", "commit", "-m", message],
        ["git", "push", "origin", "master"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            if "nothing to commit" in result.stdout:
                print("[sync] Rien à commiter — fichiers inchangés")
                return
            print(f"[git] Erreur : {result.stderr}")
            raise RuntimeError(f"Git error: {result.stderr}")
    print(f"[sync] Push réussi : {message}")


# ─────────────────────────────────────────────
# POINT D'ENTRÉE PRINCIPAL
# ─────────────────────────────────────────────

def run():
    print("=" * 50)
    print(f"BRVM SYNC — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    # 1. Téléchargement PDF
    print("\n[1/4] Connexion Google Drive...")
    service = get_drive_service()
    pdf_bytes, nom_pdf = telecharger_dernier_pdf(service)
    print(f"[1/4] PDF téléchargé : {len(pdf_bytes)} octets")

    # 2. Analyse Claude
    print("\n[2/4] Analyse du PDF avec Claude...")
    donnees = analyser_pdf(pdf_bytes)
    print(f"[2/4] Type rapport : {donnees.get('type_rapport')} — {donnees.get('date')}")
    print(f"      Opérations : {len(donnees.get('operations') or [])}")
    print(f"      Dividendes : {len(donnees.get('dividendes') or [])}")
    print(f"      Alertes    : {len(donnees.get('alertes') or [])}")

    # 3. Mise à jour fichiers
    print("\n[3/4] Mise à jour des fichiers JSON...")
    suivi       = charger_json("suivi.json")
    portefeuille = charger_json("portefeuille.json")

    suivi        = mettre_a_jour_suivi(donnees, suivi)
    portefeuille = mettre_a_jour_portefeuille(donnees, portefeuille)

    sauvegarder_json("suivi.json", suivi)
    sauvegarder_json("portefeuille.json", portefeuille)

    # 4. Git push
    print("\n[4/4] Commit et push Git...")
    date_str = donnees.get("date", datetime.now().strftime("%Y-%m-%d"))
    type_str = donnees.get("type_rapport", "rapport")
    git_push(f"auto-sync {type_str} {date_str} — {nom_pdf}")

    print("\n" + "=" * 50)
    print("SYNC TERMINÉ AVEC SUCCÈS")
    print("=" * 50)


if __name__ == "__main__":
    run()
