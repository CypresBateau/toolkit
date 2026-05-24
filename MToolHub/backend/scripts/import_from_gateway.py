"""
从 Gateway 导入所有资源（工具、模型、技能）到统一的 resources.json

运行方式：
    python scripts/import_from_gateway.py [gateway_url] [output_dir]

功能：
    1. 从 Gateway 的 /tools 接口获取所有服务列表
    2. 对每个 JSON 接口服务，调用其 /api/v1/tools 获取函数列表
    3. 对每个图像接口服务，创建单个模型资源
    4. 兼容不同字段名（description/short_description, tool_name/name）
    5. 自动检测中文并填充 description_zh 和 name_zh
    6. 生成统一的 resources.json 文件
"""

import asyncio
import httpx
import json
import re
from pathlib import Path
from typing import Dict, List, Any


def extract_input_schema(func: dict) -> Any:
    """提取函数的参数信息，原样保留，不做格式转换。

    策略：
    - 有结构化 parameters 字段（tool-mdcalc / tool-skills）：直接存 list，信息完整
    - 无 parameters 但有 docstring（tool-scale / tool-unit）：存 docstring 文本，Claude 能读懂
    - 都没有：返回 None
    """
    parameters = func.get("parameters")
    if parameters and isinstance(parameters, list) and len(parameters) > 0:
        return parameters  # 原样保留结构化参数列表

    docstring = func.get("docstring", "").strip()
    if docstring:
        return docstring  # 原样保留 docstring 文本

    return None


def has_chinese(text: str) -> bool:
    """检测文本中是否包含中文字符"""
    if not text:
        return False
    return bool(re.search(r'[\u4e00-\u9fff]', text))


async def fetch_gateway_tools(gateway_url: str) -> Dict[str, Any]:
    """获取 Gateway 所有已注册工具"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(f"{gateway_url}/tools")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[ERR] 无法连接到 Gateway: {e}")
            return {}


async def fetch_tool_functions(endpoint: str) -> List[Dict[str, Any]]:
    """获取函数列表，并并发获取每个函数的详情（含 parameters）"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.get(f"{endpoint}/api/v1/tools")
            resp.raise_for_status()
            summaries = resp.json().get("tools", [])
        except Exception as e:
            print(f"   [WARN] 无法获取工具函数列表: {e}")
            return []

        sem = asyncio.Semaphore(20)

        async def fetch_detail(fn_name: str) -> dict:
            async with sem:
                try:
                    r = await client.get(f"{endpoint}/api/v1/tools/{fn_name}", timeout=10.0)
                    if r.status_code == 200:
                        return r.json()
                except Exception:
                    pass
                return {"function_name": fn_name}

        return list(await asyncio.gather(*[
            fetch_detail(s["function_name"]) for s in summaries
        ]))


async def fetch_tool_endpoint(gateway_url: str, tool_name: str) -> str:
    """通过 /tools/{name}/info 获取工具容器的 endpoint"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{gateway_url}/tools/{tool_name}/info")
        resp.raise_for_status()
        return resp.json()["endpoint"]


async def import_json_service(tool_name: str, tool_info: dict, gateway_url: str = "") -> List[Dict[str, Any]]:
    """导入 JSON 接口服务的所有函数"""
    try:
        endpoint = await fetch_tool_endpoint(gateway_url, tool_name)
    except Exception as e:
        print(f"   [WARN] 无法获取 endpoint: {e}")
        return []

    functions = await fetch_tool_functions(endpoint)
    if not functions:
        return []

    print(f"   [INFO] 发现 {len(functions)} 个函数")

    resources = []
    for func in functions:
        # 提取描述（兼容 description 和 short_description）
        description = func.get("description") or func.get("short_description") or ""

        # 提取名称（兼容 tool_name 和 name）
        name = func.get("tool_name") or func.get("name") or func["function_name"]

        # 判断资源类型（通过 tool_name 前缀）
        if "skill" in tool_name.lower():
            resource_type = "skill"
            category = "skill"
        else:
            resource_type = "tool"
            category = tool_name.replace("tool-", "")

        # 检测中文并填充 description_zh 和 name_zh
        description_zh = None
        name_zh = None
        if has_chinese(description):
            description_zh = description
        if has_chinese(name):
            name_zh = name

        resource = {
            "id": f"{tool_name}:{func['function_name']}",
            "resource_type": resource_type,
            "name": name,
            "name_zh": name_zh,
            "description": description,
            "description_zh": description_zh,
            "keywords": [],  # 元数据中没有 keywords 字段，留空
            "gateway_tool_name": tool_name,
            "gateway_interface": "call",
            "function_name": func["function_name"],
            "input_schema": extract_input_schema(func),
            "category": category,
            "enabled": True
        }
        resources.append(resource)

    print(f"   [OK] 导入 {len(resources)} 个函数")
    return resources


def create_model_resource(tool_name: str, tool_info: dict) -> Dict[str, Any]:
    """创建模型资源"""
    description = tool_info.get("description", tool_name)

    # 检测中文
    description_zh = None
    name_zh = None
    if has_chinese(description):
        description_zh = description
    if has_chinese(tool_name):
        name_zh = tool_name

    return {
        "id": tool_name,
        "resource_type": "model",
        "name": tool_info.get("description", tool_name),
        "name_zh": name_zh,
        "description": description,
        "description_zh": description_zh,
        "keywords": [],
        "gateway_tool_name": tool_name,
        "gateway_interface": "predict",
        "function_name": None,  # 模型没有 function_name
        "input_type": "image",
        "accepted_formats": ["jpg", "jpeg", "png"],
        "category": "model",
        "enabled": True
    }


async def import_from_gateway(gateway_url: str, output_dir: str):
    """主导入流程"""
    print(f"[INFO] 正在连接 Gateway: {gateway_url}")

    # 1. 获取 Gateway 注册的所有服务
    tools_data = await fetch_gateway_tools(gateway_url)
    if not tools_data:
        print("[ERR] 未能获取任何工具数据")
        return

    print(f"[OK] 发现 {len(tools_data)} 个 Gateway 服务")

    all_resources = []

    # 2. 分类处理
    for name, info in tools_data.items():
        print(f"\n[INFO] 处理服务: {name}")

        if info.get("input") == "json":
            # JSON 接口 -> 调用 /api/v1/tools 获取函数列表
            resources = await import_json_service(name, info, gateway_url)
            all_resources.extend(resources)

        elif info.get("input") == "image":
            # 图像接口 -> 创建单个模型资源
            resource = create_model_resource(name, info)
            all_resources.append(resource)
            print(f"   [OK] 导入模型: {resource['name']}")

    # 3. 保存到统一的 resources.json
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    resources_file = output_path / "resources.json"
    with open(resources_file, "w", encoding="utf-8") as f:
        json.dump(all_resources, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] 已保存 {len(all_resources)} 个资源到: {resources_file}")

    # 统计
    type_counts = {}
    for res in all_resources:
        res_type = res["resource_type"]
        type_counts[res_type] = type_counts.get(res_type, 0) + 1

    print("\n[INFO] 资源类型统计:")
    for res_type, count in sorted(type_counts.items()):
        print(f"   {res_type}: {count}")

if __name__ == "__main__":
    import sys

    # 默认配置
    GATEWAY_URL = "http://localhost:9000"
    OUTPUT_DIR = "data/registry"

    # 支持命令行参数
    if len(sys.argv) > 1:
        GATEWAY_URL = sys.argv[1]
    if len(sys.argv) > 2:
        OUTPUT_DIR = sys.argv[2]

    asyncio.run(import_from_gateway(GATEWAY_URL, OUTPUT_DIR))
