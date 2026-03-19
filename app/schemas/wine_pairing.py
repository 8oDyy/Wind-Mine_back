from pydantic import BaseModel, Field


class WinePairingRequest(BaseModel):
    file_path: str = Field(
        ...,
        min_length=1,
        description="Chemin du fichier image dans le bucket Supabase",
    )
    user_note: str | None = Field(
        default=None,
        description="Commentaire optionnel de l'utilisateur",
    )


class FlavorProfile(BaseModel):
    richness: int = Field(..., ge=1, le=5)
    acidity: int = Field(..., ge=1, le=5)
    sweetness: int = Field(..., ge=1, le=5)
    spice: int = Field(..., ge=1, le=5)


class WineSuggestion(BaseModel):
    style: str
    color: str
    reason: str


class WinePairingData(BaseModel):
    dish_name: str
    ingredients_detected: list[str]
    flavor_profile: FlavorProfile
    wine_pairings: list[WineSuggestion] = Field(..., max_length=3)
    confidence: float = Field(..., ge=0.0, le=1.0)


class WinePairingResponse(BaseModel):
    chat_response: str
    structured_data: WinePairingData


class WinePairingError(BaseModel):
    error: str
    detail: str
