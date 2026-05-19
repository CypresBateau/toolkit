from __future__ import annotations
from fastapi import APIRouter
from ..state import app_state

router = APIRouter(tags=["lifecycle"])

@router.post("/load")
async def load():
    app_state["loaded"] = True
    return {"status": "ok"}

@router.post("/unload")
async def unload():
    app_state["loaded"] = False
    return {"status": "unloaded"}
