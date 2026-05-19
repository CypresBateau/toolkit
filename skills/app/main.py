from __future__ import annotations
import os, sys
from contextlib import asynccontextmanager
from typing import AsyncIterator
from fastapi import FastAPI
from .routers import call, health, lifecycle, tools
from .state import app_state
from .tool_registry import ToolRegistry

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    json_path = os.getenv("TOOL_JSON_PATH", "")
    if not json_path:
        print("ERROR: TOOL_JSON_PATH is not set.", file=sys.stderr)
        sys.exit(1)
    registry = ToolRegistry()
    registry.load(json_path)
    app_state["registry"] = registry
    app_state["loaded"] = True
    yield

app = FastAPI(title="Skills Service", lifespan=lifespan)
app.include_router(health.router)
app.include_router(lifecycle.router)
app.include_router(tools.router)
app.include_router(call.router)
