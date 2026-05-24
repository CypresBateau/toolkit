"""
构建 FAISS 索引脚本

从统一的 resources.json 读取资源，生成向量并构建 FAISS 索引
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.registry import registry_manager
from app.core.faiss_index import FAISSIndex
from app.core.embedding import embedding_model


def build_unified_index():
    """构建统一的 FAISS 索引"""
    print("="*60)
    print("FAISS 索引构建工具")
    print("="*60)

    # 确保 Embedding 模型已加载
    print(f"\n[INFO] 向量维度：{embedding_model.dimension}")

    # 获取所有资源
    all_resources = registry_manager.get_all_resources()
    if not all_resources:
        print("[WARN] 没有资源可索引，请先运行 import_from_gateway.py")
        return

    print(f"[INFO] 共 {len(all_resources)} 个资源待索引")

    # 按类型统计
    type_counts = {}
    for res in all_resources:
        res_type = res.resource_type
        type_counts[res_type] = type_counts.get(res_type, 0) + 1

    print("\n[INFO] 资源类型分布:")
    for res_type, count in sorted(type_counts.items()):
        print(f"   {res_type}: {count}")

    # 转换为字典格式
    items_dict = [item.model_dump() for item in all_resources]

    # 创建统一索引
    print("\n[INFO] 开始构建索引...")
    index = FAISSIndex("unified")
    index.build(items_dict)
    index.save()

    print("\n" + "="*60)
    print("[OK] 索引构建完成")
    print("="*60)


if __name__ == "__main__":
    build_unified_index()
