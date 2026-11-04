"""Publishing targets: ranked conferences and journals for the user's paper."""

import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.api.schemas import ORM, TaskLink
from app.db.models import Venue

router = APIRouter(tags=["venues"])

Kind = Literal["conference", "journal", "workshop"]
Status = Literal["considering", "target", "submitted", "accepted", "rejected", "dropped"]


class VenueIn(BaseModel):
    name: str
    rank: int = 0
    kind: Kind = "conference"
    tier: str | None = None
    deadline: date | None = None
    deadline_text: str | None = None
    why: str | None = None
    notes: str | None = None
    links: list[TaskLink] = []
    status: Status = "considering"


class VenuePatch(BaseModel):
    name: str | None = None
    rank: int | None = None
    kind: Kind | None = None
    tier: str | None = None
    deadline: date | None = None
    deadline_text: str | None = None
    why: str | None = None
    notes: str | None = None
    links: list[TaskLink] | None = None
    status: Status | None = None


class VenueOut(ORM):
    id: uuid.UUID
    name: str
    rank: int
    kind: str
    tier: str | None
    deadline: date | None
    deadline_text: str | None
    why: str | None
    notes: str | None
    links: list[TaskLink]
    status: str
    updated_at: datetime


def _get(db, user, venue_id: uuid.UUID) -> Venue:
    venue = db.get(Venue, venue_id)
    if venue is None or venue.user_id != user.id:
        raise HTTPException(404, "Venue not found")
    return venue


@router.get("/venues", response_model=list[VenueOut])
def list_venues(db: DB, user: CurrentUser):
    return db.scalars(select(Venue).where(Venue.user_id == user.id).order_by(Venue.rank, Venue.name)).all()


@router.post("/venues", response_model=VenueOut)
def create_venue(body: VenueIn, db: DB, user: CurrentUser):
    venue = Venue(user_id=user.id, **body.model_dump())
    db.add(venue)
    db.commit()
    return venue


@router.patch("/venues/{venue_id}", response_model=VenueOut)
def patch_venue(venue_id: uuid.UUID, body: VenuePatch, db: DB, user: CurrentUser):
    venue = _get(db, user, venue_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(venue, k, v)
    db.commit()
    return venue


@router.delete("/venues/{venue_id}", status_code=204)
def delete_venue(venue_id: uuid.UUID, db: DB, user: CurrentUser):
    db.delete(_get(db, user, venue_id))
    db.commit()
