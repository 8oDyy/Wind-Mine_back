from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID


class WineAddRequest(BaseModel):
    user_id: UUID = Field(..., description="ID de l'utilisateur")
    wine_id: Optional[UUID] = Field(None, description="ID du vin existant (si existant)")
    wine_data: Optional[dict] = Field(None, description="Données du nouveau vin (si nouveau)")
    stock: int = Field(1, ge=0, description="Quantité à ajouter")
    custom_notes: Optional[str] = Field(None, description="Notes personnelles")
    location: Optional[str] = Field(None, description="Emplacement dans la cave")


class WineAddResponse(BaseModel):
    success: bool
    message: str
    wine_added: bool  # True si nouveau vin créé
    cellar_wine: Optional[dict]
    wine_info: Optional[dict]


class WineAddError(BaseModel):
    error: str
    detail: str
