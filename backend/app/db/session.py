from collections.abc import Iterator

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import User

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

DEFAULT_USER_EMAIL = "me@phddog.local"


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db


def get_current_user(db: Session) -> User:
    """Single local user for the MVP; created on first use."""
    user = db.scalar(select(User).where(User.email == DEFAULT_USER_EMAIL))
    if user is None:
        user = User(email=DEFAULT_USER_EMAIL, name="Me")
        db.add(user)
        db.commit()
    return user
