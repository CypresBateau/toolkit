"""
统一执行器

根据资源的 gateway_interface 字段路由到不同的 Gateway 接口
"""

import httpx
from typing import Dict, Any, Optional
from app.models.registry import ResourceMetadata
from app.core.claude_client import claude_client
from app.config import settings


class UnifiedExecutor:
    """统一资源执行器，根据 gateway_interface 调用不同接口"""

    def __init__(self):
        self.gateway_base_url = settings.gateway_base_url
        self.timeout = settings.gateway_timeout

    async def execute(
        self,
        resource: ResourceMetadata,
        user_message: str,
        arguments: Optional[Dict[str, Any]] = None,
        file_bytes: Optional[bytes] = None,
        filename: Optional[str] = None,
        conversation_history: Optional[list] = None,
    ) -> Dict[str, Any]:
        """
        执行资源调用

        Args:
            resource: 资源元数据
            user_message: 用户消息
            arguments: 执行参数（可选，如果提供则直接使用）
            file_bytes: 文件字节（用于模型）
            filename: 文件名（用于模型）
            conversation_history: 对话历史

        Returns:
            执行结果字典：
            {
                "success": bool,
                "response": str,  # 给用户的回复
                "result": Any,    # 原始结果
                "trace": str,     # 执行追踪
            }
        """
        if resource.gateway_interface == "call":
            return await self._execute_call_interface(
                resource, user_message, arguments, conversation_history
            )
        elif resource.gateway_interface == "predict":
            return await self._execute_predict_interface(
                resource, file_bytes, filename, arguments
            )
        else:
            return {
                "success": False,
                "response": f"不支持的 gateway_interface: {resource.gateway_interface}",
                "result": None,
                "trace": f"未知接口类型: {resource.gateway_interface}",
            }

    async def _execute_call_interface(
        self,
        resource: ResourceMetadata,
        user_message: str,
        arguments: Optional[Dict[str, Any]],
        conversation_history: Optional[list],
    ) -> Dict[str, Any]:
        """
        执行 call 接口（JSON 参数）

        流程：
        1. 如果没有提供 arguments，使用 Claude 从 user_message 中提取参数
        2. 调用 Gateway /call 接口
        3. 使用 Claude 解读结果
        """
        trace = []

        # 步骤 1：提取参数
        if arguments is None:
            trace.append("正在从用户消息中提取参数...")
            arguments = await claude_client.extract_parameters(
                user_message=user_message,
                tool_schema=resource.input_schema or {},
                conversation_history=conversation_history,
            )

            if arguments is None:
                # Claude 没有调用工具，可能在追问参数
                return {
                    "success": False,
                    "response": "请提供更多信息以便我帮您计算。",
                    "result": None,
                    "trace": "\n".join(trace),
                }

            trace.append(f"提取的参数：{arguments}")

        # 步骤 2：调用 Gateway
        trace.append(f"正在调用 {resource.gateway_tool_name}/{resource.function_name}...")
        try:
            result = await self._call_gateway_json(
                gateway_tool_name=resource.gateway_tool_name,
                function_name=resource.function_name,
                arguments=arguments,
            )
            trace.append(f"调用成功")
        except Exception as e:
            trace.append(f"调用失败：{e}")
            return {
                "success": False,
                "response": f"工具调用失败：{e}",
                "result": None,
                "trace": "\n".join(trace),
            }

        return {
            "success": True,
            "response": "",
            "result": result,
            "trace": "\n".join(trace),
        }

    async def _execute_predict_interface(
        self,
        resource: ResourceMetadata,
        file_bytes: Optional[bytes],
        filename: Optional[str],
        arguments: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        执行 predict 接口（multipart/form-data）

        流程：
        1. 检查是否有文件上传
        2. 调用 Gateway /predict 接口
        """
        trace = []

        # 步骤 1：检查文件
        if not file_bytes:
            return {
                "success": False,
                "response": f"该功能需要上传{resource.input_type or '文件'}，请上传后重试。",
                "result": None,
                "trace": "缺少文件输入",
            }

        # 步骤 2：调用 Gateway
        trace.append(f"正在调用 {resource.gateway_tool_name} 模型...")
        try:
            params = arguments or {}
            top_k = params.get("top_k", 5)

            result = await self._call_gateway_predict(
                gateway_tool_name=resource.gateway_tool_name,
                file_bytes=file_bytes,
                filename=filename or "image.jpg",
                top_k=top_k,
            )
            trace.append(f"模型推理成功")
        except Exception as e:
            trace.append(f"模型推理失败：{e}")
            return {
                "success": False,
                "response": f"模型推理失败：{e}",
                "result": None,
                "trace": "\n".join(trace),
            }

        return {
            "success": True,
            "response": "",
            "result": result,
            "trace": "\n".join(trace),
        }

    async def _call_gateway_json(
        self,
        gateway_tool_name: str,
        function_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        调用 Gateway /call 接口

        Args:
            gateway_tool_name: Gateway 中的工具名（如 tool-mdcalc）
            function_name: 函数名
            arguments: 参数字典

        Returns:
            Gateway 返回的结果
        """
        url = f"{self.gateway_base_url}/tools/{gateway_tool_name}/call"
        payload = {
            "function_name": function_name,
            "arguments": arguments,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()

    async def _call_gateway_predict(
        self,
        gateway_tool_name: str,
        file_bytes: bytes,
        filename: str,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """
        调用 Gateway /predict 接口

        Args:
            gateway_tool_name: Gateway 中的工具名（如 mavl）
            file_bytes: 文件字节
            filename: 文件名
            top_k: 返回 top-k 预测结果

        Returns:
            Gateway 返回的结果
        """
        url = f"{self.gateway_base_url}/tools/{gateway_tool_name}/predict"

        files = {"file": (filename, file_bytes)}
        data = {"top_k": str(top_k)}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, files=files, data=data)
            response.raise_for_status()
            return response.json()


# 全局统一执行器实例
unified_executor = UnifiedExecutor()
