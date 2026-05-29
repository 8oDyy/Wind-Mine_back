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

Variables requises (voir `.env.example`) : `CHAT_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_BUCKET_NAME`, `SUPABASE_WINE_LABELS_BUCKET`, `VISION_MODEL`, `SUPABASE_JWT_SECRET` (Dashboard → Settings → API → JWT Secret, legacy HS256 ; sert à vérifier les access tokens des endpoints authentifiés).

**Provider LLM** : le projet utilise **OpenAI direct via `CHAT_API_KEY`**. Le code supporte aussi un fallback `GITHUB_TOKEN` (GitHub Models sur `models.inference.ai.azure.com`) mais ce n'est pas le mode utilisé. Au démarrage, `app.main` **lève une RuntimeError si aucune clé n'est présente** — c'est pourquoi `tests/test_health.py` injecte des variables factices *avant* d'importer l'app.

## Architecture

Pattern en 3 couches, une responsabilité par fichier :

- **`app/main.py`** — instancie FastAPI, monte les routers, définit `/health` et `/chat` (chat texte simple), configure CORS. Contient le `SYSTEM_PROMPT` de Paul.
- **`app/routers/`** — un router par feature, préfixe `/api`. Orchestrent : signed URL → analyse → validation Pydantic → réponse. Toute la gestion d'erreurs HTTP vit ici (mapping RuntimeError→502, ValueError→502, config manquante→500).
- **`app/services/`** — logique métier sans FastAPI. Chaque service a son propre `_get_client()` (les clients OpenAI/Supabase sont créés à la demande, **pas** au niveau module, pour ne pas exiger les secrets à l'import).
- **`app/schemas/`** — modèles Pydantic request/response par feature.
- **`app/dependencies/auth.py`** — dépendance `get_current_user_id` : vérifie le JWT Supabase (HS256, audience `authenticated`) et retourne l'`UUID` de l'utilisateur (claim `sub`).

### Features vision (LLM)

| Endpoint | Router | Service(s) | Rôle |
|---|---|---|---|
| `POST /api/wine-pairing` | `wine_pairing.py` | `vision.py` | Photo de plat → 3 styles de vins (jamais de marque précise) |
| `POST /api/wine-label-analysis` | `wine_label.py` | `wine_analysis.py` + `wine_cellar.py` | Photo d'étiquette → 2 propositions (vin existant + nouveau), **sans écrire en base** |
| `POST /api/wine-label-add` | `wine_add.py` | `wine_cellar.py` | Ajoute réellement le vin choisi à `user_cellar` (existant via `wine_id`, ou nouveau via `wine_data`) |

Le workflow étiquette est en **deux temps** : `analysis` propose, `add` écrit. `analysis` ne touche jamais la BDD.

### Features cave + profil (JWT requis)

Ces endpoints existent pour que l'app Flutter cesse d'accéder à Supabase en direct sur les données métier. **L'auth Supabase reste côté client** ; le backend ne fait que vérifier le JWT.

| Endpoint | Router | Rôle |
|---|---|---|
| `GET /api/cellar` | `cellar.py` | Liste la cave (liste de rows `user_cellar`) |
| `GET /api/cellar/last` | `cellar.py` | Dernier vin ajouté (404 si cave vide) |
| `POST /api/cellar` | `cellar.py` | Ajoute un vin catalogue (`wine_id`) ou custom (`custom_*`) → 201 |
| `DELETE /api/cellar/{cellar_id}` | `cellar.py` | Retire une bouteille → 204 |
| `PATCH /api/cellar/{cellar_id}/stock` | `cellar.py` | Met à jour le stock |
| `PATCH /api/profile` | `profile.py` | MAJ `niveau`/`preference`/`objectif` |
| `DELETE /api/account` | `profile.py` | **Vraie** suppression du compte auth (`auth.admin.delete_user`) ; les tables liées partent par cascade FK → 204 |

**Règles non négociables de ces endpoints :**
- L'`user_id` provient **uniquement du JWT** (`Depends(get_current_user_id)`), jamais du body/query. Une ressource non possédée → **404** (jamais 403, pour ne pas divulguer son existence).
- **Contrat de forme (important)** : les lectures cave renvoient les **rows `user_cellar` Supabase brutes** avec l'objet `wines` imbriqué (PostgREST `select("*, wines(*)")`), pour rester iso avec le parser Flutter `WineModel.fromCellarJson`. Ne **pas** envelopper dans un `response_model` qui renommerait/filtrerait les clés. `wines` vaut `null` pour un vin custom.

> Dette connue (hors périmètre) : `/api/wine-label-*` et `/api/wine-label-add` prennent encore `user_id` dans le body et ne sont **pas** authentifiés. À migrer vers `get_current_user_id` à terme.

### Flux image (pairing & label)

`file_path` (chemin dans le bucket) → `create_signed_url()` (Supabase, URL temporaire 300s) → URL passée au modèle vision OpenAI → réponse JSON parsée. Le pairing utilise `SUPABASE_BUCKET_NAME` ; l'étiquette force le bucket `wine-labels`.

### Recherche de vin similaire (`wine_cellar.find_similar_wine`)

Cascade de 5 niveaux de matching sur la table `wines` (130k+ vins), du plus précis au plus large : nom exact → nom partiel → nom partiel + même winery → winery + région → région + nom similaire. Retourne `(vin|None, match_type)` ; `match_type` est converti en score de confiance dans `wine_label._get_match_confidence`.

### Base de données (Supabase)

Projet `WineMind` (`ibjnyfvihtdbpdtieegr`, région eu-west-1, Postgres 17). RLS activé + policies owner sur toutes les tables. Toutes les FK `user_id → auth.users` sont en `ON DELETE CASCADE` (la suppression du compte auth nettoie automatiquement `profiles`/`user_cellar`/`dish_pictures`/`wine_labels`). Schéma du schéma `public` :

**`wines`** — catalogue de vins (PK `id` uuid). Colonnes : `name` (text, requis), `winery`, `year` (int), `region`, `region_2`, `province`, `country`, `variety`, `type` (text, défaut `'Rouge'`), `description`, `designation`, `points` (int, défaut 0), `price` (float8), `alcohol_percentage` (float8, nullable), `body_level`/`tannin_level`/`fruit_level` (float8, défaut 0.5), `food_pairings` (text[]), `stock` (int, défaut 0), `location` (text), `image_url` (text), `created_at`/`updated_at` (timestamptz).

**`user_cellar`** — cave d'un utilisateur (PK `id` uuid). FK `wine_id → wines.id`, `user_id → auth.users.id`. Référence un vin du catalogue OU stocke un vin perso via les colonnes `custom_*` (`custom_name`, `custom_year` *text*, `custom_type`, `custom_region`, `custom_points`, `custom_description`, `custom_variety`, `custom_winery`, `custom_price`). Autres colonnes : `stock` (int, défaut 1), `rating` (float8), `apogee` (text), `notes`, `location`, `purchase_date` (date), `purchase_price` (float8), `created_at`/`updated_at`.

**`profiles`** — profil utilisateur, PK `id` = `auth.users.id`. Colonnes : `email`, `prenom`, `nom`, `niveau`, `preference`, `objectif`, `created_at`.

**`dish_pictures`** / **`wine_labels`** — métadonnées des images uploadées (`user_id → auth.users.id`, `file_name`, `file_path`, `created_at`). `file_path` est le chemin passé aux endpoints pour générer la signed URL.

Toujours valider les colonnes via le **MCP Supabase** (`list_tables` verbose) avant une modification touchant la base. `wine_cellar.create_wine` mappe explicitement chaque colonne de `wines` ; `add_to_user_cellar` accepte `wine_id` nullable + tous les champs `custom_*`/`rating`/`apogee`/`purchase_*` via son paramètre `extra`.

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
