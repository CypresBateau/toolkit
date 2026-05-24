"""
测试导入脚本 - 验证 resources.json 的生成

运行方式：
    python scripts/test_import.py
"""

import json
from pathlib import Path


def test_resources_json():
    """测试 resources.json 文件"""
    resources_file = Path("data/registry/resources.json")

    if not resources_file.exists():
        print("[ERR] resources.json 不存在，请先运行 import_from_gateway.py")
        return False

    print("[INFO] 读取 resources.json...")
    with open(resources_file, "r", encoding="utf-8") as f:
        resources = json.load(f)

    if not isinstance(resources, list):
        print("[ERR] resources.json 格式错误，应为数组")
        return False

    print(f"[OK] 共 {len(resources)} 个资源")

    # 统计资源类型
    type_counts = {}
    for res in resources:
        res_type = res.get("resource_type", "unknown")
        type_counts[res_type] = type_counts.get(res_type, 0) + 1

    print("\n[INFO] 资源类型统计:")
    for res_type, count in sorted(type_counts.items()):
        print(f"   {res_type}: {count}")

    # 统计 gateway_interface
    interface_counts = {}
    for res in resources:
        interface = res.get("gateway_interface", "unknown")
        interface_counts[interface] = interface_counts.get(interface, 0) + 1

    print("\n[INFO] Gateway 接口统计:")
    for interface, count in sorted(interface_counts.items()):
        print(f"   {interface}: {count}")

    # 检查必需字段
    print("\n[INFO] 检查必需字段...")
    required_fields = ["id", "resource_type", "name", "description", "gateway_tool_name", "gateway_interface"]

    missing_count = 0
    for i, res in enumerate(resources):
        missing = [field for field in required_fields if field not in res]
        if missing:
            print(f"   [WARN] 资源 {i} ({res.get('id', '?')}) 缺少字段: {missing}")
            missing_count += 1

    if missing_count == 0:
        print("   [OK] 所有资源都包含必需字段")
    else:
        print(f"   [WARN] {missing_count} 个资源缺少必需字段")

    # 显示示例资源
    print("\n[INFO] 示例资源:")
    for res_type in ["tool", "model", "skill"]:
        examples = [r for r in resources if r.get("resource_type") == res_type]
        if examples:
            example = examples[0]
            print(f"\n   {res_type} 示例:")
            print(f"      id: {example.get('id')}")
            print(f"      name: {example.get('name')}")
            print(f"      description: {example.get('description', '')[:80]}...")
            print(f"      gateway_tool_name: {example.get('gateway_tool_name')}")
            print(f"      gateway_interface: {example.get('gateway_interface')}")
            if example.get("function_name"):
                print(f"      function_name: {example.get('function_name')}")

    return True


if __name__ == "__main__":
    success = test_resources_json()
    if success:
        print("\n[OK] 测试通过")
    else:
        print("\n[ERR] 测试失败")
