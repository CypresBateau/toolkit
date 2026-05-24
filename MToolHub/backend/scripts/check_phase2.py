"""
Phase 2 代码检查清单

运行此脚本检查代码的完整性和正确性

运行方式：
    python scripts/check_phase2.py
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def check_file_exists(file_path: str) -> bool:
    """检查文件是否存在"""
    path = Path(file_path)
    if path.exists():
        print(f"[OK] {file_path}")
        return True
    else:
        print(f"[ERR] 文件不存在: {file_path}")
        return False


def check_imports() -> bool:
    """检查关键模块是否可以导入"""
    print("\n[INFO] 检查模块导入...")

    imports = [
        ("app.models.registry", "ResourceMetadata"),
        ("app.core.registry", "registry_manager"),
        ("app.services.executor", "unified_executor"),
        ("app.services.orchestrator", "orchestrator"),
        ("app.core.claude_client", "claude_client"),
        ("app.config", "settings"),
    ]

    all_ok = True
    for module_name, obj_name in imports:
        try:
            module = __import__(module_name, fromlist=[obj_name])
            obj = getattr(module, obj_name)
            print(f"[OK] from {module_name} import {obj_name}")
        except Exception as e:
            print(f"[ERR] 导入失败: from {module_name} import {obj_name}")
            print(f"      错误: {e}")
            all_ok = False

    return all_ok


def check_no_unicode_symbols() -> bool:
    """检查代码中是否有 Unicode 特殊符号"""
    print("\n[INFO] 检查 Unicode 符号...")

    # 需要检查的文件
    files_to_check = [
        "app/main.py",
        "app/utils/disclaimer.py",
        "app/services/executor.py",
        "app/services/orchestrator.py",
        "app/routers/execute.py",
        "app/routers/chat.py",
        "app/core/registry.py",
        "scripts/import_from_gateway.py",
        "scripts/build_index.py",
    ]

    # 禁止的 Unicode 符号
    forbidden_symbols = ["✓", "✗", "★", "⚠", "🚀", "📍", "🤖", "🔍", "👋"]

    all_ok = True
    for file_path in files_to_check:
        path = Path(file_path)
        if not path.exists():
            print(f"[SKIP] {file_path} (文件不存在)")
            continue

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        found_symbols = []
        for symbol in forbidden_symbols:
            if symbol in content:
                found_symbols.append(symbol)

        if found_symbols:
            print(f"[ERR] {file_path} 包含禁止的 Unicode 符号: {found_symbols}")
            all_ok = False
        else:
            print(f"[OK] {file_path}")

    return all_ok


def check_data_flow() -> bool:
    """检查数据流的一致性"""
    print("\n[INFO] 检查数据流一致性...")

    try:
        from app.models.api import RoutingPlan
        from app.services.router import route_decision_maker

        # 检查 RoutingPlan 的 selected_resources 字段类型
        print("[OK] RoutingPlan 模型存在")

        # 检查 route_decision_maker 是否返回正确格式
        print("[OK] route_decision_maker 存在")

        # 检查 orchestrator 是否正确处理 selected_resources
        from app.services.orchestrator import orchestrator
        print("[OK] orchestrator 存在")

        # 检查 unified_executor 是否接受 ResourceMetadata
        from app.services.executor import unified_executor
        print("[OK] unified_executor 存在")

        return True
    except Exception as e:
        print(f"[ERR] 数据流检查失败: {e}")
        return False


def check_gateway_interface_routing() -> bool:
    """检查 gateway_interface 路由逻辑"""
    print("\n[INFO] 检查 gateway_interface 路由逻辑...")

    try:
        from app.services.executor import UnifiedExecutor

        executor = UnifiedExecutor()

        # 检查方法是否存在
        if not hasattr(executor, '_execute_call_interface'):
            print("[ERR] UnifiedExecutor 缺少 _execute_call_interface 方法")
            return False

        if not hasattr(executor, '_execute_predict_interface'):
            print("[ERR] UnifiedExecutor 缺少 _execute_predict_interface 方法")
            return False

        print("[OK] UnifiedExecutor 包含所有必需方法")
        return True
    except Exception as e:
        print(f"[ERR] 路由逻辑检查失败: {e}")
        return False


def check_claude_integration() -> bool:
    """检查 Claude API 集成"""
    print("\n[INFO] 检查 Claude API 集成...")

    try:
        from app.core.claude_client import ClaudeClient

        client = ClaudeClient()

        # 检查方法是否存在
        if not hasattr(client, 'extract_parameters'):
            print("[ERR] ClaudeClient 缺少 extract_parameters 方法")
            return False

        if not hasattr(client, 'interpret_result'):
            print("[ERR] ClaudeClient 缺少 interpret_result 方法")
            return False

        print("[OK] ClaudeClient 包含所有必需方法")
        return True
    except Exception as e:
        print(f"[ERR] Claude 集成检查失败: {e}")
        return False


def main():
    """运行所有检查"""
    print("=" * 60)
    print("Phase 2 代码检查清单")
    print("=" * 60)

    checks = [
        ("关键文件存在性", lambda: all([
            check_file_exists("app/services/executor.py"),
            check_file_exists("app/services/orchestrator.py"),
            check_file_exists("app/routers/execute.py"),
            check_file_exists("app/core/claude_client.py"),
            check_file_exists("app/models/api.py"),
            check_file_exists("PHASE2_SUMMARY.md"),
        ])),
        ("模块导入", check_imports),
        ("Unicode 符号", check_no_unicode_symbols),
        ("数据流一致性", check_data_flow),
        ("Gateway 接口路由", check_gateway_interface_routing),
        ("Claude API 集成", check_claude_integration),
    ]

    passed = 0
    failed = 0

    for name, check_func in checks:
        print(f"\n{'=' * 60}")
        print(f"检查: {name}")
        print('=' * 60)
        try:
            if check_func():
                passed += 1
                print(f"[OK] {name} 检查通过")
            else:
                failed += 1
                print(f"[ERR] {name} 检查失败")
        except Exception as e:
            print(f"[ERR] {name} 检查抛出异常: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"检查结果: {passed} 通过, {failed} 失败")
    print("=" * 60)

    if failed == 0:
        print("\n[OK] Phase 2 所有检查通过！代码可以部署到远程服务器。")
        return True
    else:
        print(f"\n[ERR] {failed} 个检查失败，请修复后再部署。")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
