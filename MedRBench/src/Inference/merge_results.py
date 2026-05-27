"""
merge_results.py - 合并推理结果

将 1_turn_{model}/log_{case_id}.json 格式的每个病例文件
合并为评估脚本 1turn_diagnose_accuracy.py 所需的格式：
{
  "case_id": {
    "model_name": {
      "output_messages": [...],
      "messages": [...]
    }
  }
}

用法：
  python src/Inference/merge_results.py \
    --input-dir 1_turn_deepseek-r1 \
    --model-name deepseek-r1 \
    --output results/deepseek-r1_merged.json
"""

import os
import json
import argparse
from pathlib import Path


def merge_results(input_dir: str, model_name: str, output_path: str):
    input_path = Path(input_dir)
    if not input_path.exists():
        print(f"[ERR] 输入目录不存在: {input_dir}")
        return

    log_files = sorted(input_path.glob("log_*.json"))
    if not log_files:
        print(f"[ERR] 目录中没有找到 log_*.json 文件: {input_dir}")
        return

    merged = {}
    skipped = 0

    for log_file in log_files:
        # 从文件名提取 case_id：log_PMC11625232.json -> PMC11625232
        case_id = log_file.stem.replace("log_", "", 1)

        with open(log_file, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"[SKIP] 解析失败 {log_file.name}: {e}")
                skipped += 1
                continue

        output_messages = data.get("output_messages", [])
        if not output_messages:
            print(f"[SKIP] output_messages 为空: {log_file.name}")
            skipped += 1
            continue

        # 评估脚本读取 messages[-1]['content']['answer']
        # 同时保留 output_messages 和 messages 两个字段确保兼容
        merged[case_id] = {
            model_name: {
                "output_messages": output_messages,
                "messages": output_messages,
            }
        }

        # 保留工具使用信息（如果有）
        if "tools_used" in data:
            merged[case_id][model_name]["tools_used"] = data["tools_used"]

    # 保存合并结果
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"[OK] 合并完成：{len(merged)} 个病例 -> {output_path}")
    if skipped:
        print(f"[WARN] 跳过 {skipped} 个文件")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="合并推理结果为评估脚本所需格式")
    parser.add_argument("--input-dir", type=str, required=True,
                        help="推理结果目录，如 1_turn_deepseek-r1")
    parser.add_argument("--model-name", type=str, required=True,
                        help="模型名称，如 deepseek-r1（需在评估脚本 choices 列表中）")
    parser.add_argument("--output", type=str, required=True,
                        help="输出文件路径，如 results/deepseek-r1_merged.json")

    args = parser.parse_args()
    merge_results(args.input_dir, args.model_name, args.output)
