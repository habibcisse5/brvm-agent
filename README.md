# Agent BRVM

Agent automatique de veille et synthèse du portefeuille BRVM.

## Fonctionnement

- **Déclenchement** : tous les lundis à 8h (Paris) + manuel
- **Pipeline** : Veille marché → Screener halal → Synthèse
- **Sorties** : Dashboard GitHub Pages + Email hebdo

## Structure

```
brvm-agent/
├── .github/workflows/agent.yml   ← Workflow GitHub Actions
├── agents/
│   ├── orchestrator.py           ← Chef d'orchestre
│   ├── veille.py                 ← Cours BRVM en direct
│   ├── halal.py                  ← Filtre charia
│   └── synthese.py               ← Rapport HTML + email
├── data/
│   └── portefeuille.json         ← Positions actuelles
├── output/
│   └── index.html                ← Dashboard (auto-généré)
└── requirements.txt
```

## Secrets requis (Settings → Secrets → Actions)

| Secret | Description |
|--------|-------------|
| `ANTHROPIC_API_KEY` | Clé API Anthropic |
| `REPORT_EMAIL` | Email destinataire du rapport |
| `GMAIL_APP_PASSWORD` | Mot de passe d'application Gmail |

## Dashboard

Disponible sur : `https://TON-USERNAME.github.io/brvm-agent/`
