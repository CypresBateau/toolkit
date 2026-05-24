"""
Claude API 客户端

封装 Anthropic Claude API 调用
"""

from anthropic import AsyncAnthropic
from typing import List, Dict, Any, Optional
from app.config import settings


class ClaudeClient:
    """Claude API 客户端"""

    def __init__(self):
        self.client = AsyncAnthropic(api_key=settings.claude_api_key)
        self.model = settings.claude_model
        self.max_tokens = settings.claude_max_tokens

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: Optional[int] = None,
    ) -> Any:
        """
        发送对话请求

        Args:
            messages: 消息列表
            system: 系统提示词
            tools: 工具列表（Claude tool_use 格式）
            max_tokens: 最大 token 数

        Returns:
            Claude API 响应对象
        """
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "messages": messages,
        }

        if system:
            kwargs["system"] = system

        if tools:
            kwargs["tools"] = tools

        response = await self.client.messages.create(**kwargs)
        return response

    @staticmethod
    def _normalize_tool_schema(input_schema: Any) -> Dict[str, Any]:
        """
        将任意格式的 input_schema 转换为 Anthropic API 要求的 dict 格式。

        input_schema 有三种来源：
        - dict：已是标准 JSON Schema，直接使用
        - list：tool-mdcalc/tool-skills 的结构化参数列表，转为带 description 的 dict
        - str：tool-scale/tool-unit 的 docstring，转为带 description 的 dict，让 Claude 自行解读
        - None：返回空 schema
        """
        if input_schema is None:
            return {"type": "object", "properties": {}}

        if isinstance(input_schema, dict):
            return input_schema

        if isinstance(input_schema, list):
            # 结构化参数列表，序列化为 JSON 字符串放入 description
            import json as _json
            return {
                "type": "object",
                "properties": {
                    "parameters": {
                        "type": "string",
                        "description": (
                            "根据以下参数定义提取参数并以 JSON 格式提供：\n"
                            + _json.dumps(input_schema, ensure_ascii=False, indent=2)
                        ),
                    }
                },
            }

        if isinstance(input_schema, str):
            # docstring 文本，直接放入 description
            return {
                "type": "object",
                "properties": {
                    "parameters": {
                        "type": "string",
                        "description": (
                            "根据以下函数文档提取参数并以 JSON 格式提供：\n"
                            + input_schema
                        ),
                    }
                },
            }

        return {"type": "object", "properties": {}}

    async def extract_parameters(
        self,
        user_message: str,
        tool_schema: Any,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        使用 Claude 从自然语言中提取工具参数

        Args:
            user_message: 用户消息
            tool_schema: 工具的 input_schema（可以是 dict、list 或 str）
            conversation_history: 对话历史

        Returns:
            提取的参数字典，如果 Claude 没有调用工具则返回 None
        """
        # 将任意格式的 input_schema 转换为 Anthropic API 要求的 dict
        normalized_schema = self._normalize_tool_schema(tool_schema)

        # 构建工具定义
        tool_def = {
            "name": "extract_params",
            "description": "Extract parameters from user message for the medical tool",
            "input_schema": normalized_schema,
        }

        # 构建消息
        messages = conversation_history or []
        messages.append({"role": "user", "content": user_message})

        # 系统提示词
        system = (
            "你是医疗计算助手。请根据用户输入的信息提取工具所需的参数。"
            "如果用户未提供某些必需参数，请直接询问，不要猜测。"
        )

        # 调用 Claude
        response = await self.chat(messages=messages, system=system, tools=[tool_def])

        # 检查是否调用了工具
        if response.stop_reason == "tool_use":
            for block in response.content:
                if block.type == "tool_use":
                    return block.input

        return None

    async def interpret_result(
        self,
        user_message: str,
        tool_result: Any,
        tool_name: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        使用 Claude 解读工具/模型的执行结果

        Args:
            user_message: 用户消息
            tool_result: 工具执行结果
            tool_name: 工具名称
            conversation_history: 对话历史

        Returns:
            Claude 生成的解读文本
        """
        # 构建消息
        messages = conversation_history or []
        messages.append({"role": "user", "content": user_message})
        messages.append({
            "role": "assistant",
            "content": f"我已经使用 {tool_name} 进行了计算/分析，结果如下：\n{tool_result}",
        })
        messages.append({
            "role": "user",
            "content": "请用通俗易懂的语言解释这个结果，并给出临床建议。",
        })

        # 系统提示词
        system = (
            "你是专业的医疗助手。请根据工具/模型的执行结果，"
            "用清晰、准确、通俗的语言向用户解释，并提供临床建议。"
            f"\n\n{settings.medical_disclaimer}"
        )

        # 调用 Claude
        response = await self.chat(messages=messages, system=system)

        # 提取文本
        for block in response.content:
            if block.type == "text":
                return block.text

        return "无法解读结果"


# 全局 Claude 客户端实例
claude_client = ClaudeClient()
