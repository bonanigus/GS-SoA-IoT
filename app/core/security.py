"""
Security — JWT Auth + Password Hashing
========================================
Autenticação via Bearer Token (JWT).
Sem dependências externas além de python-jose e passlib.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.orm import UserORM

# ── Configurações ──────────────────────────────
SECRET_KEY  = "cloud-identifier-gs-2025-secret-key-change-in-prod"
ALGORITHM   = "HS256"
TOKEN_EXPIRE_MINUTES = 60 * 8   # 8 horas

pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
bearer_scheme = HTTPBearer()


# ── Hashing ────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT ────────────────────────────────────────

def create_access_token(data: dict,
                         expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ── Dependency: current user ───────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> UserORM:
    payload = decode_token(credentials.credentials)
    username: Optional[str] = payload.get("sub")
    if username is None:
        raise HTTPException(status_code=401, detail="Token sem subject")

    user = db.query(UserORM).filter(UserORM.username == username).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Usuário não encontrado ou inativo")
    return user


def get_admin_user(current_user: UserORM = Depends(get_current_user)) -> UserORM:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")
    return current_user


# ── Seed: cria admin padrão se não existir ─────

def ensure_default_admin(db: Session) -> None:
    existing = db.query(UserORM).filter(UserORM.username == "admin").first()
    if not existing:
        admin = UserORM(
            id=str(uuid.uuid4()),
            username="admin",
            email="admin@cloudidentifier.gs",
            hashed_password=hash_password("admin123"),
            is_active=True,
            is_admin=True,
        )
        db.add(admin)
        db.commit()
