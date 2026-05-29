"""Schémas Pydantic pour le profil utilisateur.

La réponse n'est pas modélisée strictement : le router renvoie le row `profiles`
de Supabase (clés identiques à `UserModel.fromJson` côté Flutter).
"""
from typing import Optional

from pydantic import BaseModel, Field


class ProfileUpdateRequest(BaseModel):
    """Tous les champs sont optionnels ; seuls les champs non-null sont appliqués."""
    niveau: Optional[str] = Field(None, description="Niveau de connaissance en vin")
    preference: Optional[str] = Field(None, description="Préférences de l'utilisateur")
    objectif: Optional[str] = Field(None, description="Objectif de l'utilisateur")


class ProfileError(BaseModel):
    error: str
    detail: str
