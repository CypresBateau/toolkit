"""
FAISS 索引管理

负责构建和检索 FAISS 向量索引
"""

import faiss
import pickle
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.config import settings
from app.core.embedding import embedding_model


class FAISSIndex:
    """FAISS 索引管理器"""

    def __init__(self, category: str):
        """
        初始化 FAISS 索引

        Args:
            category: 资源类别（tool/model/skill）
        """
        self.category = category
        self.index = None
        self.metadata = []
        self.index_path = Path(settings.faiss_index_dir) / f"{category}_index.faiss"
        self.metadata_path = Path(settings.faiss_index_dir) / f"{category}_metadata.pkl"

    def build(self, items: List[Dict[str, Any]]):
        """
        构建 FAISS 索引

        Args:
            items: 资源列表，每个资源包含 name, description, keywords 等字段
        """
        if not items:
            print(f"警告：{self.category} 类别没有资源，跳过索引构建")
            return

        # 构建索引文本
        texts = []
        metadata = []
        for item in items:
            # 拼接索引文本：name + description + description_zh + keywords
            text_parts = [
                item.get("name", ""),
                item.get("description", ""),
                item.get("description_zh", ""),
            ]
            keywords = item.get("keywords", [])
            if keywords:
                text_parts.append(f"Keywords: {', '.join(keywords)}")

            text = ". ".join([p for p in text_parts if p])
            texts.append(text)
            metadata.append(item)

        # 编码为向量
        print(f"[INFO] 正在为 {len(texts)} 个 {self.category} 资源生成向量...")
        vectors = embedding_model.encode(texts, normalize=True)

        # 构建 FAISS 索引（使用内积，因为向量已归一化，等价于余弦相似度）
        dim = vectors.shape[1]
        self.index = faiss.IndexFlatIP(dim)
        self.index.add(vectors.astype(np.float32))
        self.metadata = metadata

        print(f"[OK] {self.category} 索引构建完成：{len(texts)} 个资源")

    def save(self):
        """保存索引到磁盘"""
        if self.index is None:
            print(f"警告：{self.category} 索引为空，跳过保存")
            return

        # 确保目录存在
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

        # 保存 FAISS 索引
        faiss.write_index(self.index, str(self.index_path))

        # 保存元数据
        with open(self.metadata_path, "wb") as f:
            pickle.dump(self.metadata, f)

        print(f"[OK] {self.category} 索引已保存到 {self.index_path}")

    def load(self):
        """从磁盘加载索引"""
        if not self.index_path.exists():
            print(f"警告：{self.category} 索引文件不存在：{self.index_path}")
            return False

        # 加载 FAISS 索引
        self.index = faiss.read_index(str(self.index_path))

        # 加载元数据
        with open(self.metadata_path, "rb") as f:
            self.metadata = pickle.load(f)

        print(f"[OK] {self.category} 索引已加载：{len(self.metadata)} 个资源")
        return True

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        语义搜索

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            搜索结果列表，每个结果包含 item（元数据）、score（相似度分数）、category
        """
        if self.index is None:
            return []

        # 编码查询文本
        query_vec = embedding_model.encode(query, normalize=True)
        query_vec = query_vec.reshape(1, -1).astype(np.float32)

        # 搜索
        scores, indices = self.index.search(query_vec, min(top_k, len(self.metadata)))

        # 构建结果
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:  # FAISS 返回 -1 表示没有更多结果
                continue
            results.append({
                "item": self.metadata[idx],
                "score": float(score),
                "category": self.category,
            })

        return results


class VectorSearchEngine:
    """向量搜索引擎，使用统一索引"""

    def __init__(self):
        self.index = FAISSIndex("unified")
        self.index.load()

    def search(
        self,
        query: str,
        top_k: int = 5,
        categories: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        跨类别语义搜索

        Args:
            query: 查询文本
            top_k: 返回结果数量
            categories: 限定搜索的类别列表，None 表示搜索所有类别

        Returns:
            搜索结果列表，按分数降序排列
        """
        # 从统一索引搜索（多取一些结果以便过滤后仍有足够数量）
        search_k = top_k * 3 if categories else top_k
        results = self.index.search(query, search_k)

        # 按类别过滤
        if categories:
            results = [
                r for r in results
                if r["item"].get("resource_type") in categories
            ]

        # 返回 top_k
        return results[:top_k]

    def reload(self):
        """重新加载索引"""
        self.index = FAISSIndex("unified")
        self.index.load()


# 全局向量搜索引擎实例
vector_search_engine = VectorSearchEngine()
