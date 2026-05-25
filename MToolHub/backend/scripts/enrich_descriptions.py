"""
enrich_descriptions.py — 用 DeepSeek API 为中文 description 批量生成英文版本

运行方式：
    python scripts/enrich_descriptions.py [--registry path/to/resources.json] [--dry-run]

功能：
    1. 扫描 resources.json，找出 description 以中文为主的资源
    2. 调用 DeepSeek API 将中文 description 翻译为英文
    3. 英文写入 description，原中文保留到 description_zh
    4. 保存回 resources.json（原文件备份为 resources.json.bak）

依赖：
    pip install openai  # DeepSeek API 兼容 OpenAI SDK
"""

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

from openai import OpenAI

# DeepSeek API 配置
DEEPSEEK_API_KEY = "your-deepseek-api-key-here"  # 替换为你的 key，或通过环境变量 DEEPSEEK_API_KEY 传入
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

# 默认注册表路径
DEFAULT_REGISTRY = Path(__file__).parent.parent / "data" / "registry" / "resources.json"


def is_chinese_dominant(text: str) -> bool:
    """判断文本是否以中文为主（中文字符占比超过 30%）"""
    if not text:
        return False
    chinese = len(re.findall(r'[\u4e00-\u9fff]', text))
    return chinese > len(text) * 0.3


def translate_to_english(client: OpenAI, text: str, resource_type: str, name: str) -> Optional[str]:
    """
    调用 DeepSeek API 将中文描述翻译为英文医学描述

    Args:
        client: OpenAI 兼容客户端
        text: 中文描述
        resource_type: 资源类型（tool/model/skill）
        name: 资源名称（提供上下文）

    Returns:
        英文描述，失败返回 None
    """
    system_prompt = (
        "You are a professional medical translator. "
        "Translate the given Chinese medical tool/model/skill description into concise, accurate English. "
        "The translation should be suitable for use as a search index description. "
        "Output only the translated English text, no explanations."
    )

    user_prompt = (
        f"Resource type: {resource_type}\n"
        f"Resource name: {name}\n"
        f"Chinese description to translate:\n{text}"
    )

    try:
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=512,
            temperature=0.1,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"   [ERR] API 调用失败: {e}")
        return None


def enrich_descriptions(registry_path: Path, dry_run: bool = False):
    """主流程"""
    import os

    # 获取 API Key（优先环境变量）
    api_key = os.environ.get("DEEPSEEK_API_KEY", DEEPSEEK_API_KEY)
    if api_key == "your-deepseek-api-key-here":
        print("[ERR] 请设置 DEEPSEEK_API_KEY 环境变量或修改脚本中的 DEEPSEEK_API_KEY")
        sys.exit(1)

    # 加载注册表
    print(f"[INFO] 加载注册表: {registry_path}")
    with open(registry_path, encoding="utf-8") as f:
        resources = json.load(f)

    # 找出需要翻译的资源
    to_translate = [
        r for r in resources
        if is_chinese_dominant(r.get("description", ""))
    ]

    print(f"[INFO] 共 {len(resources)} 个资源，其中 {len(to_translate)} 个需要翻译")
    if not to_translate:
        print("[OK] 无需翻译，退出")
        return

    # 按类型统计
    from collections import Counter
    type_counts = Counter(r["resource_type"] for r in to_translate)
    for rtype, count in sorted(type_counts.items()):
        print(f"   {rtype}: {count} 个")

    if dry_run:
        print("\n[DRY-RUN] 以下资源将被翻译：")
        for r in to_translate:
            print(f"   [{r['resource_type']}] {r['id']}: {r['description'][:60]}...")
        return

    # 备份原文件
    backup_path = registry_path.with_suffix(".json.bak")
    shutil.copy2(registry_path, backup_path)
    print(f"[INFO] 原文件已备份到: {backup_path}")

    # 初始化 DeepSeek 客户端
    client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)

    # 构建 id -> index 映射，方便原地修改
    id_to_idx = {r["id"]: i for i, r in enumerate(resources)}

    # 逐个翻译
    success = 0
    failed = 0
    for i, resource in enumerate(to_translate, 1):
        rid = resource["id"]
        rtype = resource["resource_type"]
        name = resource.get("name") or rid
        desc_zh = resource["description"]

        print(f"\n[{i}/{len(to_translate)}] {rid}")
        print(f"   中文: {desc_zh[:80]}{'...' if len(desc_zh) > 80 else ''}")

        desc_en = translate_to_english(client, desc_zh, rtype, name)

        if desc_en:
            print(f"   英文: {desc_en[:80]}{'...' if len(desc_en) > 80 else ''}")
            # 原地修改
            idx = id_to_idx[rid]
            resources[idx]["description"] = desc_en
            if not resources[idx].get("description_zh"):
                resources[idx]["description_zh"] = desc_zh
            success += 1
        else:
            print(f"   [SKIP] 翻译失败，保留原文")
            failed += 1

        # 避免触发速率限制
        if i < len(to_translate):
            time.sleep(0.3)

    # 保存结果
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(resources, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"[OK] 翻译完成：成功 {success} 个，失败 {failed} 个")
    print(f"[OK] 已保存到: {registry_path}")
    print(f"[INFO] 请重新运行 build_index.py 重建 FAISS 索引")
    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="为中文 description 批量生成英文版本")
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
        help="resources.json 路径",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅列出需要翻译的资源，不实际调用 API",
    )
    args = parser.parse_args()

    if not args.registry.exists():
        print(f"[ERR] 文件不存在: {args.registry}")
        sys.exit(1)

    enrich_descriptions(args.registry, dry_run=args.dry_run)
