from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.llm import LLMProvider, build_provider
from app.models import User
from app.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise unauthorized
    user = await session.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


_provider: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    """Built once from env vars. Tests override this dependency with a fake."""
    global _provider
    if _provider is None:
        _provider = build_provider(get_settings())
    return _provider
