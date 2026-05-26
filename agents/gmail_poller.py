"""
gmail_poller.py — Remplace Zapier
Vérifie Gmail toutes les heures depuis GitHub Actions.
Détecte les nouveaux emails BNI Finances avec pièces jointes PDF.
Télécharge le PDF et déclenche le pipeline brvm_sync.
"""

import os
import json
import base64
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Google API
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as SACredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

GOOGLE_CREDS_JSON = os.environ["GOOGLE_CREDS_JSON"]   # compte de service base64
DRIVE_FOLDER_ID   = os.environ["DRIVE_FOLDER_ID"]      # dossier BNI-BRVM Drive
GMAIL_USER        = os.environ.get("REPORT_EMAIL", "habibcisse5@gmail.com")

# Fichier de suivi des emails déjà traités
DATA_DIR      = Path(__file__).parent.parent / "data"
PROCESSED_FILE = DATA_DIR / "gmail_processed.json"

# Fenêtre de recherche : emails des dernières 48h
HEURES_LOOKBACK = 48

# Mots-clés pour détecter les emails BNI
BNI_SENDERS = ["bnifinances@bnifinances.ci", "bnifinances.ci"]
BNI_SUBJECTS = ["weekly", "bni finances", "notes de synthese", "top 10", "marche primaire"]


# ─────────────────────────────────────────────
# 1. SERVICES GOOGLE
# ─────────────────────────────────────────────

def get_services():
    """Crée les services Gmail et Drive avec le compte de service"""
    creds_data = json.loads(base64.b64decode(GOOGLE_CREDS_JSON).decode())
    
    # Compte de service avec délégation de domaine
    creds = SACredentials.from_service_account_info(
        creds_data,
        scopes=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/drive",
        ]
    )
    
    # Délégation vers l'utilisateur Gmail
    creds_delegated = creds.with_subject(GMAIL_USER)
    
    gmail_service = build("gmail", "v1", credentials=creds_delegated)
    drive_service = build("drive", "v3", credentials=creds_delegated)
    
    return gmail_service, drive_service


# ─────────────────────────────────────────────
# 2. LECTURE DES EMAILS TRAITÉS
# ─────────────────────────────────────────────

def charger_traites():
    """Charge la liste des message IDs déjà traités"""
    if PROCESSED_FILE.exists():
        with open(PROCESSED_FILE, "r") as f:
            return json.load(f)
    return {"processed_ids": [], "last_check": None}


def sauvegarder_traites(data):
    """Sauvegarde la liste des messages traités"""
    DATA_DIR.mkdir(exist_ok=True)
    with open(PROCESSED_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ─────────────────────────────────────────────
# 3. RECHERCHE DES EMAILS BNI
# ─────────────────────────────────────────────

def chercher_emails_bni(gmail_service):
    """Cherche les emails BNI récents avec pièces jointes"""
    
    # Calcule la date de début (48h en arrière)
    date_limite = datetime.now(timezone.utc) - timedelta(hours=HEURES_LOOKBACK)
    timestamp = int(date_limite.timestamp())
    
    # Requête Gmail
    query = f"from:bnifinances has:attachment after:{timestamp}"
    
    try:
        results = gmail_service.users().messages().list(
            userId="me",
            q=query,
            maxResults=10
        ).execute()
        
        messages = results.get("messages", [])
        print(f"[poller] {len(messages)} email(s) BNI trouvé(s) dans les {HEURES_LOOKBACK}h")
        return messages
        
    except Exception as e:
        print(f"[poller] Erreur recherche Gmail : {e}")
        return []


# ─────────────────────────────────────────────
# 4. TÉLÉCHARGEMENT DES PIÈCES JOINTES
# ─────────────────────────────────────────────

def telecharger_attachments(gmail_service, drive_service, message_id):
    """Télécharge les PDF d'un email et les dépose dans Drive"""
    
    try:
        # Récupère le message complet
        message = gmail_service.users().messages().get(
            userId="me",
            id=message_id,
            format="full"
        ).execute()
        
        # Extrait le sujet
        headers = message.get("payload", {}).get("headers", [])
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "BNI")
        date_email = next((h["value"] for h in headers if h["name"] == "Date"), "")
        
        print(f"[poller] Email : {subject}")
        
        # Parcourt les parties pour trouver les PDF
        pdfs_deposes = []
        
        def extraire_parts(payload):
            parts = payload.get("parts", [])
            
            # Cas simple : pièce jointe directe
            if payload.get("filename") and payload.get("filename", "").lower().endswith(".pdf"):
                parts = [payload]
            
            for part in parts:
                filename = part.get("filename", "")
                mime_type = part.get("mimeType", "")
                
                # Récursion pour les parties imbriquées
                if part.get("parts"):
                    extraire_parts(part)
                    continue
                
                if not filename.lower().endswith(".pdf"):
                    continue
                    
                print(f"[poller] PDF détecté : {filename}")
                
                # Télécharge la pièce jointe
                body = part.get("body", {})
                attachment_id = body.get("attachmentId")
                
                if attachment_id:
                    attachment = gmail_service.users().messages().attachments().get(
                        userId="me",
                        messageId=message_id,
                        id=attachment_id
                    ).execute()
                    
                    pdf_data = base64.urlsafe_b64decode(attachment["data"])
                else:
                    pdf_data = base64.urlsafe_b64decode(body.get("data", ""))
                
                if not pdf_data:
                    continue
                
                # Nom du fichier
                safe_subject = subject[:50].replace("/", "-").replace("\\", "-")
                nom_fichier = f"BNI_{safe_subject}_{datetime.now().strftime('%Y%m%d')}.pdf"
                
                # Dépose dans Google Drive
                from googleapiclient.http import MediaInMemoryUpload
                
                media = MediaInMemoryUpload(pdf_data, mimetype="application/pdf")
                
                file_metadata = {
                    "name": nom_fichier,
                    "parents": [DRIVE_FOLDER_ID],
                }
                
                fichier = drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields="id,name"
                ).execute()
                
                print(f"[poller] Déposé dans Drive : {fichier['name']} ({fichier['id']})")
                pdfs_deposes.append(fichier["name"])
        
        extraire_parts(message.get("payload", {}))
        return pdfs_deposes
        
    except Exception as e:
        print(f"[poller] Erreur téléchargement : {e}")
        return []


# ─────────────────────────────────────────────
# 5. GIT COMMIT DES FICHIERS TRAITÉS
# ─────────────────────────────────────────────

def git_commit_processed():
    """Commit le fichier gmail_processed.json pour éviter les doublons"""
    cmds = [
        ["git", "config", "user.email", "brvm-agent@github-actions"],
        ["git", "config", "user.name", "BRVM Agent"],
        ["git", "add", "data/gmail_processed.json"],
        ["git", "commit", "-m", f"update gmail processed — {datetime.now().strftime('%Y-%m-%d %H:%M')}"],
        ["git", "push", "origin", "master"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            if "nothing to commit" in result.stdout:
                return
            print(f"[git] {result.stderr}")


# ─────────────────────────────────────────────
# POINT D'ENTRÉE PRINCIPAL
# ─────────────────────────────────────────────

def run():
    """
    Retourne True si de nouveaux PDFs ont été déposés dans Drive,
    False sinon. L'orchestrateur GitHub Actions décide de lancer
    brvm_sync.py seulement si True.
    """
    print("=" * 50)
    print(f"GMAIL POLLER — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)
    
    # Charge les emails déjà traités
    traites = charger_traites()
    processed_ids = set(traites.get("processed_ids", []))
    
    # Connexion aux services Google
    print("\n[1/3] Connexion Gmail + Drive...")
    try:
        gmail_service, drive_service = get_services()
    except Exception as e:
        print(f"[poller] Erreur connexion : {e}")
        return False
    
    # Cherche les emails BNI récents
    print("\n[2/3] Recherche emails BNI...")
    messages = chercher_emails_bni(gmail_service)
    
    nouveaux_pdfs = 0
    
    for message in messages:
        msg_id = message["id"]
        
        # Déjà traité ?
        if msg_id in processed_ids:
            print(f"[poller] Message {msg_id} déjà traité — ignoré")
            continue
        
        # Télécharge et dépose dans Drive
        print(f"\n[3/3] Traitement message {msg_id}...")
        pdfs = telecharger_attachments(gmail_service, drive_service, msg_id)
        
        if pdfs:
            nouveaux_pdfs += len(pdfs)
            processed_ids.add(msg_id)
            print(f"[poller] {len(pdfs)} PDF(s) déposé(s) dans Drive")
    
    # Sauvegarde les IDs traités
    traites["processed_ids"] = list(processed_ids)[-100:]  # garde les 100 derniers
    traites["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    sauvegarder_traites(traites)
    
    if nouveaux_pdfs > 0:
        git_commit_processed()
        print(f"\n[poller] {nouveaux_pdfs} nouveau(x) PDF(s) — pipeline à lancer")
        return True
    else:
        print("\n[poller] Aucun nouveau PDF — pipeline non lancé")
        return False


if __name__ == "__main__":
    nouveau = run()
    # Code de sortie utilisé par le workflow GitHub Actions
    # 0 = pas de nouveau PDF
    # 10 = nouveaux PDFs détectés → lancer brvm_sync
    exit(10 if nouveau else 0)
