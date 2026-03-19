import json
import logging
import os

from openai import OpenAI

logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
VISION_MODEL = os.getenv("VISION_MODEL", "gpt-4o")

WINE_LABEL_SYSTEM_PROMPT = (
    "Tu es Paul, un sommelier virtuel expert dans l'application WineMind. "
    "Analyse l'image de l'étiquette de vin et extrait TOUTES les informations visibles. "
    "Sois extrêmement précis et professionnel. Si une information n'est pas visible, mets 'Non visible'. "
    "Enrichis les données avec tes connaissances oenologiques.\n\n"
    "INSTRUCTIONS SPÉCIALES :\n"
    "- Si le vin existe déjà dans la base, dis-le clairement dans chat_response\n"
    "- Si c'est un nouveau vin, explique pourquoi il mérite d'être ajouté\n"
    "- Enrichis les informations avec tes connaissances (cépages, région, style)\n"
    "- Sois précis sur les millésimes et appellations\n"
    "- Détecte le type de vin (Rouge/Blanc/Rosé/Mousseux/Nature/Doux)\n\n"
    "Format de réponse JSON :\n"
    "{\n"
    '  "chat_response": "Message détaillé expliquant si le vin existe déjà ou non, et pourquoi",\n'
    '  "wine_data": {\n'
    '    "name": "Nom complet exact du vin (appellation + nom si applicable)",\n'
    '    "winery": "Nom du domaine/producteur exact",\n'
    '    "year": 2020,\n'
    '    "region": "Région viticole précise (ex: Pauillac, Sauternes, Chassagne-Montrachet)",\n'
    '    "country": "Pays",\n'
    '    "variety": "Cépage(s) principaux (ex: Cabernet Sauvignon, Chardonnay, Syrah)",\n'
    '    "type": "Rouge/Blanc/Rosé/Mousseux/Nature/Doux",\n'
    '    "alcohol_percentage": 13.5,\n'
    '    "description": "Description détaillée incluant le style, les arômes, le potentiel de garde",\n'
    '    "designation": "Dénomination spécifique (Premier Cru, Grand Cru, etc)",\n'
    '    "sub_region": "Sous-région si applicable (ex: Médoc, Côte de Nuits)",\n'
    '    "confidence": 0.95\n'
    "  }\n"
    "}\n\n"
    'En cas d\'étiquette illisible, retourne :\n'
    '{"error": "label_unreadable", "detail": "message expliquant pourquoi"}'
)


def _get_client() -> OpenAI:
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        raise RuntimeError("GITHUB_TOKEN manquant dans .env")
    return OpenAI(
        base_url="https://models.inference.ai.azure.com",
        api_key=github_token,
    )


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
