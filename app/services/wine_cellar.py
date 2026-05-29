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
        # Recherche 1: Nom exact (priorité absolue, ignore l'année)
        if name:
            query = (
                client.table("wines")
                .select("*")
                .eq("name", name)
                .limit(10)
            )
            response = query.execute()
            if response.data:
                # Si winery spécifié, chercher la meilleure correspondance
                if winery:
                    for wine in response.data:
                        if wine.get("winery", "").lower() == winery.lower():
                            logger.info(f"Vin exact trouvé: {name} - {winery}")
                            return wine, "exact"
                    # Sinon prendre le premier avec le même nom
                    logger.info(f"Vin trouvé par nom exact: {name}")
                    return response.data[0], "exact"
                else:
                    logger.info(f"Vin trouvé par nom exact: {name}")
                    return response.data[0], "exact"
        
        # Recherche 2: Nom similaire (contient les mots clés)
        if name:
            name_parts = name.lower().split()
            for part in name_parts:
                if len(part) > 3:  # Ignorer les petits mots
                    query = (
                        client.table("wines")
                        .select("*")
                        .ilike("name", f"%{part}%")
                        .limit(5)
                    )
                    response = query.execute()
                    if response.data:
                        # Si winery spécifié, chercher la meilleure correspondance
                        if winery:
                            for wine in response.data:
                                if wine.get("winery", "").lower() == winery.lower():
                                    logger.info(f"Vin similaire trouvé: {wine['name']} - {winery}")
                                    return wine, "similar_name_same_winery"
                        # Sinon prendre le premier
                        logger.info(f"Vin similaire trouvé: {response.data[0]['name']}")
                        return response.data[0], "similar_name"
        
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
        "alcohol_percentage": wine_data.get("alcohol_percentage"),
        "description": wine_data.get("description"),
        "designation": wine_data.get("designation"),
        "province": wine_data.get("province"),
        "price": wine_data.get("price"),
        "points": wine_data.get("points"),
        "body_level": wine_data.get("body_level", 0.5),
        "tannin_level": wine_data.get("tannin_level", 0.5),
        "fruit_level": wine_data.get("fruit_level", 0.5),
        "food_pairings": wine_data.get("food_pairings"),
        "image_url": None  # Sera mis à jour plus tard si besoin
    }
    
    try:
        response = client.table("wines").insert(wine_insert).execute()
        logger.info(f"Nouveau vin créé: {wine_insert['name']} ({wine_insert.get('year', 'N/A')})")
        return response.data[0]
    except Exception as e:
        logger.error("Erreur création vin: %s", e)
        raise RuntimeError("Erreur lors de la création du vin") from e


# Colonnes "custom_*" et métadonnées libres acceptées à l'insertion d'une entrée de cave.
_CELLAR_OPTIONAL_FIELDS = (
    "rating", "apogee", "notes", "location", "purchase_date", "purchase_price",
    "custom_name", "custom_year", "custom_type", "custom_region", "custom_points",
    "custom_description", "custom_price", "custom_variety", "custom_winery",
)


def add_to_user_cellar(
    user_id: UUID,
    wine_id: Optional[UUID] = None,
    stock: int = 1,
    notes: Optional[str] = None,
    location: Optional[str] = None,
    extra: Optional[dict] = None,
) -> dict:
    """Ajoute un vin à la cave de l'utilisateur.

    Supporte un vin du catalogue (`wine_id` fourni) OU un vin "custom"
    (`wine_id=None`, infos portées par les champs `custom_*` passés dans `extra`).

    Args:
        user_id: ID de l'utilisateur (provient toujours du JWT côté router).
        wine_id: ID du vin catalogue, ou None pour un vin custom.
        stock: Quantité.
        notes: Notes personnelles (raccourci ; peut aussi venir d'`extra`).
        location: Emplacement (raccourci ; peut aussi venir d'`extra`).
        extra: Champs optionnels supplémentaires (rating, apogee, purchase_*, custom_*).

    Returns:
        Entrée brute insérée dans user_cellar (sans jointure wines).
    """
    client = _get_client()

    cellar_entry: dict = {
        "user_id": str(user_id),
        "wine_id": str(wine_id) if wine_id else None,
        "stock": stock,
    }
    if notes is not None:
        cellar_entry["notes"] = notes
    if location is not None:
        cellar_entry["location"] = location

    if extra:
        for field in _CELLAR_OPTIONAL_FIELDS:
            if field in extra and extra[field] is not None:
                cellar_entry[field] = extra[field]

    try:
        response = client.table("user_cellar").insert(cellar_entry).execute()
        return response.data[0]
    except Exception as e:
        logger.error("Erreur ajout cave utilisateur: %s", e)
        raise RuntimeError("Erreur lors de l'ajout à la cave") from e


def list_user_cellar(user_id: UUID) -> list[dict]:
    """Liste la cave d'un utilisateur, vin catalogue imbriqué (`wines`).

    Returns:
        Liste de rows `user_cellar` (avec clé `wines` = objet ou None),
        triées par date d'ajout décroissante. Liste vide si cave vide.
    """
    client = _get_client()
    try:
        response = (
            client.table("user_cellar")
            .select("*, wines(*)")
            .eq("user_id", str(user_id))
            .order("created_at", desc=True)
            .execute()
        )
        return response.data or []
    except Exception as e:
        logger.error("Erreur lecture cave utilisateur: %s", e)
        raise RuntimeError("Erreur lors de la lecture de la cave") from e


def get_last_cellar_wine(user_id: UUID) -> Optional[dict]:
    """Retourne la dernière entrée de cave ajoutée, ou None si la cave est vide."""
    client = _get_client()
    try:
        response = (
            client.table("user_cellar")
            .select("*, wines(*)")
            .eq("user_id", str(user_id))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error("Erreur lecture dernier vin de cave: %s", e)
        raise RuntimeError("Erreur lors de la lecture de la cave") from e


def get_cellar_entry(user_id: UUID, cellar_id: UUID) -> Optional[dict]:
    """Retourne une entrée de cave (vin imbriqué) si elle appartient à l'utilisateur."""
    client = _get_client()
    try:
        response = (
            client.table("user_cellar")
            .select("*, wines(*)")
            .eq("id", str(cellar_id))
            .eq("user_id", str(user_id))
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error("Erreur lecture entrée de cave: %s", e)
        raise RuntimeError("Erreur lors de la lecture de l'entrée de cave") from e


def delete_cellar_entry(user_id: UUID, cellar_id: UUID) -> bool:
    """Supprime une entrée de cave possédée par l'utilisateur.

    Returns:
        True si une ligne a été supprimée, False sinon (inexistante / autre user).
    """
    client = _get_client()
    try:
        response = (
            client.table("user_cellar")
            .delete()
            .eq("id", str(cellar_id))
            .eq("user_id", str(user_id))
            .execute()
        )
        return bool(response.data)
    except Exception as e:
        logger.error("Erreur suppression entrée de cave: %s", e)
        raise RuntimeError("Erreur lors de la suppression de l'entrée de cave") from e


def update_cellar_stock(user_id: UUID, cellar_id: UUID, stock: int) -> Optional[dict]:
    """Met à jour le stock d'une entrée possédée par l'utilisateur.

    Returns:
        L'entrée mise à jour (vin imbriqué), ou None si non possédée / inexistante.
    """
    client = _get_client()
    try:
        response = (
            client.table("user_cellar")
            .update({"stock": stock})
            .eq("id", str(cellar_id))
            .eq("user_id", str(user_id))
            .execute()
        )
        if not response.data:
            return None
        # Re-SELECT pour renvoyer la forme complète avec wines(*) imbriqué.
        return get_cellar_entry(user_id, cellar_id)
    except Exception as e:
        logger.error("Erreur mise à jour stock de cave: %s", e)
        raise RuntimeError("Erreur lors de la mise à jour du stock") from e


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
