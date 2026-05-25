"""
toolkit_metrics.py - 工具库使用指标计算模块

计算 MToolHub 工具库相关的评估指标，包括：
- 工具使用率
- 平均每病例工具数
- 工具选择准确率
- 执行成功率
- 响应时间统计
- Token 使用统计
"""

import json
from typing import List, Dict, Any
from pathlib import Path


def calculate_toolkit_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    计算工具库使用相关指标

    Args:
        results: 推理结果列表，每个元素包含 case_id, tools_used, response_time 等字段

    Returns:
        工具库指标字典
    """
    # 过滤掉失败的病例
    valid_results = [r for r in results if "error" not in r]
    total_cases = len(valid_results)

    if total_cases == 0:
        return {
            "total_cases": 0,
            "tool_usage_rate": 0.0,
            "avg_tools_per_case": 0.0,
            "execution_success_rate": 0.0,
            "avg_response_time": 0.0,
            "total_tokens": 0
        }

    # 1. 工具使用率（使用了至少一个工具的病例比例）
    cases_with_tools = [r for r in valid_results if r.get("tools_used") and len(r["tools_used"]) > 0]
    tool_usage_rate = len(cases_with_tools) / total_cases

    # 2. 平均每病例工具数
    total_tools_used = sum(len(r.get("tools_used", [])) for r in valid_results)
    avg_tools_per_case = total_tools_used / total_cases

    # 3. 执行成功率（所有工具调用中成功的比例）
    all_tool_calls = []
    for r in valid_results:
        all_tool_calls.extend(r.get("tools_used", []))

    if all_tool_calls:
        successful_calls = [t for t in all_tool_calls if t.get("success", False)]
        execution_success_rate = len(successful_calls) / len(all_tool_calls)
    else:
        execution_success_rate = 0.0

    # 4. 平均响应时间
    avg_response_time = sum(r.get("response_time", 0) for r in valid_results) / total_cases

    # 5. 总 tokens
    total_tokens = sum(r.get("tokens_used", 0) for r in valid_results)

    # 6. 工具使用分布（统计每个工具被调用的次数）
    tool_usage_distribution = {}
    for tool_call in all_tool_calls:
        resource_id = tool_call.get("resource_id", "unknown")
        tool_usage_distribution[resource_id] = tool_usage_distribution.get(resource_id, 0) + 1

    # 按使用次数排序
    tool_usage_distribution = dict(sorted(
        tool_usage_distribution.items(),
        key=lambda x: x[1],
        reverse=True
    ))

    return {
        "total_cases": total_cases,
        "tool_usage_rate": tool_usage_rate,
        "avg_tools_per_case": avg_tools_per_case,
        "execution_success_rate": execution_success_rate,
        "avg_response_time": avg_response_time,
        "total_tokens": total_tokens,
        "tool_usage_distribution": tool_usage_distribution,
        "top_10_tools": dict(list(tool_usage_distribution.items())[:10])
    }


def calculate_accuracy_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    计算准确率相关指标

    Args:
        results: 推理结果列表

    Returns:
        准确率指标字典
    """
    valid_results = [r for r in results if "error" not in r]
    total_cases = len(valid_results)

    if total_cases == 0:
        return {
            "total_cases": 0,
            "correct_cases": 0,
            "accuracy": 0.0
        }

    # 简单的字符串匹配准确率
    correct_cases = len([r for r in valid_results if r.get("correct", False)])
    accuracy = correct_cases / total_cases

    return {
        "total_cases": total_cases,
        "correct_cases": correct_cases,
        "accuracy": accuracy
    }


def calculate_cost_metrics(results: List[Dict[str, Any]], model: str = "claude-sonnet-4") -> Dict[str, Any]:
    """
    计算成本相关指标

    Args:
        results: 推理结果列表
        model: 模型名称（用于估算成本）

    Returns:
        成本指标字典
    """
    valid_results = [r for r in results if "error" not in r]
    total_tokens = sum(r.get("tokens_used", 0) for r in valid_results)

    # Claude Sonnet 4 定价（2026 年 5 月估算）
    # Input: $3 / 1M tokens
    # Output: $15 / 1M tokens
    # 假设 input:output = 1:1
    if "sonnet" in model.lower():
        input_cost_per_1m = 3.0
        output_cost_per_1m = 15.0
        avg_cost_per_1m = (input_cost_per_1m + output_cost_per_1m) / 2  # 简化假设
        estimated_cost = (total_tokens / 1_000_000) * avg_cost_per_1m
    elif "opus" in model.lower():
        # Opus 更贵
        avg_cost_per_1m = 30.0
        estimated_cost = (total_tokens / 1_000_000) * avg_cost_per_1m
    else:
        estimated_cost = 0.0

    return {
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(estimated_cost, 2),
        "cost_per_case_usd": round(estimated_cost / len(valid_results), 4) if valid_results else 0.0
    }


def generate_metrics_report(result_file: str, output_file: str = None) -> Dict[str, Any]:
    """
    从结果文件生成完整的指标报告

    Args:
        result_file: 推理结果 JSON 文件路径
        output_file: 输出报告文件路径（可选）

    Returns:
        完整指标字典
    """
    # 加载结果
    with open(result_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    results = data.get("results", [])
    config = data.get("config", {})

    # 计算各类指标
    toolkit_metrics = calculate_toolkit_metrics(results)
    accuracy_metrics = calculate_accuracy_metrics(results)
    cost_metrics = calculate_cost_metrics(results, model=config.get("llm_model", "claude-sonnet-4"))

    # 合并指标
    report = {
        "config": config,
        "accuracy": accuracy_metrics,
        "toolkit": toolkit_metrics,
        "cost": cost_metrics
    }

    # 保存报告
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"[OK] 指标报告已保存到: {output_file}")

    return report


def print_metrics_summary(metrics: Dict[str, Any]):
    """
    打印指标摘要（格式化输出）

    Args:
        metrics: 指标字典
    """
    print("\n" + "="*60)
    print("指标摘要")
    print("="*60)

    # 配置信息
    config = metrics.get("config", {})
    print(f"\n[配置]")
    print(f"  模式: {config.get('mode', 'unknown')}")
    print(f"  模型: {config.get('llm_model', 'unknown')}")
    print(f"  工具库: {'启用' if config.get('mtoolhub_enabled') else '禁用'}")
    if config.get('mtoolhub_enabled'):
        print(f"  搜索 top-k: {config.get('search_top_k', 'N/A')}")

    # 准确率
    accuracy = metrics.get("accuracy", {})
    print(f"\n[准确率]")
    print(f"  总病例数: {accuracy.get('total_cases', 0)}")
    print(f"  正确病例数: {accuracy.get('correct_cases', 0)}")
    print(f"  准确率: {accuracy.get('accuracy', 0):.2%}")

    # 工具库使用
    toolkit = metrics.get("toolkit", {})
    print(f"\n[工具库使用]")
    print(f"  工具使用率: {toolkit.get('tool_usage_rate', 0):.2%}")
    print(f"  平均每病例工具数: {toolkit.get('avg_tools_per_case', 0):.2f}")
    print(f"  执行成功率: {toolkit.get('execution_success_rate', 0):.2%}")
    print(f"  平均响应时间: {toolkit.get('avg_response_time', 0):.2f}s")

    # Top 工具
    top_tools = toolkit.get("top_10_tools", {})
    if top_tools:
        print(f"\n[Top 10 最常用工具]")
        for i, (tool_id, count) in enumerate(top_tools.items(), 1):
            print(f"  {i}. {tool_id}: {count} 次")

    # 成本
    cost = metrics.get("cost", {})
    print(f"\n[成本]")
    print(f"  总 tokens: {cost.get('total_tokens', 0):,}")
    print(f"  估算成本: ${cost.get('estimated_cost_usd', 0):.2f}")
    print(f"  每病例成本: ${cost.get('cost_per_case_usd', 0):.4f}")

    print("\n" + "="*60 + "\n")


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("使用方式: python toolkit_metrics.py <result_file.json> [output_file.json]")
        sys.exit(1)

    result_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    # 生成报告
    metrics = generate_metrics_report(result_file, output_file)

    # 打印摘要
    print_metrics_summary(metrics)
