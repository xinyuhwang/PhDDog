"""School identification: built-in catalog, then the user's saved schools, then OpenAlex."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Professor, School, User
from app.ingest.openalex import domain_from_url, resolve_school
from app.llm import get_llm
from app.schools_catalog import builtin_aliases
from app.services.jobs import enqueue

DOMAIN_RE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$")


def known_aliases(db: Session, user: User) -> dict[str, str]:
    aliases = builtin_aliases()
    for school in db.scalars(select(School).where(School.user_id == user.id, School.confirmed)):
        aliases[school.name.lower()] = school.name
        for a in school.aliases:
            aliases[a.lower()] = school.name
    return aliases


def normalize_domain(value: str | None) -> str | None:
    """'https://www.tamu.edu/' -> 'tamu.edu'. Raises ValueError for things that aren't domains."""
    if not value or not value.strip():
        return None
    domain = domain_from_url(value.strip())
    if not domain or not DOMAIN_RE.match(domain):
        raise ValueError(f"'{value}' doesn't look like a web domain (e.g. tamu.edu)")
    return domain


def _find(db: Session, user: User, name: str) -> School | None:
    return db.scalar(select(School).where(School.user_id == user.id, School.name == name))


def get_or_create_school(db: Session, user: User, school_raw: str) -> School:
    raw = school_raw.strip()
    canonical = known_aliases(db, user).get(raw.lower())
    if canonical and (school := _find(db, user, canonical)):
        return school
    if (school := _find(db, user, raw)) is not None:  # an unconfirmed school typed the same way
        return school

    info = get_llm().normalize_school(canonical or raw)
    if info.known:
        school = School(user_id=user.id, name=info.name, aliases=info.aliases, primary_domain=info.primary_domain,
                        confirmed=True)
    else:
        match, suggestions = resolve_school(raw)
        if match and (existing := _find(db, user, match.name)):
            _add_alias(existing, raw)
            return existing
        if match:
            school = School(user_id=user.id, name=match.name, aliases=_dedupe([*match.acronyms, raw], match.name),
                            primary_domain=match.domain, confirmed=True)
        else:
            school = School(user_id=user.id, name=raw, aliases=[], primary_domain=None, confirmed=False,
                            suggestions=[s.as_suggestion() for s in suggestions])
    db.add(school)
    db.flush()
    return school


def confirm_school(db: Session, user: User, school: School, name: str, primary_domain: str | None,
                   aliases: list[str] | None = None) -> School:
    """Confirm what an unrecognized school is. Merges into an existing school with the same name."""
    domain = normalize_domain(primary_domain)
    name = name.strip()
    typed_as = school.name
    target = _find(db, user, name) if name != school.name else None
    if target:
        profs = db.scalars(select(Professor).where(Professor.school_id == school.id)).all()
        target_names = set(db.scalars(select(Professor.normalized_name).where(Professor.school_id == target.id)))
        if clashes := [p.name for p in profs if p.normalized_name in target_names]:
            raise ValueError(f"Already listed under {target.name}: {', '.join(clashes)}. Delete the duplicate first.")
        for prof in profs:
            prof.school_id = target.id
        db.flush()
        db.expire(school, ["professors"])  # otherwise deleting the school would null out the moved rows
        db.delete(school)
        school = target
    else:
        school.name = name
    school.aliases = _dedupe([*school.aliases, *(aliases or []), typed_as], school.name)
    school.primary_domain = domain or school.primary_domain
    school.confirmed, school.suggestions = True, []
    db.flush()
    # Professors that couldn't be found may be findable now that the school is known.
    for prof in db.scalars(select(Professor).where(
        Professor.school_id == school.id, Professor.resolve_status.in_(["not_found", "needs_review"])
    )):
        enqueue(db, "resolve_professor", professor_id=prof.id)
    db.commit()
    return school


def _add_alias(school: School, alias: str) -> None:
    school.aliases = _dedupe([*school.aliases, alias], school.name)


def _dedupe(aliases: list[str], name: str) -> list[str]:
    seen, out = {name.lower()}, []
    for a in aliases:
        if a and a.strip() and a.strip().lower() not in seen:
            seen.add(a.strip().lower())
            out.append(a.strip())
    return out
