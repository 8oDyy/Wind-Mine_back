from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID


class WineLabelRequest(BaseModel):
    file_path: str = Field(..., min_length=1, description="Chemin de l'image de l'étiquette dans le bucket Supabase")
    user_id: UUID = Field(..., description="ID de l'utilisateur qui ajoute la bouteille")
    custom_notes: Optional[str] = Field(None, description="Notes personnelles sur la bouteille")
    stock: int = Field(1, ge=0, description="Quantité à ajouter dans la cave")
    location: Optional[str] = Field(None, description="Emplacement dans la cave")


class WineAnalysis(BaseModel):
    name: str
    winery: Optional[str]
    year: Optional[int]
    region: Optional[str]
    country: Optional[str]
    variety: Optional[str]
    type: Optional[str]
    alcohol_percentage: Optional[float]
    description: Optional[str]
    confidence: float = Field(..., ge=0.0, le=1.0)


class WineInfo(BaseModel):
    id: UUID
    name: str
    winery: Optional[str]
    year: Optional[int]
    region: Optional[str]
    country: Optional[str]
    variety: Optional[str]
    type: Optional[str]
    description: Optional[str]


class CellarWine(BaseModel):
    id: UUID
    wine_id: UUID
    user_id: UUID
    stock: int
    rating: Optional[float]
    notes: Optional[str]
    location: Optional[str]
    created_at: str
    wine_info: WineInfo


class WineLabelResponse(BaseModel):
    chat_response: str
    wine_added: bool
    cellar_wine: Optional[CellarWine]
    wine_analysis: WineAnalysis


class WineLabelError(BaseModel):
    error: str
    detail: str
