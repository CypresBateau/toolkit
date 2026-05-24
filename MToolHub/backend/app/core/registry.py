"""
注册表管理模块

负责加载和管理统一的资源注册表
"""

import json
from pathlib import Path
from typing import List, Optional
from app.models.registry import ResourceMetadata
from app.config import settings


class RegistryManager:
    """统一注册表管理器"""

    def __init__(self):
        self.resources: List[ResourceMetadata] = []
        self._load_resources()

    def _load_resources(self):
        """加载统一的 resources.json"""
        resources_path = Path(settings.resources_registry_path)
        if not resources_path.exists():
            print(f"[WARN] 资源注册表不存在：{resources_path}")
            return

        with open(resources_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # data 应该是一个列表
        if not isinstance(data, list):
            print(f"[ERR] resources.json 格式错误，应为数组")
            return

        loaded = []
        for item in data:
            try:
                resource = ResourceMetadata(**item)
                if resource.enabled:
                    loaded.append(resource)
            except Exception as e:
                print(f"  [SKIP] 跳过资源（字段不匹配）：{item.get('id', '?')} - {e}")

        self.resources = loaded
        print(f"[OK] 已加载 {len(self.resources)} 个资源")

    def get_resource_by_id(self, resource_id: str) -> Optional[ResourceMetadata]:
        """根据 ID 获取资源"""
        for resource in self.resources:
            if resource.id == resource_id:
                return resource
        return None

    def get_all_resources(self) -> List[ResourceMetadata]:
        """获取所有资源"""
        return self.resources

    def get_resources_by_type(self, resource_type: str) -> List[ResourceMetadata]:
        """根据类型获取资源"""
        return [r for r in self.resources if r.resource_type == resource_type]

    def reload(self):
        """重新加载注册表"""
        self.resources = []
        self._load_resources()


# 全局注册表管理器实例
registry_manager = RegistryManager()
