"""Verify Clerk session JWTs and authorize access to the shared workspace."""

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated
from urllib.parse import urlsplit

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError

bearer = HTTPBearer(auto_error=False)


def authorized_parties() -> list[str]:
    return [origin.strip() for origin in os.getenv(
        'CLERK_AUTHORIZED_PARTIES', 'http://localhost:5173,http://localhost:8000'
    ).split(',') if origin.strip()]


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    session_id: str


@lru_cache(maxsize=4)
def jwks_client(issuer: str) -> PyJWKClient:
    # The URL comes exclusively from server configuration, never JWT claims.
    return PyJWKClient(f'{issuer}/.well-known/jwks.json', timeout=5, lifespan=300)


def require_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> AuthenticatedUser:
    unauthorized = HTTPException(
        status_code=401, detail='Please sign in to continue.',
        headers={'WWW-Authenticate': 'Bearer'},
    )
    if credentials is None:
        raise unauthorized
    issuer = os.getenv('CLERK_ISSUER_URL', '').strip().rstrip('/')
    parsed = urlsplit(issuer)
    parties = authorized_parties()
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.path
            or parsed.query or parsed.fragment or parsed.username or not parties):
        raise HTTPException(status_code=503, detail='Sign-in is not configured.')
    try:
        signing_key = jwks_client(issuer).get_signing_key_from_jwt(credentials.credentials)
        claims = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=['RS256'],
            issuer=issuer,
            # Default Clerk session tokens have no audience. An unexpected aud
            # is rejected by PyJWT; custom JWT templates are not accepted here.
            options={'require': ['iss', 'sub', 'sid', 'exp', 'nbf', 'iat', 'azp']},
        )
        if (claims['azp'] not in parties or claims.get('sts') == 'pending'
                or not isinstance(claims['sub'], str) or not claims['sub'].startswith('user_')
                or not isinstance(claims['sid'], str) or not claims['sid'].startswith('sess_')):
            raise unauthorized
    except PyJWKClientConnectionError:
        raise HTTPException(status_code=503, detail='Sign-in is temporarily unavailable. Please try again.') from None
    except (jwt.PyJWTError, ValueError, TypeError):
        raise unauthorized from None
    return AuthenticatedUser(user_id=claims['sub'], session_id=claims['sid'])


def require_workspace_access(
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> AuthenticatedUser:
    mode = os.getenv('CLERK_ACCESS_MODE', 'approved_users')
    approved = {value.strip() for value in os.getenv('CLERK_ALLOWED_USER_IDS', '').split(',') if value.strip()}
    if mode == 'all_signed_in' or (mode == 'approved_users' and user.user_id in approved):
        return user
    if mode != 'approved_users':
        raise HTTPException(status_code=503, detail='Workspace access is not configured.')
    raise HTTPException(status_code=403, detail='Your account is awaiting workspace access. Contact your administrator.')
