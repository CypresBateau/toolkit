from __future__ import annotations
from typing import Any, Dict

def run_tool(tool: Dict[str, Any], arguments: Dict[str, Any]) -> Any:
    flat: Dict[str, Any] = {}
    for k, v in arguments.items():
        flat[k] = v["Value"] if isinstance(v, dict) and "Value" in v else v

    local_ns: Dict[str, Any] = {}
    code = tool.get("generated_code") or tool.get("code", "")
    exec(code, {"__builtins__": __builtins__}, local_ns)  # noqa: S102
    return local_ns[tool["function_name"]](**flat)
