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


def find_existing_wine(wine_data: dict) -> Optional[dict]:
    """Cherche si un vin existe déjà dans la base wines (optimisé).
    
    Args:
        wine_data: Données du vin extraites de l'étiquette
        
    Returns:
        Vin existant ou None
    """
    client = _get_client()
    
    # Stratégie de recherche optimisée :
    # 1. Recherche exacte sur nom + domaine + millésime (très rapide)
    # 2. Si rien trouvé, recherche plus large
    # 3. Limiter les résultats pour éviter les timeouts
    
    name = wine_data.get("name", "").strip()
    winery = wine_data.get("winery", "").strip()
    year = wine_data.get("year")
    
    try:
        # Recherche 1: Exacte sur les critères les plus discriminants (utilise idx_wines_name_winery_year)
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
                logger.info(f"Vin trouvé par recherche exacte: {name} - {winery} {year}")
                return response.data[0]
        
        # Recherche 2: Nom + domaine (utilise idx_wines_name_winery)
        if name and winery:
            query = (
                client.table("wines")
                .select("*")
                .eq("name", name)
                .eq("winery", winery)
                .limit(3)
            )
            response = query.execute()
            if response.data:
                # Filtrer par année si disponible
                if year:
                    for wine in response.data:
                        if wine.get("year") == year:
                            logger.info(f"Vin trouvé par nom+domaine+année: {name} - {winery}")
                            return wine
                # Sinon prendre le premier
                logger.info(f"Vin trouvé par nom+domaine: {name} - {winery}")
                return response.data[0]
        
        # Recherche 3: Nom seulement (plus large)
        if name:
            query = (
                client.table("wines")
                .select("*")
                .ilike("name", name)
                .limit(5)
            )
            response = query.execute()
            if response.data:
                logger.info(f"Vin trouvé par nom seulement: {name}")
                return response.data[0]
        
        # Recherche 4: Domaine seulement
        if winery:
            query = (
                client.table("wines")
                .select("*")
                .ilike("winery", winery)
                .limit(3)
            )
            response = query.execute()
            if response.data:
                logger.info(f"Vin trouvé par domaine seulement: {winery}")
                return response.data[0]
        
        logger.info(f"Aucun vin existant trouvé pour: {name} - {winery} {year}")
        return None
        
    except Exception as e:
        logger.error("Erreur recherche vin existant: %s", e)
        raise RuntimeError("Erreur lors de la recherche du vin") from e


def create_wine(wine_data: dict) -> dict:
    """Crée un nouveau vin dans la table wines.
    
    Args:
        wine_data: Données du vin
        
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
        "image_url": None  # Sera mis à jour plus tard si besoin
    }
    
    try:
        response = client.table("wines").insert(wine_insert).execute()
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
