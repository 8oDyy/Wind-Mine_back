from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID


class WineLabelRequest(BaseModel):
    file_path: str = Field(..., min_length=1, description="Chemin de l'image de l'étiquette dans le bucket Supabase")
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
    designation: Optional[str]
    province: Optional[str]
    price: Optional[float]
    points: Optional[int]
    body_level: Optional[float] = Field(None, ge=0.0, le=1.0)
    tannin_level: Optional[float] = Field(None, ge=0.0, le=1.0)
    fruit_level: Optional[float] = Field(None, ge=0.0, le=1.0)
    food_pairings: Optional[list[str]]
    drink_from: Optional[int] = Field(None, description="Début de la fenêtre de garde (année)")
    peak_year: Optional[int] = Field(None, description="Année d'apogée")
    drink_to: Optional[int] = Field(None, description="Fin de la fenêtre de garde (année)")
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


class WineProposal(BaseModel):
    id: Optional[UUID] = None  # None pour nouveau vin
    name: str
    winery: Optional[str]
    year: Optional[int]
    region: Optional[str]
    country: Optional[str]
    variety: Optional[str]
    type: Optional[str]
    alcohol_percentage: Optional[float] = None
    description: Optional[str] = None
    designation: Optional[str] = None
    province: Optional[str] = None
    price: Optional[float] = None
    points: Optional[int] = None
    body_level: Optional[float] = Field(None, ge=0.0, le=1.0)
    tannin_level: Optional[float] = Field(None, ge=0.0, le=1.0)
    fruit_level: Optional[float] = Field(None, ge=0.0, le=1.0)
    food_pairings: Optional[list[str]] = None
    drink_from: Optional[int] = None
    peak_year: Optional[int] = None
    drink_to: Optional[int] = None
    match_type: Optional[str] = None  # Pour vin existant
    match_confidence: float = 0.0    # Pour vin existant
    confidence: float = 0.0          # Pour nouveau vin


class WineLabelResponse(BaseModel):
    chat_response: str
    existing_proposal: Optional[WineProposal]
    new_proposal: WineProposal
    wine_analysis: WineAnalysis


class WineLabelError(BaseModel):
    error: str
    detail: str
