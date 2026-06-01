import json
import logging
import os

from openai import OpenAI

logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
VISION_MODEL = os.getenv("VISION_MODEL", "gpt-4o")

WINE_LABEL_SYSTEM_PROMPT = (
    "Tu es Paul, un sommelier virtuel expert dans l'application WineMind. "
    "Analyse l'image de l'étiquette de vin et extrait TOUTES les informations requises pour la base de données. "
    "Sois extrêmement précis et professionnel. Si une information n'est pas visible sur l'étiquette, "
    "utilise tes connaissances oenologiques pour la déduire logiquement.\n\n"
    "INSTRUCTIONS CRITIQUES :\n"
    "- Tu dois remplir TOUS les champs ci-dessous sans exception\n"
    "- Si une info n'est pas visible, déduis-la selon le contexte (région, type de vin, etc)\n"
    "- Sois précis sur les appellations, cépages, et classifications\n"
    "- Enrichis avec tes connaissances si nécessaire\n"
    "- Pour les niveaux (body, tannin, fruit), utilise des scores 0.0-1.0\n"
    "- Pour food_pairings, liste 3-4 accords mets-vin pertinents\n"
    "- Pour la fenêtre de garde (drink_from, peak_year, drink_to), déduis des ANNÉES "
    "(entiers) à partir du millésime et du type/cépage/région : drink_from = début de "
    "la fenêtre optimale, peak_year = apogée, drink_to = fin de garde\n\n"
    "Format de réponse JSON OBLIGATOIRE :\n"
    "{\n"
    '  "chat_response": "Message expliquant l analyse et si ce vin semble exister déjà",\n'
    '  "wine_data": {\n'
    '    "name": "Nom COMPLET du vin (appellation exacte)",\n'
    '    "winery": "Domaine/producteur exact",\n'
    '    "year": 2020,\n'
    '    "region": "Région viticole précise",\n'
    '    "country": "Pays",\n'
    '    "variety": "Cépage(s) principaux",\n'
    '    "type": "Rouge/Blanc/Rosé/Mousseux/Nature/Doux",\n'
    '    "alcohol_percentage": 13.5,\n'
    '    "description": "Description détaillée du style et arômes",\n'
    '    "designation": "Classification (Grand Cru, Premier Cru, etc)",\n'
    '    "province": "Sous-région ou province",\n'
    '    "price": 25.0,\n'
    '    "points": 92,\n'
    '    "body_level": 0.7,\n'
    '    "tannin_level": 0.6,\n'
    '    "fruit_level": 0.8,\n'
    '    "food_pairings": ["Viande rouge", "Fromage", "Champignons"],\n'
    '    "drink_from": 2023,\n'
    '    "peak_year": 2028,\n'
    '    "drink_to": 2035,\n'
    '    "confidence": 0.95\n'
    "  }\n"
    "}\n\n"
    'DÉDUCTION SI NON VISIBLE :\n'
    '- region_2: sous-région plus spécifique si applicable\n'
    '- price: prix estimé selon le type et réputation\n'
    '- points: note estimée 85-95 selon la qualité perçue\n'
    '- body_level: 0.3(léger)-0.7(medium)-0.9(puissant)\n'
    '- tannin_level: 0.2(faible)-0.6(moyen)-0.9(élevé)\n'
    '- fruit_level: 0.3(discret)-0.7(équilibré)-0.9(puissant)\n'
    '- drink_from/peak_year/drink_to: fenêtre de garde plausible selon le millésime et '
    'le potentiel de garde (vin léger à boire jeune = fenêtre courte ; grand vin de garde '
    '= fenêtre longue). Toujours drink_from <= peak_year <= drink_to.\n\n'
    'En cas d\'étiquette totalement illisible :\n'
    '{"error": "label_unreadable", "detail": "explication"}'
)


def _get_client() -> OpenAI:
    chat_api_key = os.getenv("CHAT_API_KEY")
    github_token = os.getenv("GITHUB_TOKEN")
    
    if chat_api_key:
        return OpenAI(api_key=chat_api_key)
    elif github_token:
        return OpenAI(
            base_url="https://models.inference.ai.azure.com",
            api_key=github_token,
        )
    else:
        raise RuntimeError("CHAT_API_KEY ou GITHUB_TOKEN manquant dans .env")


def analyze_wine_label(image_url: str) -> dict:
    """Analyse une étiquette de vin et retourne les informations extraites.

    Args:
        image_url: URL signée de l'image de l'étiquette.

    Returns:
        Dictionnaire JSON avec l'analyse du vin.

    Raises:
        RuntimeError: Si l'appel au modèle échoue.
        ValueError: Si la réponse n'est pas du JSON valide.
    """
    client = _get_client()

    user_content = [
        {
            "type": "image_url",
            "image_url": {"url": image_url},
        }
    ]

    messages = [
        {"role": "system", "content": WINE_LABEL_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    vision_model = os.getenv("VISION_MODEL", "gpt-4o")
    try:
        response = client.chat.completions.create(
            model=vision_model,
            messages=messages,
            temperature=0.3,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        logger.error("Erreur GitHub Models (wine label): %s", e)
        raise RuntimeError("Échec de l'appel au modèle d'analyse d'étiquette") from e

    raw_content = response.choices[0].message.content
    if not raw_content:
        raise ValueError("Le modèle a retourné une réponse vide")

    try:
        return json.loads(raw_content)
    except json.JSONDecodeError as e:
        logger.error("Réponse non-JSON du modèle: %s", raw_content[:500])
        raise ValueError("Le modèle n'a pas retourné du JSON valide") from e


# Variante texte-only : enrichit un vin du catalogue à partir de ses seules
# métadonnées (pas d'image). Ne produit QUE le profil gustatif, les accords et
# la fenêtre de garde — les identités du vin (nom, domaine…) restent inchangées.
WINE_ENRICH_SYSTEM_PROMPT = (
    "Tu es Paul, un sommelier virtuel expert dans l'application WineMind. "
    "À partir des informations textuelles d'un vin (nom, domaine, région, cépage, "
    "millésime, type, description), déduis son profil oenologique avec tes "
    "connaissances. N'invente pas l'identité du vin : utilise uniquement les champs "
    "demandés ci-dessous.\n\n"
    "INSTRUCTIONS :\n"
    "- body_level, tannin_level, fruit_level : scores 0.0-1.0 "
    "(0.3 léger / 0.7 medium / 0.9 puissant)\n"
    "- food_pairings : 3-4 accords mets-vin pertinents\n"
    "- drink_from, peak_year, drink_to : années (entiers) de la fenêtre de garde, "
    "déduites du millésime et du type/cépage/région ; toujours "
    "drink_from <= peak_year <= drink_to\n\n"
    "Format de réponse JSON OBLIGATOIRE :\n"
    "{\n"
    '  "body_level": 0.7,\n'
    '  "tannin_level": 0.6,\n'
    '  "fruit_level": 0.8,\n'
    '  "food_pairings": ["Viande rouge", "Fromage", "Champignons"],\n'
    '  "drink_from": 2023,\n'
    '  "peak_year": 2028,\n'
    '  "drink_to": 2035\n'
    "}\n\n"
    "Si les informations sont insuffisantes pour déduire quoi que ce soit :\n"
    '{"error": "insufficient_data", "detail": "explication"}'
)


def enrich_wine_from_metadata(wine: dict) -> dict:
    """Déduit le profil oenologique d'un vin à partir de ses métadonnées texte.

    Args:
        wine: Row `wines` (name/winery/region/province/country/variety/year/type/description).

    Returns:
        Dict JSON avec body/tannin/fruit_level, food_pairings, drink_from/peak_year/drink_to.

    Raises:
        RuntimeError: Si l'appel au modèle échoue.
        ValueError: Si la réponse n'est pas du JSON valide.
    """
    client = _get_client()

    fields = ("name", "winery", "region", "province", "country", "variety", "year", "type", "description")
    metadata = {k: wine.get(k) for k in fields if wine.get(k) is not None}
    user_content = (
        "Informations du vin à enrichir :\n"
        + json.dumps(metadata, ensure_ascii=False)
    )

    messages = [
        {"role": "system", "content": WINE_ENRICH_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    model = os.getenv("VISION_MODEL", "gpt-4o")
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        logger.error("Erreur modèle (enrichissement vin): %s", e)
        raise RuntimeError("Échec de l'appel au modèle d'enrichissement") from e

    raw_content = response.choices[0].message.content
    if not raw_content:
        raise ValueError("Le modèle a retourné une réponse vide")

    try:
        return json.loads(raw_content)
    except json.JSONDecodeError as e:
        logger.error("Réponse non-JSON du modèle (enrichissement): %s", raw_content[:500])
        raise ValueError("Le modèle n'a pas retourné du JSON valide") from e
