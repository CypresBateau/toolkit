"""
数据模型 - API 请求和响应

定义 API 接口的请求和响应数据结构
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal


class ChatRequest(BaseModel):
    """对话请求"""

    message: str = Field(..., description="用户消息")
    conversation_id: Optional[str] = Field(None, description="会话 ID")
    mode: Optional[Literal["auto", "direct_call", "claude_select", "chat_only"]] = Field(
        "auto", description="路由模式，auto 表示自动决策"
    )


class ChatResponse(BaseModel):
    """对话响应"""

    response: str = Field(..., description="系统回复")
    tools_used: List[str] = Field(default_factory=list, description="使用的工具/模型/技能 ID 列表")
    routing_info: Dict[str, Any] = Field(default_factory=dict, description="路由信息")
    disclaimer: str = Field(..., description="医疗免责声明")


class ExecuteRequest(BaseModel):
    """直接执行请求"""

    resource_id: str = Field(..., description="资源 ID")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="执行参数")
    context: Optional[str] = Field(None, description="上下文信息")


class ExecuteResponse(BaseModel):
    """直接执行响应"""

    success: bool = Field(..., description="是否成功")
    result: Any = Field(..., description="执行结果")
    trace: Optional[str] = Field(None, description="执行追踪信息")
    disclaimer: str = Field(..., description="医疗免责声明")


class RoutingPlan(BaseModel):
    """路由计划"""

    mode: Literal["direct_call", "claude_select", "chat_only"] = Field(..., description="路由模式")
    confidence: Literal["high", "medium", "low"] = Field(..., description="置信度")
    selected_resources: List[Dict[str, Any]] = Field(default_factory=list, description="选中的资源列表")


class ToolSearchRequest(BaseModel):
    """工具搜索请求"""

    query: str = Field(..., description="搜索查询")
    top_k: int = Field(5, ge=1, le=20, description="返回结果数量")
    categories: Optional[List[str]] = Field(None, description="限定类别：tool/model/skill")


class ToolSearchResponse(BaseModel):
    """工具搜索响应"""

    results: List[Dict[str, Any]] = Field(..., description="搜索结果")
    total: int = Field(..., description="结果总数")
