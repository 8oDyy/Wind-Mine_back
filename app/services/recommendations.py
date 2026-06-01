"""Service de recommandations de vins (« Découvertes »).

Construit des **catégories** (carrousels) de vins du catalogue `wines`,
personnalisées par le profil utilisateur (`profiles`) et le contenu de sa cave
(`user_cellar`). Chaque catégorie = une requête PostgREST ciblée avec `LIMIT`
sur un index : on ne scanne JAMAIS les ~130k vins.

Performance :
- une requête par catégorie, `WHERE <filtre> ORDER BY points DESC LIMIT n` ;
- requêtes lancées **en parallèle** (`asyncio.gather` + `asyncio.to_thread`,
  le client Supabase étant synchrone comme dans le reste du projet) ;
- cache **mémoire par utilisateur**, TTL court (absorbe les re-render / refresh
  Flutter sans retaper la base). Une seule instance prod → pas besoin de Redis.

Forme de sortie : les vins sont les **rows `wines` brutes** (iso parser Flutter).
"""
import asyncio
import logging
import os
import re
import time
import unicodedata
from collections import Counter
from typing import Optional
from uuid import UUID

from supabase import create_client, Client

logger = logging.getLogger(__name__)

# Colonnes catalogue renvoyées telles quelles (row `wines` brute attendue par le front).
# "*" suffirait, mais on liste explicitement pour documenter le contrat de forme.
_WINE_SELECT = "*"

# Seuils de qualité (sur la colonne `points`, échelle ~80-100 des données catalogue).
_TOP_RATED_MIN_POINTS = 90
_AFFORDABLE_MIN_POINTS = 86  # rangée "Petits prix" : qualité correcte mais on relâche un peu pour aller chercher le vraiment cheap.

# Plafond de prix « grand public » appliqué à TOUTES les rangées générales (for_you,
# top_rated, region_*, par type, discover, affordable). Cible produit : la plupart des
# vins ~20. Avec la corrélation prix↔points (tri `points DESC` pousse vers le plafond),
# un cap à 30 fait atterrir les recos majoritairement en ~18-28 (centrées ~20). Garder
# `points>=88` reste sûr : >17k vins en 20-30 à ≥88 pts.
# NB PostgREST : `price <= MAX` exclut nativement les prix NULL (un `lte` ne matche pas
# NULL) — c'est voulu : pas de prix inconnu dans les rangées grand public.
_MAX_EVERYDAY_PRICE = 30.0

# Rangée "Petits prix" : vraiment cheap, triée par prix croissant (bonnes affaires 8-14).
_AFFORDABLE_MAX_PRICE = 15.0

# UNE seule rangée chère assumée (placée en bas) : trophées éditorialisés, SANS plafond.
_PRESTIGE_MIN_POINTS = 96

# Mapping libellé de préférence -> valeur de `wines.type`.
# `profiles.preference` est un texte libre d'onboarding (ex. « Vin Pétillant »),
# NON iso avec `wines.type`. On mappe donc par **sous-chaîne** sur le libellé
# désaccentué/minuscule → robuste quels que soient les libellés saisis.
# Valeurs réelles de `wines.type` (MCP) : Rouge, Blanc, Champagne, Rosé.
# L'effervescent du catalogue = `type = 'Champagne'`. Ordre = priorité de match.
_PREFERENCE_SUBSTRING_TO_TYPE = (
    ("petillant", "Champagne"),  # "pétillant" désaccentué
    ("champagne", "Champagne"),
    ("effervescent", "Champagne"),
    ("bulle", "Champagne"),
    ("rouge", "Rouge"),
    ("blanc", "Blanc"),
    ("rose", "Rosé"),  # "rosé" désaccentué
)

# Catégories "par type" (evergreen) : clé front -> (valeur `wines.type`, titre).
_TYPE_CATEGORIES = [
    ("red", "Rouge", "Grands Rouges"),
    ("white", "Blanc", "Blancs à découvrir"),
    ("sparkling", "Champagne", "Bulles & Champagnes"),
    ("rose", "Rosé", "Rosés"),
]
# Nb max de carrousels evergreen "par type" ajoutés (vise ~6-7 rangées au total).
_MAX_TYPE_CATEGORIES = 3


def _get_client() -> Client:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_service_role_key:
        raise RuntimeError("SUPABASE_URL ou SUPABASE_SERVICE_ROLE_KEY manquant dans .env")
    return create_client(supabase_url, supabase_service_role_key)


# ─────────────────────────── Cache mémoire par user ───────────────────────────

_CACHE_TTL_SECONDS = 90
# user_id (str) -> (timestamp_monotonic, liste de catégories déjà sérialisables)
_cache: dict[str, tuple[float, list[dict]]] = {}


def _cache_get(user_id: UUID) -> Optional[list[dict]]:
    entry = _cache.get(str(user_id))
    if entry is None:
        return None
    ts, value = entry
    if time.monotonic() - ts > _CACHE_TTL_SECONDS:
        _cache.pop(str(user_id), None)
        return None
    return value


def _cache_set(user_id: UUID, categories: list[dict]) -> None:
    _cache[str(user_id)] = (time.monotonic(), categories)


# ─────────────────────────── Lecture du contexte user ───────────────────────────

def _normalize(label: Optional[str]) -> str:
    """Minuscule + trim + désaccentué, pour comparer des libellés libres de façon tolérante.

    Ex. « Vin Pétillant » -> « vin petillant » (le match `preference` se fait par sous-chaîne).
    """
    text = (label or "").strip().lower()
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _slug(label: str) -> str:
    """Slug stable et ASCII pour une clé de catégorie (ex. région). 'Côtes du Rhône' -> 'cotes-du-rhone'."""
    base = _normalize(label)
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-") or "region"


def _fetch_profile(client: Client, user_id: UUID) -> dict:
    """Profil utilisateur (preference/niveau/objectif), {} si absent."""
    try:
        response = (
            client.table("profiles")
            .select("preference, niveau, objectif")
            .eq("id", str(user_id))
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else {}
    except Exception as e:
        logger.warning("Lecture profil pour reco échouée (on continue sans perso): %s", e)
        return {}


def _fetch_cellar_context(client: Client, user_id: UUID) -> dict:
    """Dérive du contenu de la cave : ids déjà possédés, région dominante, type dominant.

    Lecture légère (seules les colonnes utiles du vin imbriqué), bornée par user
    (index user_id). Tolérante : toute erreur => contexte vide (pas de perso cave).
    """
    try:
        response = (
            client.table("user_cellar")
            .select("wine_id, wines(region, type)")
            .eq("user_id", str(user_id))
            .execute()
        )
        rows = response.data or []
    except Exception as e:
        logger.warning("Lecture cave pour reco échouée (on continue sans perso): %s", e)
        return {
            "owned_wine_ids": [], "owned_regions": [],
            "dominant_region": None, "dominant_type": None,
        }

    owned_wine_ids = [r["wine_id"] for r in rows if r.get("wine_id")]
    regions = Counter()
    types = Counter()
    for r in rows:
        wine = r.get("wines") or {}
        if wine.get("region"):
            regions[wine["region"]] += 1
        if wine.get("type"):
            types[wine["type"]] += 1

    dominant_region = regions.most_common(1)[0][0] if regions else None
    dominant_type = types.most_common(1)[0][0] if types else None

    return {
        "owned_wine_ids": owned_wine_ids,
        "owned_regions": list(regions.keys()),
        "dominant_region": dominant_region,
        "dominant_type": dominant_type,
    }


# ─────────────────────────── Requêtes par catégorie ───────────────────────────

def _base_query(client: Client, limit: int):
    """SELECT de base : row brute, tri qualité décroissante, borné par LIMIT."""
    return client.table("wines").select(_WINE_SELECT).order("points", desc=True).limit(limit)


def _cap_price(query, cap: float = _MAX_EVERYDAY_PRICE):
    """Plafonne le prix d'une rangée « grand public » (exclut aussi les prix NULL).

    Empêche `ORDER BY points DESC` de remonter des trophées hors de prix. À ne PAS
    appliquer à `affordable` (plafond bas dédié) ni à `prestige` (sans plafond).
    """
    return query.lte("price", cap)


def _exclude_owned(query, owned_wine_ids: list[str]):
    """Exclut les vins déjà en cave (PostgREST `not.in`), si la liste n'est pas vide.

    On borne la liste pour ne pas fabriquer un filtre géant (cave réaliste = petite).
    """
    if not owned_wine_ids:
        return query
    # `in_` attend un itérable de valeurs ; il construit lui-même le `(...)` PostgREST.
    # On borne la liste (cave réaliste = petite) pour ne pas fabriquer un filtre géant.
    ids = [str(i) for i in owned_wine_ids[:200]]
    return query.not_.in_("id", ids)


def _run(query) -> list[dict]:
    """Exécute une requête PostgREST synchrone et renvoie les rows (liste, jamais None)."""
    return query.execute().data or []


def _map_preference(preference: Optional[str]) -> Optional[str]:
    """Mappe un libellé de préférence libre vers une valeur de `wines.type`, ou None.

    Match par sous-chaîne sur le libellé désaccentué (ex. « Vin Pétillant » -> 'Champagne').
    `preference` est une multi-sélection jointe par « , » (ex. « Vin Rouge, Vin Blanc ») :
    on renvoie le premier type dans l'ordre des règles `_PREFERENCE_SUBSTRING_TO_TYPE`.

    NB (amélioration v2 possible) : ce « premier matché » suit l'ordre des règles, pas
    l'ordre de saisie de l'utilisateur (« Vin Blanc, Vin Rouge » -> Rouge car Rouge est
    testé avant Blanc). Déterministe et suffisant pour la pondération perso v1 ; pour
    respecter l'ordre de saisie, splitter sur « , » et mapper token par token.
    """
    norm = _normalize(preference)
    if not norm:
        return None
    for needle, wine_type in _PREFERENCE_SUBSTRING_TO_TYPE:
        if needle in norm:
            return wine_type
    return None


def _preferred_type(profile: dict, cellar: dict) -> Optional[str]:
    """Type de vin préféré : d'abord `profiles.preference` (mappé), sinon type dominant en cave."""
    pref = _map_preference(profile.get("preference"))
    if pref:
        return pref
    return cellar.get("dominant_type")


def _build_category_specs(profile: dict, cellar: dict, limit: int) -> list[dict]:
    """Construit la liste ordonnée des catégories à requêter.

    Chaque spec = {key, title, subtitle, build(client)->query}. L'ordre ici est
    l'ordre d'affichage des carrousels côté front. Les catégories perso d'abord.
    """
    owned = cellar.get("owned_wine_ids", [])
    region = cellar.get("dominant_region")
    specs: list[dict] = []

    # 1) "Pour vous" : type préféré (profil sinon cave), hors vins possédés, sous plafond
    # grand public (sinon « Pour vous » en Champagne = Krug/Cristal/Salon à 250-617). Omise si pas de type.
    pref_type = _preferred_type(profile, cellar)
    if pref_type:
        specs.append({
            "key": "for_you",
            "title": "Pour vous",
            "subtitle": "D'après vos goûts",
            "build": lambda c, t=pref_type: _exclude_owned(
                _cap_price(_base_query(c, limit).eq("type", t).gte("points", _AFFORDABLE_MIN_POINTS)),
                owned,
            ),
        })

    # 2) Région dominante de la cave (hors vins possédés), sous plafond. Omise si cave vide.
    if region:
        specs.append({
            "key": f"region_{_slug(region)}",
            "title": f"À découvrir en {region}",
            "subtitle": "Comme dans votre cave",
            "build": lambda c, r=region: _exclude_owned(
                _cap_price(_base_query(c, limit).eq("region", r)), owned
            ),
        })

    # 3) Mieux notés (global, repli universel — toujours présent), sous plafond grand public.
    specs.append({
        "key": "top_rated",
        "title": "Les mieux notés",
        "subtitle": None,
        "build": lambda c: _cap_price(_base_query(c, limit).gte("points", _TOP_RATED_MIN_POINTS)),
    })

    # 4) Petits prix : la rangée la moins chère. Plafond fixe bas, qualité correcte,
    # triée par PRIX CROISSANT pour faire remonter les vraies bonnes affaires (8-14)
    # au lieu du cluster collé au plafond. (Distincte du grand public ~20.)
    specs.append({
        "key": "affordable",
        "title": "Petits prix",
        "subtitle": f"Sous {int(_AFFORDABLE_MAX_PRICE)} €",
        "build": lambda c: (
            c.table("wines").select(_WINE_SELECT)
            .gte("points", _AFFORDABLE_MIN_POINTS)
            .lte("price", _AFFORDABLE_MAX_PRICE)
            .order("price", desc=False)
            .limit(limit)
        ),
    })

    # 5) Carrousels evergreen "par type" (curated), en sautant le type déjà couvert par "for_you",
    # bornés à _MAX_TYPE_CATEGORIES pour viser ~6-7 rangées au total.
    added_types = 0
    for key, wine_type, title in _TYPE_CATEGORIES:
        if added_types >= _MAX_TYPE_CATEGORIES:
            break
        if wine_type == pref_type:
            continue
        specs.append({
            "key": key,
            "title": title,
            "subtitle": None,
            "build": lambda c, t=wine_type: _cap_price(_base_query(c, limit).eq("type", t)),
        })
        added_types += 1

    # 6) "À découvrir" : régions absentes de la cave (sinon catalogue diversifié), hors vins
    # possédés, sous plafond grand public.
    owned_regions = cellar.get("owned_regions") or []
    def _build_discover(c, regions=owned_regions):
        q = _exclude_owned(_cap_price(_base_query(c, limit)), owned)
        # Exclut les régions déjà présentes en cave pour pousser la découverte.
        for r in regions[:50]:
            q = q.neq("region", r)
        return q
    specs.append({
        "key": "discover",
        "title": "À découvrir",
        "subtitle": "Hors de vos sentiers habituels",
        "build": _build_discover,
    })

    # 7) "Prestige" (en bas) : trophées assumés, SANS plafond de prix. Choix éditorial
    # plutôt que défaut. Très haut de gamme uniquement (points >= 96).
    specs.append({
        "key": "prestige",
        "title": "Pour une grande occasion",
        "subtitle": "Les vins d'exception",
        "build": lambda c: _base_query(c, limit).gte("points", _PRESTIGE_MIN_POINTS),
    })

    return specs


# ─────────────────────────── Orchestration ───────────────────────────

async def get_recommendations(
    user_id: UUID,
    limit_per_category: int = 12,
    only_keys: Optional[set[str]] = None,
) -> list[dict]:
    """Construit les catégories de recommandations pour l'utilisateur.

    Args:
        user_id: ID de l'utilisateur (provient toujours du JWT côté router).
        limit_per_category: nb de vins max par carrousel.
        only_keys: si fourni, ne calcule que ces clés de catégorie.

    Returns:
        Liste de catégories sérialisables {key, title, subtitle, wines:[row brute]}.
        Les catégories sans aucun vin sont **omises**.
    """
    if only_keys is None:
        cached = _cache_get(user_id)
        if cached is not None:
            return cached

    client = _get_client()

    # Contexte user (profil + cave) lu en parallèle.
    profile, cellar = await asyncio.gather(
        asyncio.to_thread(_fetch_profile, client, user_id),
        asyncio.to_thread(_fetch_cellar_context, client, user_id),
    )

    specs = _build_category_specs(profile, cellar, limit_per_category)
    if only_keys is not None:
        specs = [s for s in specs if s["key"] in only_keys]

    # Une requête par catégorie, toutes lancées en parallèle.
    async def _execute(spec: dict) -> dict:
        try:
            wines = await asyncio.to_thread(lambda: _run(spec["build"](client)))
        except Exception as e:
            # Une catégorie en échec ne doit pas faire tomber toute la page.
            logger.warning("Catégorie reco '%s' échouée: %s", spec["key"], e)
            wines = []
        return {
            "key": spec["key"],
            "title": spec["title"],
            "subtitle": spec["subtitle"],
            "wines": wines,
        }

    results = await asyncio.gather(*(_execute(s) for s in specs))

    # Omettre les carrousels vides ; préserver l'ordre des specs.
    categories = [c for c in results if c["wines"]]

    if only_keys is None:
        _cache_set(user_id, categories)
    return categories
