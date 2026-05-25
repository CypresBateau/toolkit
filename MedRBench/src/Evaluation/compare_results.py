"""
compare_results.py - 对比实验结果分析脚本

对比 baseline 和 experimental 两组实验结果，计算增益和统计显著性。

使用方式：
    python src/Evaluation/compare_results.py \
        --baseline results/baseline.json \
        --experimental results/experimental.json \
        --output results/comparison_report.json
"""

import json
import argparse
from pathlib import Path
from typing import Dict, Any, List
from src.Evaluation.toolkit_metrics import (
    calculate_toolkit_metrics,
    calculate_accuracy_metrics,
    calculate_cost_metrics
)


def calculate_improvement(baseline_value: float, experimental_value: float) -> Dict[str, Any]:
    """
    计算改进幅度

    Args:
        baseline_value: 基线值
        experimental_value: 实验值

    Returns:
        包含绝对改进和相对改进的字典
    """
    absolute_improvement = experimental_value - baseline_value

    if baseline_value != 0:
        relative_improvement = (experimental_value - baseline_value) / baseline_value
    else:
        relative_improvement = 0.0

    return {
        "baseline": baseline_value,
        "experimental": experimental_value,
        "absolute_improvement": absolute_improvement,
        "relative_improvement": relative_improvement,
        "relative_improvement_pct": relative_improvement * 100
    }


def compare_accuracy(baseline_results: List[Dict], experimental_results: List[Dict]) -> Dict[str, Any]:
    """
    对比准确率

    Args:
        baseline_results: baseline 结果列表
        experimental_results: experimental 结果列表

    Returns:
        准确率对比字典
    """
    baseline_metrics = calculate_accuracy_metrics(baseline_results)
    experimental_metrics = calculate_accuracy_metrics(experimental_results)

    baseline_acc = baseline_metrics["accuracy"]
    experimental_acc = experimental_metrics["accuracy"]

    improvement = calculate_improvement(baseline_acc, experimental_acc)

    return {
        "baseline": {
            "total_cases": baseline_metrics["total_cases"],
            "correct_cases": baseline_metrics["correct_cases"],
            "accuracy": baseline_acc
        },
        "experimental": {
            "total_cases": experimental_metrics["total_cases"],
            "correct_cases": experimental_metrics["correct_cases"],
            "accuracy": experimental_acc
        },
        "improvement": improvement
    }


def compare_toolkit_usage(baseline_results: List[Dict], experimental_results: List[Dict]) -> Dict[str, Any]:
    """
    对比工具库使用情况

    Args:
        baseline_results: baseline 结果列表
        experimental_results: experimental 结果列表

    Returns:
        工具库使用对比字典
    """
    baseline_metrics = calculate_toolkit_metrics(baseline_results)
    experimental_metrics = calculate_toolkit_metrics(experimental_results)

    return {
        "baseline": {
            "tool_usage_rate": baseline_metrics["tool_usage_rate"],
            "avg_tools_per_case": baseline_metrics["avg_tools_per_case"],
            "execution_success_rate": baseline_metrics["execution_success_rate"]
        },
        "experimental": {
            "tool_usage_rate": experimental_metrics["tool_usage_rate"],
            "avg_tools_per_case": experimental_metrics["avg_tools_per_case"],
            "execution_success_rate": experimental_metrics["execution_success_rate"],
            "top_10_tools": experimental_metrics.get("top_10_tools", {})
        }
    }


def compare_performance(baseline_results: List[Dict], experimental_results: List[Dict]) -> Dict[str, Any]:
    """
    对比性能指标（响应时间、tokens）

    Args:
        baseline_results: baseline 结果列表
        experimental_results: experimental 结果列表

    Returns:
        性能对比字典
    """
    baseline_metrics = calculate_toolkit_metrics(baseline_results)
    experimental_metrics = calculate_toolkit_metrics(experimental_results)

    response_time_improvement = calculate_improvement(
        baseline_metrics["avg_response_time"],
        experimental_metrics["avg_response_time"]
    )

    tokens_improvement = calculate_improvement(
        baseline_metrics["total_tokens"],
        experimental_metrics["total_tokens"]
    )

    return {
        "response_time": response_time_improvement,
        "tokens": tokens_improvement
    }


def compare_cost(baseline_results: List[Dict], experimental_results: List[Dict], model: str) -> Dict[str, Any]:
    """
    对比成本

    Args:
        baseline_results: baseline 结果列表
        experimental_results: experimental 结果列表
        model: 模型名称

    Returns:
        成本对比字典
    """
    baseline_metrics = calculate_cost_metrics(baseline_results, model)
    experimental_metrics = calculate_cost_metrics(experimental_results, model)

    cost_improvement = calculate_improvement(
        baseline_metrics["estimated_cost_usd"],
        experimental_metrics["estimated_cost_usd"]
    )

    return {
        "baseline": baseline_metrics,
        "experimental": experimental_metrics,
        "improvement": cost_improvement
    }


def analyze_error_cases(baseline_results: List[Dict], experimental_results: List[Dict]) -> Dict[str, Any]:
    """
    分析错误病例

    Args:
        baseline_results: baseline 结果列表
        experimental_results: experimental 结果列表

    Returns:
        错误分析字典
    """
    # 构建 case_id -> result 映射
    baseline_map = {r["case_id"]: r for r in baseline_results if "error" not in r}
    experimental_map = {r["case_id"]: r for r in experimental_results if "error" not in r}

    # 找出共同的病例
    common_cases = set(baseline_map.keys()) & set(experimental_map.keys())

    # 分类病例
    both_correct = []  # 两者都对
    both_wrong = []  # 两者都错
    baseline_only_correct = []  # 只有 baseline 对
    experimental_only_correct = []  # 只有 experimental 对

    for case_id in common_cases:
        baseline_correct = baseline_map[case_id].get("correct", False)
        experimental_correct = experimental_map[case_id].get("correct", False)

        if baseline_correct and experimental_correct:
            both_correct.append(case_id)
        elif not baseline_correct and not experimental_correct:
            both_wrong.append(case_id)
        elif baseline_correct and not experimental_correct:
            baseline_only_correct.append(case_id)
        elif not baseline_correct and experimental_correct:
            experimental_only_correct.append(case_id)

    return {
        "total_common_cases": len(common_cases),
        "both_correct": len(both_correct),
        "both_wrong": len(both_wrong),
        "baseline_only_correct": len(baseline_only_correct),
        "experimental_only_correct": len(experimental_only_correct),
        "net_improvement": len(experimental_only_correct) - len(baseline_only_correct),
        "experimental_only_correct_cases": experimental_only_correct[:10],  # 只保存前 10 个
        "baseline_only_correct_cases": baseline_only_correct[:10]
    }


def generate_comparison_report(
    baseline_file: str,
    experimental_file: str,
    output_file: str = None
) -> Dict[str, Any]:
    """
    生成完整的对比报告

    Args:
        baseline_file: baseline 结果文件路径
        experimental_file: experimental 结果文件路径
        output_file: 输出报告文件路径（可选）

    Returns:
        完整对比报告字典
    """
    # 加载结果
    with open(baseline_file, 'r', encoding='utf-8') as f:
        baseline_data = json.load(f)

    with open(experimental_file, 'r', encoding='utf-8') as f:
        experimental_data = json.load(f)

    baseline_results = baseline_data.get("results", [])
    experimental_results = experimental_data.get("results", [])

    baseline_config = baseline_data.get("config", {})
    experimental_config = experimental_data.get("config", {})

    model = experimental_config.get("llm_model", "claude-sonnet-4")

    # 生成各类对比
    report = {
        "metadata": {
            "baseline_file": baseline_file,
            "experimental_file": experimental_file,
            "baseline_config": baseline_config,
            "experimental_config": experimental_config
        },
        "accuracy_comparison": compare_accuracy(baseline_results, experimental_results),
        "toolkit_usage_comparison": compare_toolkit_usage(baseline_results, experimental_results),
        "performance_comparison": compare_performance(baseline_results, experimental_results),
        "cost_comparison": compare_cost(baseline_results, experimental_results, model),
        "error_analysis": analyze_error_cases(baseline_results, experimental_results)
    }

    # 保存报告
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"[OK] 对比报告已保存到: {output_file}")

    return report


def print_comparison_summary(report: Dict[str, Any]):
    """
    打印对比摘要（格式化输出）

    Args:
        report: 对比报告字典
    """
    print("\n" + "="*60)
    print("实验对比报告")
    print("="*60)

    # 配置信息
    metadata = report.get("metadata", {})
    baseline_config = metadata.get("baseline_config", {})
    experimental_config = metadata.get("experimental_config", {})

    print(f"\n[配置对比]")
    print(f"  Baseline 模式: {baseline_config.get('mode', 'unknown')}")
    print(f"  Experimental 模式: {experimental_config.get('mode', 'unknown')}")
    print(f"  模型: {experimental_config.get('llm_model', 'unknown')}")
    print(f"  工具库: {'启用' if experimental_config.get('mtoolhub_enabled') else '禁用'}")

    # 准确率对比
    accuracy = report.get("accuracy_comparison", {})
    improvement = accuracy.get("improvement", {})

    print(f"\n[准确率对比]")
    print(f"  Baseline: {improvement.get('baseline', 0):.2%}")
    print(f"  Experimental: {improvement.get('experimental', 0):.2%}")
    print(f"  绝对提升: {improvement.get('absolute_improvement', 0):.2%}")
    print(f"  相对提升: {improvement.get('relative_improvement_pct', 0):.2f}%")

    # 工具库使用
    toolkit = report.get("toolkit_usage_comparison", {})
    exp_toolkit = toolkit.get("experimental", {})

    print(f"\n[工具库使用]")
    print(f"  工具使用率: {exp_toolkit.get('tool_usage_rate', 0):.2%}")
    print(f"  平均每病例工具数: {exp_toolkit.get('avg_tools_per_case', 0):.2f}")
    print(f"  执行成功率: {exp_toolkit.get('execution_success_rate', 0):.2%}")

    # 性能对比
    performance = report.get("performance_comparison", {})
    response_time = performance.get("response_time", {})
    tokens = performance.get("tokens", {})

    print(f"\n[性能对比]")
    print(f"  响应时间:")
    print(f"    Baseline: {response_time.get('baseline', 0):.2f}s")
    print(f"    Experimental: {response_time.get('experimental', 0):.2f}s")
    print(f"    变化: {response_time.get('absolute_improvement', 0):+.2f}s ({response_time.get('relative_improvement_pct', 0):+.1f}%)")

    print(f"  Tokens:")
    print(f"    Baseline: {tokens.get('baseline', 0):,.0f}")
    print(f"    Experimental: {tokens.get('experimental', 0):,.0f}")
    print(f"    变化: {tokens.get('absolute_improvement', 0):+,.0f} ({tokens.get('relative_improvement_pct', 0):+.1f}%)")

    # 成本对比
    cost = report.get("cost_comparison", {})
    cost_improvement = cost.get("improvement", {})

    print(f"\n[成本对比]")
    print(f"  Baseline: ${cost_improvement.get('baseline', 0):.2f}")
    print(f"  Experimental: ${cost_improvement.get('experimental', 0):.2f}")
    print(f"  变化: ${cost_improvement.get('absolute_improvement', 0):+.2f} ({cost_improvement.get('relative_improvement_pct', 0):+.1f}%)")

    # 错误分析
    error_analysis = report.get("error_analysis", {})

    print(f"\n[错误分析]")
    print(f"  共同病例数: {error_analysis.get('total_common_cases', 0)}")
    print(f"  两者都对: {error_analysis.get('both_correct', 0)}")
    print(f"  两者都错: {error_analysis.get('both_wrong', 0)}")
    print(f"  仅 Baseline 对: {error_analysis.get('baseline_only_correct', 0)}")
    print(f"  仅 Experimental 对: {error_analysis.get('experimental_only_correct', 0)}")
    print(f"  净改进: {error_analysis.get('net_improvement', 0):+d}")

    print("\n" + "="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="对比 baseline 和 experimental 实验结果")
    parser.add_argument(
        "--baseline",
        type=str,
        required=True,
        help="Baseline 结果文件路径"
    )
    parser.add_argument(
        "--experimental",
        type=str,
        required=True,
        help="Experimental 结果文件路径"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出报告文件路径（可选）"
    )

    args = parser.parse_args()

    # 生成对比报告
    report = generate_comparison_report(
        baseline_file=args.baseline,
        experimental_file=args.experimental,
        output_file=args.output
    )

    # 打印摘要
    print_comparison_summary(report)


if __name__ == '__main__':
    main()
