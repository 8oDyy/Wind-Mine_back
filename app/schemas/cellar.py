"""Schémas Pydantic pour les endpoints de cave.

Les réponses de lecture ne sont volontairement PAS modélisées : les routers
renvoient directement les rows `user_cellar` de Supabase (avec l'objet `wines`
imbriqué), pour garantir une forme JSON strictement identique à celle que le
parser Flutter `WineModel.fromCellarJson` consomme aujourd'hui.
"""
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CellarAddRequest(BaseModel):
    """Ajout d'un vin à la cave : vin catalogue (`wine_id`) OU vin custom (`custom_*`)."""
    wine_id: Optional[UUID] = Field(None, description="ID du vin catalogue ; absent/null => vin custom")
    stock: int = Field(..., ge=0, description="Quantité en cave")
    rating: Optional[float] = Field(None, description="Note personnelle")
    apogee: Optional[str] = Field(None, description="Apogée de garde")
    notes: Optional[str] = None
    location: Optional[str] = Field(None, description="Emplacement dans la cave")
    purchase_date: Optional[str] = Field(None, description="Date d'achat (ISO 8601, ex. 2026-05-29)")
    purchase_price: Optional[float] = None
    # Champs custom_* : pertinents uniquement si wine_id est absent.
    custom_name: Optional[str] = None
    custom_year: Optional[str] = None
    custom_type: Optional[str] = None
    custom_region: Optional[str] = None
    custom_points: Optional[int] = None
    custom_description: Optional[str] = None
    custom_price: Optional[float] = None
    custom_variety: Optional[str] = None
    custom_winery: Optional[str] = None


class CellarStockUpdateRequest(BaseModel):
    stock: int = Field(..., ge=0, description="Nouveau stock")


class CellarError(BaseModel):
    error: str
    detail: str
