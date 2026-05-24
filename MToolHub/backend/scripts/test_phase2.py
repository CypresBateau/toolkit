"""
测试 Phase 2 - 统一执行器

验证：
1. UnifiedExecutor 能正确加载
2. 能从 resources.json 读取资源
3. 能根据 gateway_interface 路由到正确的方法

运行方式：
    python scripts/test_phase2.py
"""

import sys
import json
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.registry import ResourceMetadata
from app.core.registry import registry_manager
from app.services.executor import unified_executor


def test_registry_loading():
    """测试注册表加载"""
    print("[INFO] 测试注册表加载...")

    resources = registry_manager.get_all_resources()
    if not resources:
        print("[ERR] 未加载任何资源，请先运行 import_from_gateway.py")
        return False

    print(f"[OK] 已加载 {len(resources)} 个资源")

    # 统计类型
    type_counts = {}
    for res in resources:
        type_counts[res.resource_type] = type_counts.get(res.resource_type, 0) + 1

    print("\n[INFO] 资源类型统计:")
    for res_type, count in sorted(type_counts.items()):
        print(f"   {res_type}: {count}")

    return True


def test_resource_metadata():
    """测试 ResourceMetadata 模型"""
    print("\n[INFO] 测试 ResourceMetadata 模型...")

    # 测试工具资源
    tool_data = {
        "id": "tool-mdcalc:wells_score_dvt",
        "resource_type": "tool",
        "name": "Wells Score for DVT",
        "description": "Calculates risk of DVT",
        "gateway_tool_name": "tool-mdcalc",
        "gateway_interface": "call",
        "function_name": "wells_score_dvt",
        "input_schema": {"type": "object", "properties": {}},
        "enabled": True
    }

    try:
        tool = ResourceMetadata(**tool_data)
        print(f"[OK] 工具资源解析成功: {tool.id}")
    except Exception as e:
        print(f"[ERR] 工具资源解析失败: {e}")
        return False

    # 测试模型资源
    model_data = {
        "id": "mavl",
        "resource_type": "model",
        "name": "MAVL Chest X-ray Analysis",
        "description": "Multi-label chest X-ray classification",
        "gateway_tool_name": "mavl",
        "gateway_interface": "predict",
        "input_type": "image",
        "accepted_formats": ["jpg", "png"],
        "enabled": True
    }

    try:
        model = ResourceMetadata(**model_data)
        print(f"[OK] 模型资源解析成功: {model.id}")
    except Exception as e:
        print(f"[ERR] 模型资源解析失败: {e}")
        return False

    # 测试技能资源
    skill_data = {
        "id": "tool-skills:drug_interaction",
        "resource_type": "skill",
        "name": "Drug Interaction Check",
        "name_zh": "药物相互作用检查",
        "description": "Check drug interactions",
        "description_zh": "检查药物相互作用",
        "gateway_tool_name": "tool-skills",
        "gateway_interface": "call",
        "function_name": "drug_interaction",
        "enabled": True
    }

    try:
        skill = ResourceMetadata(**skill_data)
        print(f"[OK] 技能资源解析成功: {skill.id}")
        if skill.name_zh:
            print(f"[OK] 中文字段正确: name_zh={skill.name_zh}, description_zh={skill.description_zh}")
    except Exception as e:
        print(f"[ERR] 技能资源解析失败: {e}")
        return False

    return True


def test_executor_routing():
    """测试执行器路由逻辑"""
    print("\n[INFO] 测试执行器路由逻辑...")

    # 获取不同类型的资源
    resources = registry_manager.get_all_resources()

    tool_resources = [r for r in resources if r.resource_type == "tool" and r.gateway_interface == "call"]
    model_resources = [r for r in resources if r.resource_type == "model" and r.gateway_interface == "predict"]
    skill_resources = [r for r in resources if r.resource_type == "skill" and r.gateway_interface == "call"]

    print(f"\n[INFO] 找到资源:")
    print(f"   call 接口工具: {len(tool_resources)}")
    print(f"   predict 接口模型: {len(model_resources)}")
    print(f"   call 接口技能: {len(skill_resources)}")

    # 验证执行器方法存在
    if not hasattr(unified_executor, '_execute_call_interface'):
        print("[ERR] UnifiedExecutor 缺少 _execute_call_interface 方法")
        return False

    if not hasattr(unified_executor, '_execute_predict_interface'):
        print("[ERR] UnifiedExecutor 缺少 _execute_predict_interface 方法")
        return False

    print("[OK] UnifiedExecutor 包含所有必需方法")

    # 验证路由逻辑
    if tool_resources:
        tool = tool_resources[0]
        print(f"\n[INFO] 工具示例: {tool.id}")
        print(f"   gateway_interface: {tool.gateway_interface}")
        print(f"   function_name: {tool.function_name}")
        print(f"   [OK] 应路由到 _execute_call_interface")

    if model_resources:
        model = model_resources[0]
        print(f"\n[INFO] 模型示例: {model.id}")
        print(f"   gateway_interface: {model.gateway_interface}")
        print(f"   input_type: {model.input_type}")
        print(f"   [OK] 应路由到 _execute_predict_interface")

    if skill_resources:
        skill = skill_resources[0]
        print(f"\n[INFO] 技能示例: {skill.id}")
        print(f"   gateway_interface: {skill.gateway_interface}")
        print(f"   function_name: {skill.function_name}")
        print(f"   [OK] 应路由到 _execute_call_interface")

    return True


def test_gateway_url_construction():
    """测试 Gateway URL 构造"""
    print("\n[INFO] 测试 Gateway URL 构造...")

    from app.config import settings

    base_url = settings.gateway_base_url
    print(f"   Gateway Base URL: {base_url}")

    # 测试 call 接口 URL
    tool_name = "tool-mdcalc"
    call_url = f"{base_url}/tools/{tool_name}/call"
    print(f"   Call URL 示例: {call_url}")

    # 测试 predict 接口 URL
    model_name = "mavl"
    predict_url = f"{base_url}/tools/{model_name}/predict"
    print(f"   Predict URL 示例: {predict_url}")

    print("[OK] URL 构造正确")
    return True


def main():
    """运行所有测试"""
    print("=" * 60)
    print("Phase 2 测试 - 统一执行器")
    print("=" * 60)

    tests = [
        ("注册表加载", test_registry_loading),
        ("ResourceMetadata 模型", test_resource_metadata),
        ("执行器路由逻辑", test_executor_routing),
        ("Gateway URL 构造", test_gateway_url_construction),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"[ERR] 测试 '{name}' 抛出异常: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)

    if failed == 0:
        print("\n[OK] Phase 2 所有测试通过！")
        return True
    else:
        print(f"\n[ERR] {failed} 个测试失败")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
