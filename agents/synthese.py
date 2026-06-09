"""
synthese.py v2 — Agent synthèse BRVM
Injecte les données réelles (cours, positions, actions, opportunités)
dans le template dashboard v3 et envoie le rapport par email.
"""

import os
import json
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from pathlib import Path

DATA_DIR     = Path(__file__).parent.parent / "data"
OUTPUT_DIR   = Path(__file__).parent.parent / "output"
TEMPLATE_DIR = Path(__file__).parent.parent / "output"


def charger_json(nom):
    chemin = DATA_DIR / nom
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def generer_dashboard(donnees):
    """
    Génère le fichier output/index.html en injectant
    les données réelles dans le template dashboard v3.
    """
    veille       = donnees.get("veille", {})
    halal        = donnees.get("halal", {})
    risque_data  = donnees.get("risque", {})
    opps         = donnees.get("opportunites", {})
    suivi        = donnees.get("suivi", {})
    date_str     = donnees.get("date", datetime.now().strftime("%d/%m/%Y"))
    heure_str    = donnees.get("heure", datetime.now().strftime("%H:%M"))
    semaine      = datetime.now().isocalendar()[1]

    positions_raw = veille.get("positions", [])
    halal_res     = halal.get("resultats", {})
    alertes_halal = halal.get("alertes", [])
    score_risque  = risque_data.get("score_risque", 0)
    poids_halal   = risque_data.get("poids_halal", 0)
    total_valeur  = veille.get("total_valeur", 0)
    liquidite     = charger_json("portefeuille.json").get("liquidite_fcfa", 0)
    actions       = suivi.get("actions", [])
    opp_list      = opps.get("opportunites", [])

    # ── Calculs globaux ──────────────────────────
    pv_total = sum(p.get("pv", 0) for p in positions_raw)
    pv_signe = "+" if pv_total >= 0 else ""

    # ── Positions JSON pour le JS ────────────────
    positions_js = []
    for p in positions_raw:
        h = halal_res.get(p["ticker"], {})
        # halal.py émet directement statut = conforme / a_clarifier / haram
        statut_halal = h.get("statut", "a_clarifier")
        positions_js.append({
            "ticker":  p["ticker"],
            "nom":     p.get("nom", p["ticker"]),
            "qte":     p.get("quantite", 0),
            "cmp":     p.get("cmp", 0),
            "cours":   p.get("cours", 0),
            "pv":      round(p.get("pv", 0)),
            "poids":   p.get("poids", 0),
            "halal":   statut_halal,
        })

    # ── Actions JSON pour le JS ──────────────────
    actions_js = []
    for a in actions:
        actions_js.append({
            "id":               a.get("id", ""),
            "titre":            a.get("titre", ""),
            "detail":           a.get("detail", ""),
            "statut":           a.get("statut", "en_attente"),
            "date_cible":       a.get("date_cible"),
            "date_realisation": a.get("date_realisation"),
            "note":             a.get("note", ""),
        })

    # ── Opportunités JSON pour le JS ─────────────
    opps_js = []
    for o in opp_list[:5]:
        opps_js.append({
            "ticker":    o.get("ticker", ""),
            "nom":       o.get("nom", ""),
            "secteur":   o.get("secteur", ""),
            "conviction":o.get("note", 3),
            "per":       o.get("per"),
            "div":       o.get("div_yield"),
            "cours":     o.get("cours", 0),
            "signal":    o.get("signal_tech", ""),
            "bni":       o.get("bonus_bni", 0) > 0,
            "rang":      None,
        })

    # ── Dividendes depuis suivi.json ─────────────
    divs_raw = suivi.get("dividendes_a_venir", [])
    divs_js  = []
    for d in divs_raw:
        if not d.get("ticker"):
            continue
        qte_pos = next((p["qte"] for p in positions_js if p["ticker"] == d["ticker"]), 0)
        div_net = d.get("dividende_net", 0) or 0
        total   = round(div_net * qte_pos) if qte_pos else d.get("montant_brut", 0)
        divs_js.append({
            "ticker":       d.get("ticker"),
            "nom":          d.get("nom", d.get("ticker")),
            "div_net":      div_net,
            "qte":          qte_pos,
            "total":        total,
            "ex_div":       d.get("ex_div", "—"),
            "paiement":     d.get("paiement", "—"),
            "rendement":    d.get("rendement_pct", 0),
            "purification": d.get("purification_requise", False),
            "pct_haram":    d.get("pct_haram", 0) if d.get("pct_haram") else 0,
            "sadaqa":       d.get("montant_purification"),
            "net_halal":    d.get("montant_net_halal"),
        })

    # ── Alertes risque ───────────────────────────
    alertes_risque = risque_data.get("alertes", [])

    # ── Métriques overview ───────────────────────
    total_general = total_valeur + liquidite
    total_val_fmt = f"{round(total_general / 1_000_000, 1)}M"
    pv_fmt        = f"{pv_signe}{round(abs(pv_total) / 1_000)}k"
    liq_fmt       = f"{round(liquidite / 1_000)}k"

    # ── Couleur score risque ─────────────────────
    if score_risque >= 70:
        risk_color = "var(--dn)"
    elif score_risque >= 40:
        risk_color = "var(--warn)"
    else:
        risk_color = "var(--up)"

    # ── Couleur part halal ───────────────────────
    halal_color = "var(--up)" if poids_halal >= 30 else "var(--warn)"

    # ── Construction du HTML ─────────────────────
    html = _build_html(
        date_str=date_str,
        heure_str=heure_str,
        semaine=semaine,
        total_val_fmt=total_val_fmt,
        liq_fmt=liq_fmt,
        pv_fmt=pv_fmt,
        pv_class="up" if pv_total >= 0 else "dn",
        score_risque=score_risque,
        risk_color=risk_color,
        poids_halal=poids_halal,
        halal_color=halal_color,
        positions_js=json.dumps(positions_js, ensure_ascii=False),
        actions_js=json.dumps(actions_js, ensure_ascii=False),
        opps_js=json.dumps(opps_js, ensure_ascii=False),
        divs_js=json.dumps(divs_js, ensure_ascii=False),
        alertes_risque=alertes_risque,
        alertes_halal=alertes_halal,
    )

    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(OUTPUT_DIR / "index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("[synthese] Dashboard généré → output/index.html")
    return html


def _build_html(**ctx):
    """Construit le HTML complet du dashboard v3"""

    # Alertes HTML
    alertes_html = ""
    for a in ctx["alertes_risque"]:
        cls = "a-red" if a["niveau"] in ("URGENT", "CRITIQUE") else "a-warn"
        alertes_html += f'<div class="alert {cls}"><strong>{a["ticker"]}</strong> — {a["message"]}</div>\n'
    for a in ctx["alertes_halal"]:
        if a["niveau"] == "ATTENTION":
            alertes_html += f'<div class="alert a-warn"><strong>{a["ticker"]}</strong> — {a["message"]}</div>\n'
    if not alertes_html:
        alertes_html = '<div class="alert a-ok">Aucune alerte critique cette semaine.</div>'

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BRVM Dashboard — M. Cissé Habib</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Cabinet+Grotesk:wght@400;500;700;800&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
:root {{
  --bg:#0A0E1A;--bg2:#111827;--bg3:#1A2235;
  --border:rgba(255,255,255,0.07);--border2:rgba(255,255,255,0.12);
  --text:#F0F4FF;--text2:#8892A4;--text3:#4A5568;
  --up:#00E5A0;--up-bg:rgba(0,229,160,0.10);
  --dn:#FF4D6D;--dn-bg:rgba(255,77,109,0.10);
  --warn:#FFB547;--warn-bg:rgba(255,181,71,0.10);
  --info:#60A5FA;--info-bg:rgba(96,165,250,0.10);
  --accent:#7C6FFF;--r:12px;--r-lg:16px;
}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:'Cabinet Grotesk',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;}}
.header{{background:linear-gradient(135deg,#0A0E1A,#111827,#0D1B2A);border-bottom:1px solid var(--border);padding:1.25rem 2rem;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;backdrop-filter:blur(10px);}}
.logo{{width:36px;height:36px;background:linear-gradient(135deg,var(--accent),#A78BFA);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:17px;}}
.header-title{{font-size:16px;font-weight:700;letter-spacing:-.3px;}}
.header-sub{{font-size:11px;color:var(--text2);margin-top:1px;font-family:'DM Mono',monospace;}}
.live-badge{{display:flex;align-items:center;gap:6px;font-size:11px;font-weight:500;color:var(--up);background:var(--up-bg);padding:4px 10px;border-radius:20px;font-family:'DM Mono',monospace;}}
.live-dot{{width:6px;height:6px;border-radius:50%;background:var(--up);animation:pulse 2s infinite;}}
@keyframes pulse{{0%,100%{{opacity:1;transform:scale(1)}}50%{{opacity:.5;transform:scale(1.3)}}}}
.nav{{background:var(--bg2);border-bottom:1px solid var(--border);padding:0 2rem;display:flex;overflow-x:auto;scrollbar-width:none;}}
.nav::-webkit-scrollbar{{display:none;}}
.nav-tab{{padding:.85rem 1.1rem;font-size:13px;font-weight:500;color:var(--text2);cursor:pointer;border-bottom:2px solid transparent;transition:all .15s;white-space:nowrap;background:none;border-top:none;border-left:none;border-right:none;}}
.nav-tab:hover{{color:var(--text);}}
.nav-tab.active{{color:var(--accent);border-bottom-color:var(--accent);}}
.container{{max-width:1200px;margin:0 auto;padding:1.5rem;}}
.page{{display:none;}}.page.active{{display:block;}}
.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:1.5rem;}}
@media(max-width:768px){{.metrics{{grid-template-columns:repeat(2,1fr);}}}}
.metric{{background:var(--bg2);border:1px solid var(--border);border-radius:var(--r-lg);padding:16px 18px;position:relative;overflow:hidden;transition:border-color .15s,transform .15s;}}
.metric:hover{{border-color:var(--border2);transform:translateY(-1px);}}
.metric::before{{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--accent),transparent);}}
.metric.green::before{{background:linear-gradient(90deg,var(--up),transparent);}}
.metric.amber::before{{background:linear-gradient(90deg,var(--warn),transparent);}}
.metric-label{{font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px;font-family:'DM Mono',monospace;}}
.metric-val{{font-size:22px;font-weight:800;letter-spacing:-.5px;}}
.metric-sub{{font-size:11px;color:var(--text2);margin-top:4px;font-family:'DM Mono',monospace;}}
.up{{color:var(--up);}}.dn{{color:var(--dn);}}.neu{{color:var(--text2);}}
.sec{{font-size:11px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.10em;margin:1.5rem 0 .75rem;display:flex;align-items:center;gap:8px;}}
.sec::after{{content:'';flex:1;height:1px;background:var(--border);}}
.table-wrap{{background:var(--bg2);border:1px solid var(--border);border-radius:var(--r-lg);overflow:hidden;margin-bottom:1.5rem;}}
table{{width:100%;border-collapse:collapse;font-size:13px;}}
th{{background:var(--bg3);font-weight:600;font-size:10px;color:var(--text2);padding:10px 14px;text-align:left;border-bottom:1px solid var(--border);text-transform:uppercase;letter-spacing:.05em;font-family:'DM Mono',monospace;}}
td{{padding:11px 14px;border-bottom:1px solid var(--border);vertical-align:middle;}}
tr:last-child td{{border-bottom:none;}}
tr:hover td{{background:rgba(255,255,255,.02);}}
.bar-bg{{height:3px;border-radius:2px;background:var(--bg3);margin-top:4px;overflow:hidden;}}
.bar-f{{height:100%;border-radius:2px;}}
.badge{{font-size:10px;padding:2px 8px;border-radius:20px;font-weight:600;white-space:nowrap;font-family:'DM Mono',monospace;}}
.b-halal{{background:var(--up-bg);color:var(--up);border:1px solid rgba(0,229,160,.2);}}
.b-warn{{background:var(--warn-bg);color:var(--warn);border:1px solid rgba(255,181,71,.2);}}
.b-alert{{background:var(--dn-bg);color:var(--dn);border:1px solid rgba(255,77,109,.2);}}
.b-done{{background:rgba(0,229,160,.08);color:var(--up);border:1px solid rgba(0,229,160,.15);}}
.b-wait{{background:var(--warn-bg);color:var(--warn);border:1px solid rgba(255,181,71,.2);}}
.b-cours{{background:var(--info-bg);color:var(--info);border:1px solid rgba(96,165,250,.2);}}
.alert{{border-left:3px solid;padding:12px 16px;margin-bottom:10px;font-size:13px;line-height:1.6;border-radius:0 var(--r) var(--r) 0;}}
.a-red{{border-color:var(--dn);background:var(--dn-bg);color:#FFB3C0;}}
.a-warn{{border-color:var(--warn);background:var(--warn-bg);color:#FFD99A;}}
.a-ok{{border-color:var(--up);background:var(--up-bg);color:#7FFFD4;}}
.a-info{{border-color:var(--info);background:var(--info-bg);color:#BAD8FF;}}
.action-card{{background:var(--bg2);border:1px solid var(--border);border-radius:var(--r-lg);padding:16px 18px;margin-bottom:10px;display:flex;align-items:flex-start;gap:14px;transition:border-color .15s;}}
.action-card:hover{{border-color:var(--border2);}}
.action-card.done{{opacity:.45;}}
.action-num{{min-width:28px;height:28px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;flex-shrink:0;font-family:'DM Mono',monospace;}}
.num-wait{{background:var(--warn-bg);color:var(--warn);}}
.num-cours{{background:var(--info-bg);color:var(--info);}}
.num-done{{background:var(--up-bg);color:var(--up);}}
.btn{{display:inline-flex;align-items:center;gap:5px;padding:6px 12px;font-size:12px;font-weight:600;border-radius:8px;cursor:pointer;transition:all .15s;font-family:'Cabinet Grotesk',sans-serif;border:none;}}
.btn-success{{background:rgba(0,229,160,.15);color:var(--up);border:1px solid rgba(0,229,160,.25);}}
.btn-success:hover{{background:rgba(0,229,160,.25);}}
.btn-warn{{background:rgba(255,181,71,.15);color:var(--warn);border:1px solid rgba(255,181,71,.25);}}
.btn-warn:hover{{background:rgba(255,181,71,.25);}}
.btn-ghost{{background:transparent;color:var(--text2);border:1px solid var(--border);}}
.btn-ghost:hover{{background:var(--bg3);color:var(--text);}}
.btn-sm{{padding:4px 10px;font-size:11px;}}
.btn-add{{background:linear-gradient(135deg,var(--accent),#A78BFA);color:#fff;border:none;padding:8px 16px;font-size:13px;border-radius:10px;cursor:pointer;font-weight:700;transition:opacity .15s;}}
.btn-add:hover{{opacity:.85;}}
.modal-overlay{{position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:1000;display:flex;align-items:center;justify-content:center;padding:1rem;backdrop-filter:blur(4px);}}
.modal-overlay.hidden{{display:none;}}
.modal{{background:var(--bg2);border:1px solid var(--border2);border-radius:var(--r-lg);padding:24px;width:100%;max-width:480px;max-height:90vh;overflow-y:auto;}}
.modal-title{{font-size:16px;font-weight:700;margin-bottom:16px;}}
.modal-field{{margin-bottom:14px;}}
.modal-label{{font-size:12px;color:var(--text2);margin-bottom:5px;display:block;font-weight:500;}}
.modal-input{{width:100%;background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:10px 12px;color:var(--text);font-size:13px;font-family:'Cabinet Grotesk',sans-serif;outline:none;}}
.modal-input:focus{{border-color:var(--accent);}}
.modal-select{{width:100%;background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:10px 12px;color:var(--text);font-size:13px;font-family:'Cabinet Grotesk',sans-serif;outline:none;cursor:pointer;}}
.modal-select option{{background:var(--bg2);}}
.modal-btns{{display:flex;gap:8px;justify-content:flex-end;margin-top:20px;}}
.token-banner{{background:rgba(255,181,71,.08);border:1px solid rgba(255,181,71,.2);border-radius:var(--r-lg);padding:16px 18px;margin-bottom:1.5rem;display:flex;align-items:center;gap:14px;}}
.token-banner.hidden{{display:none;}}
.progress-section{{background:var(--bg2);border:1px solid var(--border);border-radius:var(--r-lg);padding:16px 18px;margin-bottom:1.5rem;}}
.progress-bar-bg{{height:6px;background:var(--bg3);border-radius:3px;overflow:hidden;}}
.progress-bar-fill{{height:100%;border-radius:3px;background:linear-gradient(90deg,var(--accent),var(--up));transition:width .8s ease;}}
.filter-row{{display:flex;gap:6px;margin-bottom:1rem;flex-wrap:wrap;align-items:center;}}
.filter-btn{{font-size:12px;padding:5px 14px;border:1px solid var(--border);border-radius:20px;background:transparent;color:var(--text2);cursor:pointer;transition:all .15s;font-family:'Cabinet Grotesk',sans-serif;}}
.filter-btn:hover{{color:var(--text);border-color:var(--border2);}}
.filter-btn.active{{background:rgba(124,111,255,.15);color:var(--accent);border-color:rgba(124,111,255,.3);}}
.toast{{position:fixed;bottom:24px;right:24px;z-index:2000;background:var(--bg2);border:1px solid var(--border2);border-radius:var(--r-lg);padding:14px 18px;font-size:13px;font-weight:500;max-width:320px;transform:translateY(100px);opacity:0;transition:all .3s ease;}}
.toast.show{{transform:translateY(0);opacity:1;}}
.toast.success{{border-color:rgba(0,229,160,.3);color:var(--up);}}
.toast.error{{border-color:rgba(255,77,109,.3);color:var(--dn);}}
.opp-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:12px;margin-bottom:1.5rem;}}
.opp-card{{background:var(--bg2);border:1px solid var(--border);border-radius:var(--r-lg);padding:16px 18px;transition:border-color .15s,transform .15s;position:relative;overflow:hidden;}}
.opp-card:hover{{border-color:var(--accent);transform:translateY(-2px);}}
.opp-card.bni{{border-color:rgba(124,111,255,.3);}}
.opp-card.bni::after{{content:'BNI';position:absolute;top:12px;right:12px;font-size:9px;font-weight:700;color:var(--accent);background:rgba(124,111,255,.15);padding:2px 6px;border-radius:4px;font-family:'DM Mono',monospace;}}
.div-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px;}}
.div-card{{background:var(--bg2);border:1px solid var(--border);border-radius:var(--r-lg);padding:16px 18px;position:relative;overflow:hidden;}}
.div-card::before{{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,#FFB547,transparent);}}
.chart-container{{background:var(--bg2);border:1px solid var(--border);border-radius:var(--r-lg);padding:20px;margin-bottom:1.5rem;}}
.chart-wrap{{position:relative;height:220px;}}
.chart-legend{{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px;}}
.chart-legend-item{{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--text2);font-family:'DM Mono',monospace;}}
.chart-dot{{width:8px;height:8px;border-radius:2px;}}
.risk-section{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:1.5rem;}}
@media(max-width:600px){{.risk-section{{grid-template-columns:1fr;}}}}
.risk-card{{background:var(--bg2);border:1px solid var(--border);border-radius:var(--r-lg);padding:20px;text-align:center;}}
.halal-bar-bg{{height:8px;background:var(--bg3);border-radius:4px;overflow:hidden;}}
.halal-bar-fill{{height:100%;border-radius:4px;background:linear-gradient(90deg,var(--up),#00B377);transition:width .8s ease;}}
@media(max-width:768px){{.header{{padding:1rem;}}.container{{padding:1rem .75rem;}}.nav{{padding:0 .75rem;}}table{{font-size:12px;}}th,td{{padding:8px 10px;}}}}
::-webkit-scrollbar{{width:4px;height:4px;}}
::-webkit-scrollbar-track{{background:var(--bg);}}
::-webkit-scrollbar-thumb{{background:var(--bg3);border-radius:2px;}}
</style>
</head>
<body>
<div class="toast" id="toast"></div>

<!-- MODAL réalisé -->
<div class="modal-overlay hidden" id="modal-realise">
  <div class="modal">
    <div class="modal-title">✅ Marquer comme réalisé</div>
    <div class="modal-field"><label class="modal-label">Action</label><div style="font-size:14px;font-weight:600" id="modal-action-titre">—</div></div>
    <div class="modal-field"><label class="modal-label">Date de réalisation</label><input type="date" class="modal-input" id="modal-date"></div>
    <div class="modal-field"><label class="modal-label">Note (optionnel)</label><input type="text" class="modal-input" id="modal-note" placeholder="Ex: 50 titres achetés à 8 100 FCFA"></div>
    <div class="modal-btns"><button class="btn btn-ghost" onclick="closeModal('modal-realise')">Annuler</button><button class="btn btn-success" onclick="confirmerRealise()">Confirmer ✓</button></div>
  </div>
</div>

<!-- MODAL nouvelle action -->
<div class="modal-overlay hidden" id="modal-new">
  <div class="modal">
    <div class="modal-title">➕ Nouvelle action</div>
    <div class="modal-field"><label class="modal-label">Titre</label><input type="text" class="modal-input" id="new-titre" placeholder="Ex: Acheter PALC"></div>
    <div class="modal-field"><label class="modal-label">Détail</label><input type="text" class="modal-input" id="new-detail" placeholder="Ex: 50 titres à 8 100 FCFA"></div>
    <div class="modal-field"><label class="modal-label">Statut</label><select class="modal-select" id="new-statut"><option value="en_attente">En attente</option><option value="en_cours">En cours</option></select></div>
    <div class="modal-field"><label class="modal-label">Date cible</label><input type="date" class="modal-input" id="new-date"></div>
    <div class="modal-field"><label class="modal-label">Note</label><input type="text" class="modal-input" id="new-note" placeholder="Contexte ou condition"></div>
    <div class="modal-btns"><button class="btn btn-ghost" onclick="closeModal('modal-new')">Annuler</button><button class="btn" style="background:rgba(124,111,255,.2);color:var(--accent);border:1px solid rgba(124,111,255,.3)" onclick="confirmerNouvelle()">Ajouter</button></div>
  </div>
</div>

<!-- MODAL token -->
<div class="modal-overlay hidden" id="modal-token">
  <div class="modal">
    <div class="modal-title">🔑 Token GitHub</div>
    <div style="font-size:13px;color:var(--text2);margin-bottom:16px;line-height:1.6">Permet de sauvegarder tes actions directement dans GitHub. Stocké uniquement dans ton navigateur.</div>
    <div class="modal-field"><label class="modal-label">Personal Access Token (scope: repo)</label><input type="password" class="modal-input" id="token-input" placeholder="ghp_..."></div>
    <div style="font-size:11px;color:var(--text3);margin-top:4px">github.com → Settings → Developer settings → Personal access tokens</div>
    <div class="modal-btns"><button class="btn btn-ghost" onclick="closeModal('modal-token')">Annuler</button><button class="btn" style="background:rgba(124,111,255,.2);color:var(--accent);border:1px solid rgba(124,111,255,.3)" onclick="sauvegarderToken()">Enregistrer</button></div>
  </div>
</div>

<!-- HEADER -->
<header class="header">
  <div style="display:flex;align-items:center;gap:14px">
    <div class="logo">📊</div>
    <div><div class="header-title">BRVM Dashboard</div><div class="header-sub">M. Cissé Habib · Semaine {ctx['semaine']} · {ctx['date_str']}</div></div>
  </div>
  <div style="display:flex;align-items:center;gap:10px">
    <div class="live-badge"><div class="live-dot"></div>{ctx['date_str']} {ctx['heure_str']}</div>
    <button class="btn btn-ghost btn-sm" onclick="openModal('modal-token')" title="Token GitHub">🔑</button>
  </div>
</header>

<nav class="nav">
  <button class="nav-tab active" onclick="showPage('overview',this)">Vue d'ensemble</button>
  <button class="nav-tab" onclick="showPage('portfolio',this)">Portefeuille</button>
  <button class="nav-tab" onclick="showPage('actions',this)">Actions <span id="badge-attente" style="background:var(--warn-bg);color:var(--warn);font-size:10px;padding:1px 6px;border-radius:10px;margin-left:4px;font-family:'DM Mono',monospace"></span></button>
  <button class="nav-tab" onclick="showPage('opportunites',this)">Opportunités</button>
  <button class="nav-tab" onclick="showPage('dividendes',this)">Dividendes</button>
</nav>

<!-- PAGE overview -->
<div class="page active" id="page-overview"><div class="container">
  <div class="metrics">
    <div class="metric green"><div class="metric-label">Total général</div><div class="metric-val">{ctx['total_val_fmt']}</div><div class="metric-sub">FCFA</div></div>
    <div class="metric"><div class="metric-label">Liquidités</div><div class="metric-val">{ctx['liq_fmt']}</div><div class="metric-sub">FCFA disponibles</div></div>
    <div class="metric amber"><div class="metric-label">Score risque</div><div class="metric-val" style="color:{ctx['risk_color']}">{ctx['score_risque']}/100</div><div class="metric-sub">Concentration portefeuille</div></div>
    <div class="metric"><div class="metric-label">Part halal</div><div class="metric-val" style="color:{ctx['halal_color']}">{ctx['poids_halal']}%</div><div class="metric-sub">Objectif 30%</div></div>
  </div>
  <div class="risk-section">
    <div class="risk-card">
      <div class="metric-label" style="margin-bottom:10px">Score de risque</div>
      <div style="font-size:48px;font-weight:800;font-family:'DM Mono',monospace;color:{ctx['risk_color']}">{ctx['score_risque']}</div>
      <div style="font-size:12px;color:var(--text2)">/ 100</div>
      <div style="margin-top:12px"><div class="halal-bar-bg"><div style="height:100%;border-radius:4px;width:{ctx['score_risque']}%;background:linear-gradient(90deg,{ctx['risk_color']},transparent)"></div></div></div>
    </div>
    <div class="risk-card">
      <div class="metric-label" style="margin-bottom:10px">Part halal</div>
      <div style="font-size:48px;font-weight:800;font-family:'DM Mono',monospace;color:{ctx['halal_color']}">{ctx['poids_halal']}%</div>
      <div style="font-size:12px;color:var(--text2)">Objectif : 30%</div>
      <div style="margin-top:12px"><div class="halal-bar-bg"><div class="halal-bar-fill" style="width:{ctx['poids_halal']}%"></div></div>
      <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--text3);margin-top:4px;font-family:'DM Mono',monospace"><span>0%</span><span style="color:var(--up)">▼ 30%</span><span>100%</span></div></div>
    </div>
  </div>
  <div class="sec">Alertes</div>
  {alertes_html}
  <div class="sec">Répartition</div>
  <div class="chart-container">
    <div style="font-size:13px;font-weight:600;margin-bottom:16px;color:var(--text2)">Pondération par titre</div>
    <div class="chart-wrap"><canvas id="chartDonut"></canvas></div>
    <div class="chart-legend" id="chart-legend"></div>
  </div>
</div></div>

<!-- PAGE portfolio -->
<div class="page" id="page-portfolio"><div class="container">
  <div class="metrics">
    <div class="metric green"><div class="metric-label">Valeur titres</div><div class="metric-val" id="m-titres">—</div><div class="metric-sub">FCFA</div></div>
    <div class="metric"><div class="metric-label">Liquidités</div><div class="metric-val">{ctx['liq_fmt']}</div><div class="metric-sub">FCFA</div></div>
    <div class="metric"><div class="metric-label">Positions</div><div class="metric-val" id="m-pos">—</div><div class="metric-sub">lignes</div></div>
    <div class="metric"><div class="metric-label">Meilleure PV</div><div class="metric-val up" id="m-best">—</div><div class="metric-sub" id="m-best-label">—</div></div>
  </div>
  <div class="sec">Positions détaillées</div>
  <div class="table-wrap"><table><thead><tr><th>Titre</th><th>Qté</th><th>CMP</th><th>Cours</th><th>+/- Value</th><th>Poids</th><th>Halal</th></tr></thead><tbody id="positions-table"></tbody></table></div>
  <div class="sec">Plus-values latentes</div>
  <div class="chart-container"><div style="font-size:13px;font-weight:600;margin-bottom:16px;color:var(--text2)">PV latentes par position (k FCFA)</div><div class="chart-wrap"><canvas id="chartBar"></canvas></div></div>
</div></div>

<!-- PAGE actions -->
<div class="page" id="page-actions"><div class="container">
  <div class="token-banner" id="token-banner">
    <div style="font-size:20px">🔑</div>
    <div style="flex:1"><div style="font-size:13px;font-weight:600;color:var(--warn)">Token GitHub non configuré</div><div style="font-size:12px;color:var(--text2);margin-top:2px">Configure ton token pour sauvegarder les mises à jour directement dans GitHub.</div></div>
    <button class="btn btn-warn btn-sm" onclick="openModal('modal-token')">Configurer</button>
  </div>
  <div class="progress-section">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
      <div style="font-size:13px;font-weight:600">Progression</div>
      <div style="font-size:20px;font-weight:800;font-family:'DM Mono',monospace;color:var(--up)" id="actions-count">—</div>
    </div>
    <div class="progress-bar-bg"><div class="progress-bar-fill" id="actions-progress" style="width:0%"></div></div>
    <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text2);margin-top:6px;font-family:'DM Mono',monospace"><span id="actions-done-label">—</span><span id="actions-total-label">—</span></div>
  </div>
  <div class="filter-row">
    <button class="filter-btn active" onclick="filterActions('tous',this)">Toutes</button>
    <button class="filter-btn" onclick="filterActions('en_attente',this)">En attente</button>
    <button class="filter-btn" onclick="filterActions('en_cours',this)">En cours</button>
    <button class="filter-btn" onclick="filterActions('realise',this)">Réalisées</button>
    <button class="btn-add" style="margin-left:auto" onclick="openModal('modal-new')">+ Nouvelle action</button>
  </div>
  <div id="actions-list"></div>
</div></div>

<!-- PAGE opportunites -->
<div class="page" id="page-opportunites"><div class="container">
  <div class="alert a-info" style="margin-bottom:1.5rem"><strong>Sources :</strong> TOP 10 BNI Finances + scan BRVM halal + analyse technique.</div>
  <div class="sec">Top opportunités halal</div>
  <div class="opp-grid" id="opp-grid"></div>
</div></div>

<!-- PAGE dividendes -->
<div class="page" id="page-dividendes"><div class="container">
  <div class="alert a-warn" style="margin-bottom:1.5rem"><strong>Purification obligatoire</strong> — Les dividendes bancaires contiennent une part haram. Le montant sadaqa est calculé automatiquement.</div>
  <div class="sec">Calendrier des dividendes</div>
  <div class="div-grid" id="div-grid"></div>
</div></div>

<script>
const REPO_OWNER='habibcisse5',REPO_NAME='brvm-agent',FILE_PATH='data/suivi.json';
const COLORS={{BICB:'#FF4D6D',BOAB:'#00E5A0',SNTS:'#60A5FA',SGBC:'#FFB547',ETIT:'#A78BFA',BICC:'#34D399',SIVC:'#FB923C',SIBC:'#94A3B8',TTLC:'#F472B6',NTLC:'#38BDF8'}};

let SUIVI = {{actions: {ctx['actions_js']}}};
const POSITIONS = {ctx['positions_js']};
const OPPORTUNITES = {ctx['opps_js']};
const DIVIDENDES = {ctx['divs_js']};
let githubToken = localStorage.getItem('brvm_gh_token')||'';
let actionEnCours = null;
let filtreActif = 'tous';

function showPage(id,btn){{document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));document.querySelectorAll('.nav-tab').forEach(t=>t.classList.remove('active'));document.getElementById('page-'+id).classList.add('active');if(btn)btn.classList.add('active');}}
function openModal(id){{document.getElementById(id).classList.remove('hidden');}}
function closeModal(id){{document.getElementById(id).classList.add('hidden');}}
function showToast(msg,type='success'){{const t=document.getElementById('toast');t.textContent=msg;t.className='toast '+type+' show';setTimeout(()=>t.classList.remove('show'),3000);}}

function sauvegarderToken(){{const v=document.getElementById('token-input').value.trim();if(!v.startsWith('ghp_')&&!v.startsWith('github_pat_')){{showToast('Token invalide','error');return;}}githubToken=v;localStorage.setItem('brvm_gh_token',v);closeModal('modal-token');updateTokenBanner();showToast('Token enregistré ✓','success');}}
function updateTokenBanner(){{const b=document.getElementById('token-banner');if(githubToken)b.classList.add('hidden');else b.classList.remove('hidden');}}

async function saveSuiviToGitHub(suivi){{
  if(!githubToken){{openModal('modal-token');return false;}}
  try{{
    showToast('Sauvegarde...','success');
    const r1=await fetch(`https://api.github.com/repos/${{REPO_OWNER}}/${{REPO_NAME}}/contents/${{FILE_PATH}}`,{{headers:{{Authorization:`Bearer ${{githubToken}}`,Accept:'application/vnd.github+json'}}}});
    if(!r1.ok)throw new Error('Lecture impossible');
    const d1=await r1.json();
    const content=btoa(unescape(encodeURIComponent(JSON.stringify(suivi,null,2))));
    const r2=await fetch(`https://api.github.com/repos/${{REPO_OWNER}}/${{REPO_NAME}}/contents/${{FILE_PATH}}`,{{method:'PUT',headers:{{Authorization:`Bearer ${{githubToken}}`,Accept:'application/vnd.github+json','Content-Type':'application/json'}},body:JSON.stringify({{message:`update suivi — ${{new Date().toISOString().split('T')[0]}}`,content,sha:d1.sha}})}});
    if(!r2.ok){{const e=await r2.json();throw new Error(e.message||'Erreur');}}
    showToast('Sauvegardé sur GitHub ✓','success');return true;
  }}catch(e){{showToast('Erreur: '+e.message,'error');return false;}}
}}

function ouvrirMarquerRealise(id){{const a=SUIVI.actions.find(x=>x.id===id);if(!a)return;actionEnCours=id;document.getElementById('modal-action-titre').textContent=a.titre;document.getElementById('modal-date').value=new Date().toISOString().split('T')[0];document.getElementById('modal-note').value=a.note||'';openModal('modal-realise');}}
async function confirmerRealise(){{const a=SUIVI.actions.find(x=>x.id===actionEnCours);if(!a)return;a.statut='realise';a.date_realisation=document.getElementById('modal-date').value;a.note=document.getElementById('modal-note').value;closeModal('modal-realise');const ok=await saveSuiviToGitHub(SUIVI);if(ok){{renderActions();updateBadge();}}}}
async function marquerEnCours(id){{const a=SUIVI.actions.find(x=>x.id===id);if(!a)return;a.statut='en_cours';const ok=await saveSuiviToGitHub(SUIVI);if(ok){{renderActions();updateBadge();}}}}
async function confirmerNouvelle(){{const titre=document.getElementById('new-titre').value.trim();if(!titre){{showToast('Titre obligatoire','error');return;}}SUIVI.actions.push({{id:'A'+String(SUIVI.actions.length+1).padStart(3,'0'),titre,detail:document.getElementById('new-detail').value,statut:document.getElementById('new-statut').value,date_cible:document.getElementById('new-date').value||null,date_realisation:null,note:document.getElementById('new-note').value}});closeModal('modal-new');['new-titre','new-detail','new-date','new-note'].forEach(i=>document.getElementById(i).value='');const ok=await saveSuiviToGitHub(SUIVI);if(ok){{renderActions();updateBadge();}}}}

function filterActions(f,btn){{filtreActif=f;document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');renderActions();}}
function updateBadge(){{const n=SUIVI.actions.filter(a=>a.statut==='en_attente').length;document.getElementById('badge-attente').textContent=n>0?n:'';}}

function renderActions(){{
  const total=SUIVI.actions.length,done=SUIVI.actions.filter(a=>a.statut==='realise').length,pct=total?Math.round(done/total*100):0;
  document.getElementById('actions-count').textContent=done+'/'+total;
  document.getElementById('actions-progress').style.width=pct+'%';
  document.getElementById('actions-done-label').textContent=done+' réalisée'+(done>1?'s':'');
  document.getElementById('actions-total-label').textContent=total+' au total';
  const vis=filtreActif==='tous'?SUIVI.actions:SUIVI.actions.filter(a=>a.statut===filtreActif);
  const el=document.getElementById('actions-list');
  if(!vis.length){{el.innerHTML='<div style="text-align:center;color:var(--text2);font-size:13px;padding:2rem 0">Aucune action</div>';return;}}
  el.innerHTML=vis.map(a=>{{
    const nc=a.statut==='realise'?'num-done':a.statut==='en_cours'?'num-cours':'num-wait';
    const bc=a.statut==='realise'?'b-done':a.statut==='en_cours'?'b-cours':'b-wait';
    const bl=a.statut==='realise'?'Réalisé ✓':a.statut==='en_cours'?'En cours':'En attente';
    const ds=a.date_realisation?'✓ '+a.date_realisation:(a.date_cible?'📅 '+a.date_cible:'');
    const btns=a.statut!=='realise'?`<div style="display:flex;flex-direction:column;gap:6px;flex-shrink:0">${{a.statut==='en_attente'?`<button class="btn btn-warn btn-sm" onclick="marquerEnCours('${{a.id}}')">En cours</button>`:''}}
      <button class="btn btn-success btn-sm" onclick="ouvrirMarquerRealise('${{a.id}}')">✓ Réalisé</button></div>`:'';
    return `<div class="action-card ${{a.statut==='realise'?'done':''}}">
      <div class="action-num ${{nc}}">${{a.id}}</div>
      <div style="flex:1">
        <div style="font-size:14px;font-weight:600;margin-bottom:3px">${{a.titre}}</div>
        <div style="font-size:12px;color:var(--text2);line-height:1.5">${{a.detail}}</div>
        ${{a.note?`<div style="font-size:11px;color:var(--text3);margin-top:4px;font-style:italic">${{a.note}}</div>`:''}}
        <div style="display:flex;align-items:center;gap:8px;margin-top:8px;flex-wrap:wrap">
          <span class="badge ${{bc}}">${{bl}}</span>
          ${{ds?`<span style="font-size:11px;color:var(--text2);font-family:'DM Mono',monospace">${{ds}}</span>`:''}}
        </div>
      </div>
      ${{btns}}
    </div>`;
  }}).join('');
}}

function renderPositions(){{
  let best={{pv:-Infinity,ticker:''}};
  let totalVal=0;
  document.getElementById('positions-table').innerHTML=POSITIONS.map(p=>{{
    if(p.pv>best.pv)best={{pv:p.pv,ticker:p.ticker}};
    totalVal+=p.cours*p.qte;
    const s=p.pv>=0?'+':'',cl=p.pv>=0?'up':'dn',c=p.poids>30?'#FF4D6D':p.poids>20?'#FFB547':'#00E5A0';
    const b=p.halal==='conforme'?'<span class="badge b-halal">Halal</span>':'<span class="badge b-warn">À clarifier</span>';
    return `<tr><td><strong>${{p.ticker}}</strong><br><span style="font-size:11px;color:var(--text2)">${{p.nom}}</span></td>
      <td style="font-family:'DM Mono',monospace">${{p.qte.toLocaleString('fr-FR')}}</td>
      <td style="font-family:'DM Mono',monospace">${{p.cmp.toLocaleString('fr-FR')}}</td>
      <td style="font-family:'DM Mono',monospace">${{p.cours.toLocaleString('fr-FR')}}</td>
      <td class="${{cl}}" style="font-family:'DM Mono',monospace">${{s}}${{Math.round(p.pv).toLocaleString('fr-FR')}}</td>
      <td><span style="font-weight:600;color:${{c}};font-family:'DM Mono',monospace">${{p.poids}}%</span><div class="bar-bg"><div class="bar-f" style="width:${{Math.min(p.poids,100)}}%;background:${{c}}"></div></div></td>
      <td>${{b}}</td></tr>`;
  }}).join('');
  document.getElementById('m-titres').textContent=Math.round(totalVal/1000000*10)/10+'M';
  document.getElementById('m-pos').textContent=POSITIONS.length;
  document.getElementById('m-best').textContent='+'+Math.round(best.pv/1000)+'k';
  document.getElementById('m-best-label').textContent=best.ticker;
}}

function renderOpportunites(){{
  document.getElementById('opp-grid').innerHTML=(OPPORTUNITES.length?OPPORTUNITES:[{{ticker:'—',nom:'Aucune opportunité cette semaine',secteur:'',conviction:0,per:null,div:null,cours:0,signal:'',bni:false,rang:null}}]).map(o=>{{
    const stars='★'.repeat(o.conviction)+'☆'.repeat(5-o.conviction);
    return `<div class="opp-card ${{o.bni?'bni':''}}">
      <div style="font-size:20px;font-weight:800;margin-bottom:2px">${{o.ticker}}</div>
      <div style="font-size:11px;color:var(--text2);margin-bottom:10px">${{o.nom}} · <span style="color:var(--info)">${{o.secteur}}</span></div>
      <div style="color:var(--warn);font-size:13px;margin-bottom:8px">${{stars}}</div>
      ${{o.cours?`<div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px"><span style="color:var(--text2)">Cours</span><span style="font-family:'DM Mono',monospace;font-weight:600">${{o.cours.toLocaleString('fr-FR')}} FCFA</span></div>`:''}},
      ${{o.per?`<div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px"><span style="color:var(--text2)">PER</span><span style="font-family:'DM Mono',monospace;font-weight:600">${{o.per}}x</span></div>`:''}}
      ${{o.div?`<div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px"><span style="color:var(--text2)">Dividende</span><span style="color:var(--up);font-family:'DM Mono',monospace;font-weight:600">${{o.div}}%</span></div>`:''}}
      <div style="font-size:11px;color:var(--text2);margin-top:6px">${{o.signal}}</div>
      ${{o.bni?`<div style="margin-top:8px;font-size:10px;color:var(--accent);font-family:'DM Mono',monospace">TOP ${{o.rang}} BNI FINANCES</div>`:''}}
      <div style="margin-top:10px"><span class="badge b-halal">Halal ✓</span></div>
    </div>`;
  }}).join('');
}}

function renderDividendes(){{
  document.getElementById('div-grid').innerHTML=(DIVIDENDES.length?DIVIDENDES:[]).map(d=>{{
    const purif=d.purification&&d.sadaqa
      ?`<div style="margin-top:10px;background:var(--dn-bg);border-radius:8px;padding:8px 12px;font-size:11px;color:#FFB3C0;border:1px solid rgba(255,77,109,.15)"><strong>Purification requise</strong><br>Taux haram : ${{d.pct_haram}}% · Sadaqa : <strong>${{d.sadaqa?.toLocaleString('fr-FR')}} FCFA</strong><br>Net halal : ${{d.net_halal?d.net_halal.toLocaleString('fr-FR')+' FCFA':'À calculer'}}</div>`
      :`<div style="margin-top:10px;font-size:11px;color:var(--up)">✓ Aucune purification requise</div>`;
    return `<div class="div-card">
      <div style="font-size:16px;font-weight:800;margin-bottom:4px">${{d.ticker}} <span style="font-size:13px;color:var(--text2);font-weight:400">${{d.nom}}</span></div>
      <div style="font-size:24px;font-weight:800;color:var(--warn);font-family:'DM Mono',monospace">${{d.div_net?.toLocaleString('fr-FR')}} <span style="font-size:14px;color:var(--text2);font-weight:400">FCFA/titre</span></div>
      <div style="font-size:12px;color:var(--text2);margin-bottom:8px">${{d.qte?.toLocaleString('fr-FR')}} titres → <strong style="color:var(--text)">${{d.total?.toLocaleString('fr-FR')}} FCFA</strong></div>
      <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px;color:var(--text2)"><span>Ex-dividende</span><span style="color:var(--text);font-family:'DM Mono',monospace">${{d.ex_div}}</span></div>
      <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px;color:var(--text2)"><span>Paiement</span><span style="color:var(--text);font-family:'DM Mono',monospace">${{d.paiement}}</span></div>
      <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--text2)"><span>Rendement</span><span style="color:var(--up);font-family:'DM Mono',monospace">${{d.rendement}}%</span></div>
      ${{purif}}
    </div>`;
  }}).join('') || '<div style="color:var(--text2);font-size:13px">Aucun dividende à venir</div>';
}}

function initCharts(){{
  const labels=POSITIONS.map(p=>p.ticker),values=POSITIONS.map(p=>p.poids),colors=POSITIONS.map(p=>COLORS[p.ticker]||'#6B7280');
  new Chart(document.getElementById('chartDonut'),{{type:'doughnut',data:{{labels,datasets:[{{data:values,backgroundColor:colors,borderWidth:0,hoverOffset:6}}]}},options:{{responsive:true,maintainAspectRatio:false,cutout:'65%',plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:ctx=>` ${{ctx.label}} : ${{ctx.parsed.toFixed(1)}}%`}}}}}}}}}});
  document.getElementById('chart-legend').innerHTML=POSITIONS.map(p=>`<div class="chart-legend-item"><div class="chart-dot" style="background:${{COLORS[p.ticker]||'#6B7280'}}"></div>${{p.ticker}} ${{p.poids}}%</div>`).join('');
  const pv=POSITIONS.filter(p=>p.pv!==0);
  new Chart(document.getElementById('chartBar'),{{type:'bar',data:{{labels:pv.map(p=>p.ticker),datasets:[{{data:pv.map(p=>Math.round(p.pv/1000)),backgroundColor:pv.map(p=>p.pv>=0?'rgba(0,229,160,.7)':'rgba(255,77,109,.7)'),borderRadius:4,borderSkipped:false}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:ctx=>` ${{ctx.parsed.y}}k FCFA`}}}}}},scales:{{x:{{grid:{{color:'rgba(255,255,255,.04)'}},ticks:{{color:'#8892A4',font:{{family:'DM Mono',size:11}}}}}},y:{{grid:{{color:'rgba(255,255,255,.04)'}},ticks:{{color:'#8892A4',font:{{family:'DM Mono',size:11}},callback:v=>v+'k'}}}}}}}}}});
}}

updateTokenBanner();
renderPositions();
renderActions();
renderOpportunites();
renderDividendes();
initCharts();
updateBadge();
</script>
</body>
</html>"""


def envoyer_email(html, destinataire):
    """Envoie le rapport par email via Gmail SMTP"""
    expediteur   = os.environ.get("REPORT_EMAIL", "")
    mot_de_passe = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not mot_de_passe:
        print("[synthese] GMAIL_APP_PASSWORD non défini — email ignoré")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Synthèse BRVM — {datetime.now().strftime('%d/%m/%Y')}"
    msg["From"]    = expediteur
    msg["To"]      = destinataire
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
            s.login(expediteur, mot_de_passe)
            s.sendmail(expediteur, destinataire, msg.as_string())
        print(f"[synthese] Email envoyé → {destinataire}")
    except Exception as e:
        print(f"[synthese] Erreur email : {e}")


def run(donnees):
    """Point d'entrée principal"""
    print("[synthese] Génération du dashboard v3...")
    html = generer_dashboard(donnees)

    destinataire = os.environ.get("REPORT_EMAIL", "")
    if destinataire:
        envoyer_email(html, destinataire)

    print("[synthese] Terminé")
    return html
