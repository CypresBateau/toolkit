"""
验证统一数据模型 - 测试 ResourceMetadata 是否能正确解析不同格式的数据

运行方式：
    python scripts/validate_model.py
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.models.registry import ResourceMetadata


def test_tool_resource():
    """测试工具资源"""
    print("[INFO] 测试工具资源...")

    tool_data = {
        "id": "tool-mdcalc:wells_score_dvt",
        "resource_type": "tool",
        "name": "Wells Score for DVT",
        "description": "Calculates risk of deep vein thrombosis",
        "gateway_tool_name": "tool-mdcalc",
        "gateway_interface": "call",
        "function_name": "wells_score_dvt",
        "input_schema": {"type": "object"},
        "category": "mdcalc",
        "enabled": True
    }

    try:
        resource = ResourceMetadata(**tool_data)
        print(f"   [OK] 工具资源解析成功: {resource.id}")
        return True
    except Exception as e:
        print(f"   [ERR] 工具资源解析失败: {e}")
        return False


def test_model_resource():
    """测试模型资源"""
    print("[INFO] 测试模型资源...")

    model_data = {
        "id": "mavl",
        "resource_type": "model",
        "name": "MAVL Chest X-ray Analysis",
        "description": "Multi-label chest X-ray classification model",
        "gateway_tool_name": "mavl",
        "gateway_interface": "predict",
        "input_type": "image",
        "accepted_formats": ["jpg", "png"],
        "category": "model",
        "enabled": True
    }

    try:
        resource = ResourceMetadata(**model_data)
        print(f"   [OK] 模型资源解析成功: {resource.id}")
        return True
    except Exception as e:
        print(f"   [ERR] 模型资源解析失败: {e}")
        return False


def test_skill_resource():
    """测试技能资源"""
    print("[INFO] 测试技能资源...")

    skill_data = {
        "id": "tool-skills:drug_interaction",
        "resource_type": "skill",
        "name": "药物相互作用检查",
        "name_zh": "药物相互作用检查",
        "description": "Check drug interactions using openFDA API",
        "description_zh": "通过 openFDA API 检查药物相互作用",
        "gateway_tool_name": "tool-skills",
        "gateway_interface": "call",
        "function_name": "drug_interaction",
        "skill_type": "executable",
        "category": "skill",
        "enabled": True
    }

    try:
        resource = ResourceMetadata(**skill_data)
        print(f"   [OK] 技能资源解析成功: {resource.id}")
        return True
    except Exception as e:
        print(f"   [ERR] 技能资源解析失败: {e}")
        return False


def test_chinese_detection():
    """测试中文检测"""
    print("[INFO] 测试中文字段...")

    # 中文描述
    data_with_chinese = {
        "id": "test:chinese",
        "resource_type": "tool",
        "name": "测试工具",
        "name_zh": "测试工具",
        "description": "这是一个测试工具",
        "description_zh": "这是一个测试工具",
        "gateway_tool_name": "test",
        "gateway_interface": "call",
        "enabled": True
    }

    try:
        resource = ResourceMetadata(**data_with_chinese)
        if resource.name_zh and resource.description_zh:
            print(f"   [OK] 中文字段正确: name_zh={resource.name_zh}, description_zh={resource.description_zh}")
            return True
        else:
            print(f"   [WARN] 中文字段缺失")
            return False
    except Exception as e:
        print(f"   [ERR] 中文资源解析失败: {e}")
        return False


def main():
    """主函数"""
    print("="*60)
    print("统一数据模型验证")
    print("="*60)
    print()

    results = []
    results.append(test_tool_resource())
    results.append(test_model_resource())
    results.append(test_skill_resource())
    results.append(test_chinese_detection())

    print()
    print("="*60)
    if all(results):
        print("[OK] 所有测试通过")
    else:
        print(f"[ERR] {results.count(False)} 个测试失败")
    print("="*60)


if __name__ == "__main__":
    main()
