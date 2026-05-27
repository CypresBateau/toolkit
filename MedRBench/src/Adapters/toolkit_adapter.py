"""
ToolkitAdapter - MToolHub 工具库适配器

提供 MedRBench 推理脚本与 MToolHub 后端的集成接口。
支持两种模式：
- baseline: 不提供任何工具（返回空列表）
- experimental: 通过 MToolHub API 搜索和执行工具
"""

import httpx
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """LLM 配置

    provider 支持：
    - "anthropic"        : 直接调用 Anthropic API，读取 ANTHROPIC_API_KEY
    - "openrouter"       : 通过 OpenRouter（OpenAI 兼容），读取 OPENROUTER_API_KEY
                           model 格式: "anthropic/claude-sonnet-4-5"
    - "openai_compatible": 任意 OpenAI 兼容接口，需指定 api_base_url 和 api_key_env
    """
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    temperature: float = 0.0
    max_tokens: int = 4096
    # OpenRouter / OpenAI 兼容接口配置
    api_base_url: Optional[str] = None   # 如 "https://openrouter.ai/api/v1"
    api_key_env: Optional[str] = None    # 读取 API Key 的环境变量名，如 "OPENROUTER_API_KEY"


class MToolHubConfig(BaseModel):
    """MToolHub 配置"""
    enabled: bool = False
    url: str = "http://localhost:8080"
    search_top_k: int = 3
    enable_execution: bool = True
    timeout: int = 30


class ExperimentConfig(BaseModel):
    """实验配置"""
    mode: Literal["baseline", "experimental"] = "baseline"
    llm: LLMConfig = Field(default_factory=LLMConfig)
    mtoolhub: MToolHubConfig = Field(default_factory=MToolHubConfig)


class ClaudeTool(BaseModel):
    """Claude function calling 工具格式"""
    name: str
    description: str
    input_schema: Dict[str, Any]


class ToolkitAdapter:
    """MToolHub 工具库适配器"""

    def __init__(self, config: ExperimentConfig):
        """
        初始化适配器

        Args:
            config: 实验配置对象
        """
        self.config = config
        self.mode = config.mode
        self.mtoolhub_url = config.mtoolhub.url
        self.search_top_k = config.mtoolhub.search_top_k
        self.enable_execution = config.mtoolhub.enable_execution
        self.timeout = config.mtoolhub.timeout

        # 创建 HTTP 客户端
        self.client = httpx.AsyncClient(timeout=self.timeout)

    async def get_tools_for_query(self, query: str) -> List[Dict[str, Any]]:
        """
        根据查询获取相关工具（Claude function calling 格式）

        Args:
            query: 病例描述或诊断问题

        Returns:
            Claude tools 列表（baseline 模式返回空列表）
        """
        # Baseline 模式：不提供任何工具
        if self.mode == "baseline" or not self.config.mtoolhub.enabled:
            return []

        try:
            # 调用 MToolHub 搜索接口
            response = await self.client.get(
                f"{self.mtoolhub_url}/api/tools/search",
                params={"q": query, "top_k": self.search_top_k}
            )
            response.raise_for_status()
            data = response.json()

            # 提取搜索结果
            results = data.get("results", [])

            # 转换为 Claude function calling 格式
            # 搜索结果结构：{"item": {...资源元数据...}, "score": float, "category": str}
            tools = []
            for res in results:
                item = res.get("item", res)  # 兼容直接返回元数据的情况
                resource_id = item.get("id", "")
                if not resource_id:
                    continue

                # 将 resource_id 中的冒号替换为下划线（函数名不支持冒号）
                tool_name = resource_id.replace(":", "_").replace("-", "_")

                # 构建工具定义
                tool = {
                    "name": tool_name,
                    "description": item.get("description", ""),
                    "input_schema": item.get("input_schema") or {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }

                # 保存原始 resource_id 用于后续执行
                tool["_resource_id"] = resource_id

                tools.append(tool)

            return tools

        except Exception as e:
            print(f"[WARN] 工具搜索失败: {e}")
            return []

    async def execute_tool(
        self,
        resource_id: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行工具调用

        Args:
            resource_id: 工具 ID（如 "tool-mdcalc:wells_score_dvt"）
            arguments: 工具参数

        Returns:
            执行结果，包含以下字段：
            - success: bool - 是否成功
            - result: Any - 执行结果
            - trace: str - 执行跟踪信息
            - error: str (可选) - 错误信息
        """
        # 检查是否启用执行
        if not self.enable_execution:
            return {
                "success": False,
                "result": None,
                "trace": "Tool execution disabled in current config",
                "error": "Execution disabled"
            }

        try:
            # 调用 MToolHub 执行接口
            response = await self.client.post(
                f"{self.mtoolhub_url}/api/execute",
                json={
                    "resource_id": resource_id,
                    "arguments": arguments
                }
            )
            response.raise_for_status()
            result = response.json()

            return {
                "success": result.get("success", False),
                "result": result.get("result"),
                "trace": result.get("trace", ""),
                "gateway_response": result.get("gateway_response")
            }

        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "result": None,
                "trace": f"HTTP error: {e.response.status_code}",
                "error": str(e)
            }
        except Exception as e:
            return {
                "success": False,
                "result": None,
                "trace": f"Execution failed: {str(e)}",
                "error": str(e)
            }

    async def close(self):
        """关闭 HTTP 客户端"""
        await self.client.aclose()

    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close()


def load_config(config_path: str, mode: str) -> ExperimentConfig:
    """
    从 YAML 文件加载实验配置

    Args:
        config_path: 配置文件路径
        mode: 配置模式（如 "baseline", "experimental", "ablation.search_only"）

    Returns:
        ExperimentConfig 对象
    """
    import yaml
    from pathlib import Path

    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_file, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)

    # 解析嵌套模式（如 "ablation.search_only"）
    mode_parts = mode.split(".")
    config_section = config_data
    for part in mode_parts:
        if part not in config_section:
            raise ValueError(f"配置模式不存在: {mode}")
        config_section = config_section[part]

    # 构建 ExperimentConfig
    return ExperimentConfig(**config_section)
