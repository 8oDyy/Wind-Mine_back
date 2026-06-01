"""Schémas Pydantic pour l'endpoint de recommandations (« Découvertes »).

La réponse est une liste de catégories (carrousels). Comme pour la cave, les
vins de chaque catégorie sont les **rows `wines` Supabase brutes** : on ne les
modélise donc PAS (champ `wines: list[dict]`), pour garantir une forme JSON
strictement iso avec le parser Flutter `WineModel.fromCellarJson` / la fiche
détail existante. Seule l'enveloppe (`categories[].key/title/subtitle`) est typée.
"""
from typing import Optional

from pydantic import BaseModel, Field


class RecommendationCategory(BaseModel):
    """Un carrousel : clé stable, libellés d'affichage, et la liste de vins bruts."""
    key: str = Field(..., description="Clé stable de la catégorie (ex. 'for_you', 'top_rated')")
    title: str = Field(..., description="Titre affiché du carrousel")
    subtitle: Optional[str] = Field(None, description="Sous-titre optionnel")
    # Rows `wines` brutes (mêmes clés que l'objet `wines` imbriqué côté cave).
    # Volontairement non modélisé pour ne rien renommer/filtrer.
    wines: list[dict] = Field(default_factory=list, description="Rows `wines` Supabase brutes")


class RecommendationsResponse(BaseModel):
    """Réponse de `GET /api/recommendations` : la liste ordonnée des carrousels."""
    categories: list[RecommendationCategory] = Field(default_factory=list)


class RecommendationsError(BaseModel):
    error: str
    detail: str
