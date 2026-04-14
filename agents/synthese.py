"""
synthese.py — Agent synthèse BRVM
Génère le rapport HTML à partir des données des autres agents
et l'envoie par email via Gmail SMTP
"""

import os
import json
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from jinja2 import Template


TEMPLATE_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Synthèse BRVM — {{ date }}</title>
<style>
  :root { --up:#27500A; --dn:#791F1F; --warn:#633806; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:#f5f4ef; color:#1a1a18; padding:2rem 1rem; }
  .container { max-width:860px; margin:0 auto; }
  h1 { font-size:24px; font-weight:400; margin-bottom:4px; }
  .subtitle { font-size:13px; color:#6b6a63; margin-bottom:1.5rem; font-family:monospace; }
  .metrics { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-bottom:1.5rem; }
  .m { background:#fff; border-radius:10px; padding:14px; border:0.5px solid rgba(0,0,0,.1); }
  .ml { font-size:11px; color:#6b6a63; text-transform:uppercase; letter-spacing:.05em; margin-bottom:4px; }
  .mv { font-size:20px; }
  .up { color:var(--up); } .dn { color:var(--dn); }
  table { width:100%; border-collapse:collapse; font-size:13px; background:#fff; border-radius:12px; overflow:hidden; border:0.5px solid rgba(0,0,0,.1); margin-bottom:1.5rem; }
  th { background:#f5f4ef; font-size:11px; color:#6b6a63; padding:8px 12px; text-align:left; border-bottom:0.5px solid rgba(0,0,0,.1); text-transform:uppercase; }
  td { padding:9px 12px; border-bottom:0.5px solid rgba(0,0,0,.06); }
  .badge { font-size:11px; padding:2px 8px; border-radius:20px; font-weight:600; }
  .b-halal { background:#EAF3DE; color:#27500A; }
  .b-warn  { background:#FAEEDA; color:#633806; }
  .b-alert { background:#FCEBEB; color:#791F1F; }
  .alert { border-left:3px solid; padding:10px 14px; margin-bottom:10px; border-radius:0 8px 8px 0; font-size:13px; line-height:1.6; }
  .a-red  { border-color:#E24B4A; background:#FCEBEB; color:#791F1F; }
  .a-warn { border-color:#BA7517; background:#FAEEDA; color:#633806; }
  .a-ok   { border-color:#1D9E75; background:#EAF3DE; color:#27500A; }
  .a-info { border-color:#378ADD; background:#E6F1FB; color:#0C447C; }
  .sec { font-size:10px; font-weight:700; color:#9b9a93; text-transform:uppercase; letter-spacing:.10em; margin:1.5rem 0 .6rem; }
  .footer { margin-top:2rem; font-size:11px; color:#9b9a93; text-align:center; font-family:monospace; border-top:0.5px solid rgba(0,0,0,.1); padding-top:1rem; }
  .action-item { display:flex; gap:10px; padding:10px 12px; border:0.5px solid rgba(0,0,0,.1); border-radius:8px; margin-bottom:8px; background:#fff; font-size:13px; }
  .action-num { min-width:22px; height:22px; border-radius:50%; background:#EEEDFE; color:#3C3489; font-size:11px; font-weight:600; display:flex; align-items:center; justify-content:center; flex-shrink:0; margin-top:1px; }
</style>
</head>
<body>
<div class="container">
  <h1>Synthèse BRVM — Semaine {{ semaine }}</h1>
  <div class="subtitle">{{ date }} · Cours BRVM live · Portefeuille M. Cissé Habib</div>

  <div class="metrics">
    <div class="m"><div class="ml">Valeur titres</div><div class="mv">{{ total_valeur_fmt }} FCFA</div></div>
    <div class="m"><div class="ml">Liquidités</div><div class="mv">{{ liquidite_fmt }} FCFA</div></div>
    <div class="m"><div class="ml">PV latente</div><div class="mv {{ 'up' if pv_total >= 0 else 'dn' }}">{{ '+' if pv_total >= 0 else '' }}{{ pv_total_fmt }} FCFA</div></div>
    <div class="m"><div class="ml">Part halal</div><div class="mv" style="color:#BA7517;">{{ pct_halal }}%</div></div>
  </div>

  <div class="sec">Positions au {{ date }}</div>
  <table>
    <thead><tr><th>Titre</th><th>Cours</th><th>CMP</th><th>+/- Value</th><th>Poids</th><th>Halal</th></tr></thead>
    <tbody>
    {% for p in positions %}
    <tr>
      <td><strong>{{ p.nom }}</strong></td>
      <td>{{ "{:,.0f}".format(p.cours).replace(",", " ") }}</td>
      <td>{{ "{:,.0f}".format(p.cmp).replace(",", " ") }}</td>
      <td class="{{ 'up' if p.pv >= 0 else 'dn' }}">{{ '+' if p.pv >= 0 else '' }}{{ "{:,.0f}".format(p.pv).replace(",", " ") }}</td>
      <td>{{ p.poids }}%</td>
      <td>
        {% if p.halal == 'conforme' %}<span class="badge b-halal">Halal</span>
        {% elif p.halal == 'a_clarifier' %}<span class="badge b-warn">À clarifier</span>
        {% else %}<span class="badge b-alert">Haram</span>{% endif %}
      </td>
    </tr>
    {% endfor %}
    </tbody>
  </table>

  <div class="sec">Alertes</div>
  {% for alerte in alertes %}
  <div class="alert {{ 'a-red' if alerte.niveau == 'BLOQUANT' else 'a-warn' }}">
    <strong>{{ alerte.ticker }}</strong> — {{ alerte.message }}
  </div>
  {% endfor %}

  <div class="sec">Actions prioritaires cette semaine</div>
  {% for action in actions %}
  <div class="action-item">
    <div class="action-num">{{ loop.index }}</div>
    <div><strong>{{ action.titre }}</strong><br><span style="color:#6b6a63;">{{ action.detail }}</span></div>
  </div>
  {% endfor %}

  <div class="footer">Rapport généré automatiquement le {{ date }} à {{ heure }} · Agent BRVM · GitHub Actions</div>
</div>
</body>
</html>"""


def generer_html(donnees):
    """Génère le HTML du rapport à partir des données agrégées"""
    template = Template(TEMPLATE_HTML)

    total_valeur = donnees["veille"]["total_valeur"]
    positions_raw = donnees["veille"]["positions"]
    halal_data = donnees["halal"]["resultats"]

    # Ajoute statut halal aux positions
    positions = []
    pv_total = 0
    for p in positions_raw:
        h = halal_data.get(p["ticker"], {})
        p["halal"] = h.get("statut", "inconnu")
        positions.append(p)
        pv_total += p["pv"]

    # Part halal (poids des positions conformes)
    pct_halal = round(sum(p["poids"] for p in positions if p["halal"] == "conforme"), 1)

    # Actions prioritaires fixes basées sur l'analyse
    actions = [
        {"titre": "Ordre limite BIIC BN",
         "detail": "400 titres à 5 700 FCFA · validité 30 jours · Sur Sika Finance"},
        {"titre": "Acheter NTLC",
         "detail": f"~99 titres à 12 000 FCFA · liquidités disponibles · correction actuelle = opportunité"},
        {"titre": "Dividende BOA BN",
         "detail": "Ex-div 5 mai · ~208 000 FCFA brut · Préparer calcul purification"},
        {"titre": "Préparer ordre TTLC",
         "detail": "En attente produit vente BIIC · cours cible 2 700–2 800 FCFA"},
    ]

    html = template.render(
        date=donnees["date"],
        heure=donnees["heure"],
        semaine=datetime.now().isocalendar()[1],
        total_valeur_fmt=f"{total_valeur:,.0f}".replace(",", " "),
        liquidite_fmt="1 201 585",
        pv_total=pv_total,
        pv_total_fmt=f"{abs(pv_total):,.0f}".replace(",", " "),
        pct_halal=pct_halal,
        positions=positions,
        alertes=donnees["halal"]["alertes"],
        actions=actions,
    )
    return html


def sauvegarder_dashboard(html):
    """Sauvegarde le dashboard dans output/index.html"""
    os.makedirs("output", exist_ok=True)
    with open("output/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("[synthese] Dashboard sauvegardé → output/index.html")


def envoyer_email(html, destinataire):
    """Envoie le rapport par email (nécessite GMAIL_APP_PASSWORD en secret)"""
    expediteur = os.environ.get("REPORT_EMAIL", "")
    mot_de_passe = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not mot_de_passe:
        print("[synthese] GMAIL_APP_PASSWORD non défini — email non envoyé")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Synthèse BRVM — {datetime.now().strftime('%d/%m/%Y')}"
    msg["From"] = expediteur
    msg["To"] = destinataire
    msg.attach(MIMEText(html, "html"))

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(expediteur, mot_de_passe)
            server.sendmail(expediteur, destinataire, msg.as_string())
        print(f"[synthese] Email envoyé → {destinataire}")
    except Exception as e:
        print(f"[synthese] Erreur envoi email : {e}")


def run(donnees):
    """Point d'entrée principal"""
    print("[synthese] Génération du rapport...")
    html = generer_html(donnees)
    sauvegarder_dashboard(html)

    destinataire = os.environ.get("REPORT_EMAIL", "")
    if destinataire:
        envoyer_email(html, destinataire)

    print("[synthese] Rapport généré avec succès")
    return html
