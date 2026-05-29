"""Dépendance d'authentification — vérification du JWT Supabase.

L'app Flutter conserve l'authentification côté client (login/signup/session via
le SDK Supabase) et transmet son access token dans l'en-tête
`Authorization: Bearer <token>`. On vérifie ici la signature HS256 avec le
JWT Secret du projet, et on en extrait l'`user_id` (claim `sub`).

Règle de sécurité non négociable : l'`user_id` provient TOUJOURS du JWT,
jamais du body ni de la query.
"""
import logging
import os
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

# auto_error=False : on gère nous-mêmes l'absence de header pour renvoyer un 401 propre.
_bearer = HTTPBearer(auto_error=False)


async def get_current_user_id(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UUID:
    """Vérifie le JWT Supabase et retourne l'UUID de l'utilisateur (claim `sub`).

    Raises:
        HTTPException(401): token absent, invalide, expiré, ou config manquante.
    """
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=401, detail="Token d'authentification manquant")

    jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
    if not jwt_secret:
        logger.error("SUPABASE_JWT_SECRET manquant dans l'environnement")
        raise HTTPException(status_code=401, detail="Configuration d'authentification indisponible")

    try:
        payload = jwt.decode(
            creds.credentials,
            jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expiré")
    except jwt.InvalidTokenError as e:
        logger.warning("JWT invalide: %s", e)
        raise HTTPException(status_code=401, detail="Token invalide")

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token sans identifiant utilisateur")

    try:
        return UUID(sub)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Identifiant utilisateur invalide dans le token")
