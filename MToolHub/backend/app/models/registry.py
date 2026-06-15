"""
数据模型 - 注册表相关

统一的资源元数据结构，支持 Tool、Model、Skill 三种类型
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any


class ResourceMetadata(BaseModel):
    """统一资源元数据（工具、模型、技能）"""

    id: str = Field(..., description="资源唯一标识，如 tool-mdcalc:wells_score_dvt | mavl | tool-skills:drug_interaction")
    resource_type: Literal["tool", "model", "skill"] = Field(..., description="资源类型")
    name: str = Field(..., description="资源名称")
    name_zh: Optional[str] = Field(None, description="中文名称")
    description: str = Field(..., description="描述")
    description_zh: Optional[str] = Field(None, description="中文描述")
    keywords: List[str] = Field(default_factory=list, description="关键词列表")

    # Gateway 调用信息
    gateway_tool_name: str = Field(..., description="Gateway 中的工具名，如 tool-mdcalc | mavl | tool-skills")
    gateway_interface: Literal["call", "predict"] = Field(..., description="Gateway 接口类型：call 用 JSON，predict 用 multipart")
    function_name: Optional[str] = Field(None, description="函数名称（仅 call 接口需要）")

    # 参数定义（仅 call 接口）
    input_schema: Optional[Any] = Field(None, description="输入参数 JSON Schema 或参数列表")
    output_schema: Optional[Any] = Field(None, description="返回字段列表，格式 [{key, type, description}]")

    # 模型特定字段
    input_type: Optional[str] = Field(None, description="输入类型：image | text | json")
    accepted_formats: Optional[List[str]] = Field(None, description="接受的文件格式，如 ['jpg', 'png']")

    # 技能特定字段
    skill_type: Optional[Literal["document_only", "tool_reference", "executable", "complex_workflow"]] = Field(
        None, description="技能类型"
    )
    skill_md_path: Optional[str] = Field(None, description="SKILL.md 文件路径")
    coworker_path: Optional[str] = Field(None, description="coworker.py 文件路径")
    references_dir: Optional[str] = Field(None, description="references 目录路径")

    # 元数据
    category: Optional[str] = Field(None, description="子类别：mdcalc | unit | scale | skill | model")
    enabled: bool = Field(True, description="是否启用")


# 向后兼容的别名
ToolMetadata = ResourceMetadata
ModelMetadata = ResourceMetadata
SkillMetadata = ResourceMetadata


class ToolsRegistry(BaseModel):
    """工具注册表（向后兼容）"""
    tools: List[ResourceMetadata]


class ModelsRegistry(BaseModel):
    """模型注册表（向后兼容）"""
    models: List[ResourceMetadata]


class SkillsRegistry(BaseModel):
    """技能注册表（向后兼容）"""
    skills: List[ResourceMetadata]
