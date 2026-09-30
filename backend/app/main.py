import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import meta, outreach, papers, professors, profile
from app.config import get_settings

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="PhDDog API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (meta, profile, professors, papers, outreach):
    app.include_router(module.router)
