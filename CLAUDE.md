# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Présentation

Backend API du chatbot sommelier **WineMind** (« Paul »). FastAPI async + OpenAI (vision/chat) + Supabase (stockage images & base de vins). Python 3.13. Déployé en production sur `https://winemind.fr`.

## Commandes

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # inclut requirements.txt + pytest

# Lancer le serveur (http://0.0.0.0:8000, reload activé)
python -m app.main

# Tests (la config pytest.ini ne collecte QUE tests/)
pytest tests/ -v
pytest tests/test_health.py::test_health_ok   # un seul test

# Docker local
docker compose up --build
```

`test_wine_endpoints.py` à la racine est un **script d'intégration manuel** qui frappe un serveur réel — il est volontairement exclu de la collecte pytest, ne pas le lancer en CI.

## Configuration (.env)

Variables requises (voir `.env.example`) : `CHAT_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_BUCKET_NAME`, `SUPABASE_WINE_LABELS_BUCKET`, `VISION_MODEL`.

**Provider LLM** : le projet utilise **OpenAI direct via `CHAT_API_KEY`**. Le code supporte aussi un fallback `GITHUB_TOKEN` (GitHub Models sur `models.inference.ai.azure.com`) mais ce n'est pas le mode utilisé. Au démarrage, `app.main` **lève une RuntimeError si aucune clé n'est présente** — c'est pourquoi `tests/test_health.py` injecte des variables factices *avant* d'importer l'app.

## Architecture

Pattern en 3 couches, une responsabilité par fichier :

- **`app/main.py`** — instancie FastAPI, monte les routers, définit `/health` et `/chat` (chat texte simple), configure CORS. Contient le `SYSTEM_PROMPT` de Paul.
- **`app/routers/`** — un router par feature, préfixe `/api`. Orchestrent : signed URL → analyse → validation Pydantic → réponse. Toute la gestion d'erreurs HTTP vit ici (mapping RuntimeError→502, ValueError→502, config manquante→500).
- **`app/services/`** — logique métier sans FastAPI. Chaque service a son propre `_get_client()` (les clients OpenAI/Supabase sont créés à la demande, **pas** au niveau module, pour ne pas exiger les secrets à l'import).
- **`app/schemas/`** — modèles Pydantic request/response par feature.

### Les trois features

| Endpoint | Router | Service(s) | Rôle |
|---|---|---|---|
| `POST /api/wine-pairing` | `wine_pairing.py` | `vision.py` | Photo de plat → 3 styles de vins (jamais de marque précise) |
| `POST /api/wine-label-analysis` | `wine_label.py` | `wine_analysis.py` + `wine_cellar.py` | Photo d'étiquette → 2 propositions (vin existant + nouveau), **sans écrire en base** |
| `POST /api/wine-label-add` | `wine_add.py` | `wine_cellar.py` | Ajoute réellement le vin choisi à `user_cellar` (existant via `wine_id`, ou nouveau via `wine_data`) |

Le workflow étiquette est en **deux temps** : `analysis` propose, `add` écrit. `analysis` ne touche jamais la BDD.

### Flux image (pairing & label)

`file_path` (chemin dans le bucket) → `create_signed_url()` (Supabase, URL temporaire 300s) → URL passée au modèle vision OpenAI → réponse JSON parsée. Le pairing utilise `SUPABASE_BUCKET_NAME` ; l'étiquette force le bucket `wine-labels`.

### Recherche de vin similaire (`wine_cellar.find_similar_wine`)

Cascade de 5 niveaux de matching sur la table `wines` (130k+ vins), du plus précis au plus large : nom exact → nom partiel → nom partiel + même winery → winery + région → région + nom similaire. Retourne `(vin|None, match_type)` ; `match_type` est converti en score de confiance dans `wine_label._get_match_confidence`.

### Base de données (Supabase)

Tables principales : `wines` (catalogue) et `user_cellar` (cave par utilisateur). Le schéma détaillé est accessible via le **MCP Supabase** — l'utiliser pour vérifier les colonnes avant toute modification touchant la base. `wine_cellar.create_wine` mappe explicitement chaque colonne de `wines`.

## Conventions & pièges

- **Format JSON strict des prompts vision** : `vision.py` et `wine_analysis.py` imposent au modèle un schéma JSON précis (`response_format={"type": "json_object"}`) et un format de sortie d'erreur (`{"error": ..., "detail": ...}`). Ne pas modifier ces prompts à la légère — les routers et schémas Pydantic en aval en dépendent directement.
- **CORS `allow_origins=["*"]`** : volontaire (app mobile), ne pas restreindre.
- **`_clean_wine_data`** (`wine_label.py`) : le modèle renvoie parfois des strings ("non visible", "13.5%"…) là où Pydantic attend des nombres. Cette fonction normalise avant validation — passer toute donnée issue du LLM par elle.
- Langue : tout le contenu utilisateur (prompts, messages, docstrings) est en **français**.

## Git & déploiement

- **Workflow : feature branch → PR vers `main`.** Ne jamais committer directement sur `main`. Branche actuelle de travail : `test`.
- CI/CD (`.github/workflows/ci-cd.yml`) : PR vers `main` → tests seuls ; push sur `main` → tests **puis** déploiement auto (rsync vers le VPS + `docker compose -f deploy/docker-compose.yml up --build` + healthcheck `https://winemind.fr/health`).
- **Le `.env` de production vit uniquement sur le serveur** : le rsync de déploiement l'exclut explicitement. Ne pas chercher à le synchroniser.
- Prod = `deploy/docker-compose.yml` (api interne + Caddy reverse-proxy HTTPS auto) ; `docker-compose.yml` racine = dev local simple.
