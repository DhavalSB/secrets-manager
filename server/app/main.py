"""FastAPI app. Run from server/:  ../env/bin/uvicorn app.main:app --reload"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import auth, routes_org, routes_secrets, routes_tokens
from .db import create_tables


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_tables()
    yield


app = FastAPI(title="SecretsManager", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(routes_secrets.router)
app.include_router(routes_org.router)
app.include_router(routes_tokens.router)


@app.get("/health")
def health():
    return {"ok": True}
