"""
Database — SQLAlchemy + SQLite
================================
Configuração da conexão, engine e sessão.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from app.models.orm import Base

DATABASE_URL = "sqlite:///./cloud_identifier.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # necessário para SQLite
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables() -> None:
    """Cria todas as tabelas se não existirem."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency Injection para FastAPI.
    Garante que a sessão seja fechada após cada request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
