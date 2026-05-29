import json
import logging
import os

from openai import OpenAI

logger = logging.getLogger(__name__)

WINE_PAIRING_SYSTEM_PROMPT = (
    "Tu es Paul, un sommelier virtuel expert et chaleureux dans l'application WineMind. "
    "Analyse l'image du plat et, si disponible, la note utilisateur. "
    "Déduis le type de plat probable, les ingrédients visibles, le profil gustatif global, "
    "puis propose au maximum 3 styles de vins adaptés. "
    "Réponds de façon conversationnelle et naturelle, comme si tu parlais directement à l'utilisateur. "
    "Sois concis, amical, et utilise un vocabulaire accessible. "
    "Ne propose jamais de bouteille ou de marque précise. "
    "Si l'image est trop floue ou inexploitable, réponds poliment que tu ne peux pas l'analyser.\n\n"
    "Format de réponse JSON :\n"
    "{\n"
    '  "chat_response": "Ta réponse conversationnelle complète ici",\n'
    '  "structured_data": {\n'
    '    "dish_name": "string",\n'
    '    "ingredients_detected": ["string"],\n'
    '    "flavor_profile": {\n'
    '      "richness": 1-5,\n'
    '      "acidity": 1-5,\n'
    '      "sweetness": 1-5,\n'
    '      "spice": 1-5\n'
    '    },\n'
    '    "wine_pairings": [\n'
    '      {\n'
    '        "style": "string",\n'
    '        "color": "string",\n'
    '        "reason": "string"\n'
    '      }\n'
    '    ],\n'
    '    "confidence": 0.0-1.0\n'
    '  }\n'
    "}\n\n"
    'En cas d\'image inexploitable, retourne :\n'
    '{"error": "image_unusable", "detail": "message conversationnel expliquant le problème"}'
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


def analyze_dish_image(image_url: str, user_note: str | None = None) -> dict:
    """Envoie l'image au modèle vision et retourne la réponse JSON parsée.

    Args:
        image_url: URL signée de l'image.
        user_note: Note optionnelle de l'utilisateur.

    Returns:
        Dictionnaire JSON de la réponse du modèle.

    Raises:
        RuntimeError: Si l'appel au modèle échoue.
        ValueError: Si la réponse n'est pas du JSON valide.
    """
    client = _get_client()

    user_content: list[dict] = [
        {
            "type": "image_url",
            "image_url": {"url": image_url},
        },
    ]

    if user_note:
        user_content.append({
            "type": "text",
            "text": f"Note de l'utilisateur : {user_note}",
        })

    messages = [
        {"role": "system", "content": WINE_PAIRING_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    vision_model = os.getenv("VISION_MODEL", "gpt-4o")
    try:
        response = client.chat.completions.create(
            model=vision_model,
            messages=messages,
            temperature=0.4,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        logger.error("Erreur GitHub Models (vision): %s", e)
        raise RuntimeError("Échec de l'appel au modèle de vision") from e

    raw_content = response.choices[0].message.content
    if not raw_content:
        raise ValueError("Le modèle a retourné une réponse vide")

    try:
        return json.loads(raw_content)
    except json.JSONDecodeError as e:
        logger.error("Réponse non-JSON du modèle: %s", raw_content[:500])
        raise ValueError("Le modèle n'a pas retourné du JSON valide") from e
