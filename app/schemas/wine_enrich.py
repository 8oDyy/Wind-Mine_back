from pydantic import BaseModel


class WineEnrichResponse(BaseModel):
    """Réponse de l'endpoint d'enrichissement.

    `wine` est la row `wines` brute (mêmes clés que le catalogue), pour rester iso
    avec le parser Flutter. `enriched` indique si un appel LLM a réellement eu lieu
    (False = le vin était déjà enrichi, renvoyé tel quel).
    """
    enriched: bool
    wine: dict


class WineEnrichError(BaseModel):
    error: str
    detail: str
