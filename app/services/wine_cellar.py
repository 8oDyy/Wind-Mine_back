import logging
import os
from typing import Optional, Tuple
from uuid import UUID

from supabase import create_client, Client

logger = logging.getLogger(__name__)


def _get_client() -> Client:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_service_role_key:
        raise RuntimeError("SUPABASE_URL ou SUPABASE_SERVICE_ROLE_KEY manquant dans .env")
    return create_client(supabase_url, supabase_service_role_key)


def find_similar_wine(wine_data: dict) -> tuple[Optional[dict], str]:
    """Cherche un vin existant avec recherche de similarité intelligente.
    
    Args:
        wine_data: Données du vin extraites de l'étiquette
        
    Returns:
        Tuple (vin_similaire_ou_None, type_correspondance)
    """
    client = _get_client()
    
    name = wine_data.get("name", "").strip()
    winery = wine_data.get("winery", "").strip()
    year = wine_data.get("year")
    region = wine_data.get("region", "").strip()
    
    try:
        # Recherche 1: Exacte sur nom + domaine + millésime
        if name and winery and year:
            query = (
                client.table("wines")
                .select("*")
                .eq("name", name)
                .eq("winery", winery)
                .eq("year", year)
                .limit(1)
            )
            response = query.execute()
            if response.data:
                logger.info(f"Vin exact trouvé: {name} - {winery} {year}")
                return response.data[0], "exact"
        
        # Recherche 2: Nom + domaine (différentes années)
        if name and winery:
            query = (
                client.table("wines")
                .select("*")
                .eq("name", name)
                .eq("winery", winery)
                .limit(5)
            )
            response = query.execute()
            if response.data:
                # Chercher l'année la plus proche
                if year:
                    closest = min(response.data, key=lambda w: abs(w.get("year", 0) - year))
                    logger.info(f"Vin similaire trouvé (même nom+domaine, année proche): {name} - {winery} {closest.get('year')}")
                    return closest, "same_wine_different_year"
                # Sinon prendre le plus récent
                newest = max(response.data, key=lambda w: w.get("year", 0))
                logger.info(f"Vin similaire trouvé (même nom+domaine): {name} - {winery}")
                return newest, "same_wine_different_year"
        
        # Recherche 3: Nom similaire + même domaine
        if name and winery:
            # Chercher des noms similaires (contient les mots clés)
            name_parts = name.lower().split()
            for part in name_parts:
                if len(part) > 3:  # Ignorer les petits mots
                    query = (
                        client.table("wines")
                        .select("*")
                        .ilike("name", f"%{part}%")
                        .eq("winery", winery)
                        .limit(3)
                    )
                    response = query.execute()
                    if response.data:
                        logger.info(f"Vin similaire trouvé (nom partiel + même domaine): {part} - {winery}")
                        return response.data[0], "similar_name_same_winery"
        
        # Recherche 4: Même domaine + même région
        if winery and region:
            query = (
                client.table("wines")
                .select("*")
                .eq("winery", winery)
                .eq("region", region)
                .limit(3)
            )
            response = query.execute()
            if response.data:
                logger.info(f"Vin similaire trouvé (même domaine + région): {winery} - {region}")
                return response.data[0], "same_winery_region"
        
        # Recherche 5: Même région + type de vin similaire
        if region and name:
            wine_type = wine_data.get("type", "")
            query = (
                client.table("wines")
                .select("*")
                .ilike("name", f"%{name.split()[0]}%")
                .eq("region", region)
                .limit(5)
            )
            response = query.execute()
            if response.data:
                logger.info(f"Vin similaire trouvé (région + nom similaire): {region}")
                return response.data[0], "same_region_similar_name"
        
        logger.info(f"Aucun vin similaire trouvé pour: {name} - {winery} {year}")
        return None, "no_match"
        
    except Exception as e:
        logger.error("Erreur recherche vin similaire: %s", e)
        raise RuntimeError("Erreur lors de la recherche du vin") from e


def create_wine(wine_data: dict) -> dict:
    """Crée un nouveau vin dans la table wines avec données enrichies.
    
    Args:
        wine_data: Données du vin extraites et enrichies
        
    Returns:
        Vin créé
    """
    client = _get_client()
    
    wine_insert = {
        "name": wine_data.get("name", "Vin inconnu"),
        "winery": wine_data.get("winery"),
        "year": wine_data.get("year"),
        "region": wine_data.get("region"),
        "country": wine_data.get("country"),
        "variety": wine_data.get("variety"),
        "type": wine_data.get("type", "Rouge"),
        "description": wine_data.get("description"),
        "designation": wine_data.get("designation"),
        "province": wine_data.get("sub_region"),  # Utiliser sub_region comme province
        "image_url": None  # Sera mis à jour plus tard si besoin
    }
    
    try:
        response = client.table("wines").insert(wine_insert).execute()
        logger.info(f"Nouveau vin créé: {wine_insert['name']} ({wine_insert.get('year', 'N/A')})")
        return response.data[0]
    except Exception as e:
        logger.error("Erreur création vin: %s", e)
        raise RuntimeError("Erreur lors de la création du vin") from e


def add_to_user_cellar(user_id: UUID, wine_id: UUID, stock: int = 1, 
                      notes: Optional[str] = None, location: Optional[str] = None) -> dict:
    """Ajoute un vin à la cave de l'utilisateur.
    
    Args:
        user_id: ID de l'utilisateur
        wine_id: ID du vin
        stock: Quantité
        notes: Notes personnelles
        location: Emplacement
        
    Returns:
        Entrée dans user_cellar
    """
    client = _get_client()
    
    cellar_entry = {
        "user_id": str(user_id),
        "wine_id": str(wine_id),
        "stock": stock,
        "notes": notes,
        "location": location
    }
    
    try:
        response = client.table("user_cellar").insert(cellar_entry).execute()
        return response.data[0]
    except Exception as e:
        logger.error("Erreur ajout cave utilisateur: %s", e)
        raise RuntimeError("Erreur lors de l'ajout à la cave") from e


def get_wine_with_cellar_info(cellar_entry: dict) -> Tuple[dict, dict]:
    """Récupère les infos complètes du vin + entrée cave.
    
    Args:
        cellar_entry: Entrée de user_cellar
        
    Returns:
        Tuple (vin, cellar_entry_with_wine_info)
    """
    client = _get_client()
    
    try:
        # Récupérer les infos du vin
        wine_response = client.table("wines").select("*").eq("id", cellar_entry["wine_id"]).execute()
        wine = wine_response.data[0] if wine_response.data else None
        
        if not wine:
            raise ValueError(f"Vin {cellar_entry['wine_id']} non trouvé")
        
        return wine, cellar_entry
        
    except Exception as e:
        logger.error("Erreur récupération infos vin: %s", e)
        raise RuntimeError("Erreur lors de la récupération des informations du vin") from e
