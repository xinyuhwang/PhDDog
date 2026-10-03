from fastapi import APIRouter, HTTPException, UploadFile

from app.api.deps import DB, CurrentUser
from app.api.schemas import ProfileIn, ProfileOut
from app.services import profile as svc

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileOut | None)
def get_profile(db: DB, user: CurrentUser):
    return svc.active_profile(db, user)


@router.put("", response_model=ProfileOut)
def put_profile(body: ProfileIn, db: DB, user: CurrentUser):
    return svc.update_profile(
        db, user, body.research_statement, [k.strip() for k in body.keywords if k.strip()], body.project_notes,
    )


@router.post("/resume", response_model=ProfileOut)
async def upload_resume(file: UploadFile, db: DB, user: CurrentUser):
    content = await file.read()
    if not content.startswith(b"%PDF"):
        raise HTTPException(400, "Please upload a PDF resume")
    return svc.upload_resume(db, user, content, file.filename or "resume.pdf")
