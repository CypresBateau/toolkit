from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

class CallRequest(BaseModel):
    function_name: str
    arguments: Dict[str, Any]

class CallResponse(BaseModel):
    function_name: str
    tool_name: str
    category: str
    result: Any

class ToolSummary(BaseModel):
    function_name: str
    tool_name: str
    description: Optional[str] = None

class ToolDetail(BaseModel):
    function_name: str
    tool_name: str
    description: Optional[str] = None

class ToolListResponse(BaseModel):
    category: str
    count: int
    tools: List[ToolSummary]

class HealthResponse(BaseModel):
    status: str
    category: str
    tool_count: int
    loaded: bool
