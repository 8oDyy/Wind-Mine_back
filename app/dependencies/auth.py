"""Dépendance d'authentification — vérification du JWT Supabase.

L'app Flutter conserve l'authentification côté client (login/signup/session via
le SDK Supabase) et transmet son access token dans l'en-tête
`Authorization: Bearer <token>`. On vérifie ici la signature et on en extrait
l'`user_id` (claim `sub`).

Le projet a migré vers les **JWT Signing Keys asymétriques** (ES256) : les
access tokens actuels sont signés en ES256 et vérifiés via le JWKS public
(`/auth/v1/.well-known/jwks.json`). Le **legacy JWT secret** (HS256) reste
accepté en repli pour les tokens encore signés symétriquement.

Règle de sécurité non négociable : l'`user_id` provient TOUJOURS du JWT,
jamais du body ni de la query.
"""
import logging
import os
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

logger = logging.getLogger(__name__)

# auto_error=False : on gère nous-mêmes l'absence de header pour renvoyer un 401 propre.
_bearer = HTTPBearer(auto_error=False)

# Client JWKS initialisé paresseusement (pas d'appel réseau à l'import).
_jwk_client: PyJWKClient | None = None


def _get_jwk_client() -> PyJWKClient | None:
    """Retourne un PyJWKClient (avec cache) pointant sur le JWKS Supabase, ou None."""
    global _jwk_client
    if _jwk_client is not None:
        return _jwk_client
    supabase_url = os.getenv("SUPABASE_URL")
    if not supabase_url:
        return None
    jwks_url = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    _jwk_client = PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)
    return _jwk_client


def _decode_token(token: str) -> dict:
    """Vérifie et décode un access token Supabase (ES256 via JWKS, ou HS256 legacy).

    Raises:
        jwt.InvalidTokenError (et sous-classes) si le token est invalide/expiré.
        HTTPException(401) si aucune méthode de vérification n'est configurée.
    """
    alg = jwt.get_unverified_header(token).get("alg", "")
    options = {"audience": "authenticated"}

    # Tokens asymétriques (clés de signature modernes) : vérification via JWKS.
    if alg.startswith(("ES", "RS", "PS", "EdDSA")):
        client = _get_jwk_client()
        if client is None:
            logger.error("SUPABASE_URL manquant : impossible de récupérer le JWKS")
            raise HTTPException(status_code=401, detail="Configuration d'authentification indisponible")
        signing_key = client.get_signing_key_from_jwt(token)
        return jwt.decode(token, signing_key.key, algorithms=[alg], **options)

    # Repli legacy HS256 (ancien JWT secret symétrique).
    jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
    if not jwt_secret:
        logger.error("SUPABASE_JWT_SECRET manquant pour vérifier un token HS256")
        raise HTTPException(status_code=401, detail="Configuration d'authentification indisponible")
    return jwt.decode(token, jwt_secret, algorithms=["HS256"], **options)


async def get_current_user_id(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UUID:
    """Vérifie le JWT Supabase et retourne l'UUID de l'utilisateur (claim `sub`).

    Raises:
        HTTPException(401): token absent, invalide, expiré, ou config manquante.
    """
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=401, detail="Token d'authentification manquant")

    try:
        payload = _decode_token(creds.credentials)
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expiré")
    except jwt.InvalidTokenError as e:
        logger.warning("JWT invalide: %s", e)
        raise HTTPException(status_code=401, detail="Token invalide")
    except Exception as e:  # ex. échec de récupération du JWKS
        logger.warning("Échec de vérification du JWT: %s", e)
        raise HTTPException(status_code=401, detail="Token invalide")

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token sans identifiant utilisateur")

    try:
        return UUID(sub)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Identifiant utilisateur invalide dans le token")
