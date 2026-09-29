import uuid
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import Professor, School, User
from app.db.session import get_current_user, get_db

DB = Annotated[Session, Depends(get_db)]


def current_user(db: DB) -> User:
    return get_current_user(db)


CurrentUser = Annotated[User, Depends(current_user)]


def get_professor(db: Session, user: User, professor_id: uuid.UUID) -> Professor:
    prof = db.get(Professor, professor_id)
    if prof is None or db.get(School, prof.school_id).user_id != user.id:
        raise HTTPException(404, "Professor not found")
    return prof
