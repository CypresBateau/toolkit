"""
one_turn_claude.py - 单轮诊断推理脚本（Claude + MToolHub 版本）

支持两种模式：
- baseline: LLM 裸跑，不提供任何工具
- experimental: LLM + MToolHub 工具库

支持两种 LLM provider：
- anthropic  : 直接调用 Anthropic API（需要 ANTHROPIC_API_KEY）
- openrouter : 通过 OpenRouter 调用（需要 OPENROUTER_API_KEY）
               使用 OpenAI 兼容接口，工具调用格式自动转换

使用方式：
    python src/Inference/one_turn_claude.py --config configs/experiment_config.yaml --mode baseline --output results/baseline.json
    python src/Inference/one_turn_claude.py --config configs/experiment_config.yaml --mode experimental --output results/experimental.json
"""

import os
import sys
import json
import argparse
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from tqdm import tqdm

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.Adapters.toolkit_adapter import ToolkitAdapter, load_config, LLMConfig


# ======================
# 配置常量
# ======================

DATA_PATH = 'data/MedRBench/diagnosis_957_cases_with_rare_disease_491.json'
SYSTEM_PROMPT = """You are a professional doctor with expertise in clinical diagnosis.

Your task is to analyze the patient's information and provide a diagnosis.

Please follow these steps:
1. Review the patient's demographics, symptoms, and test results
2. If relevant clinical tools are available, use them to calculate scores or perform assessments
3. Based on all available information, provide your diagnosis

Format your response as:
### Diagnosis: [Your diagnosis]
### Reasoning: [Your clinical reasoning]
### Confidence: [High/Medium/Low]
"""


# ======================
# LLM 客户端工厂
# ======================

def build_llm_client(llm_config: LLMConfig):
    """
    根据 provider 构建对应的 LLM 客户端。

    - anthropic        : 返回 anthropic.Anthropic 实例
    - openrouter       : 返回 openai.OpenAI 实例（指向 OpenRouter 接口）
    - openai_compatible: 返回 openai.OpenAI 实例（指向自定义接口）
    """
    provider = llm_config.provider

    # 读取 API Key
    key_env = llm_config.api_key_env or {
        "anthropic": "ANTHROPIC_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "openai_compatible": "OPENAI_API_KEY",
    }.get(provider, "OPENAI_API_KEY")

    api_key = os.environ.get(key_env)
    if not api_key:
        raise ValueError(f"请设置环境变量 {key_env}（provider={provider}）")

    if provider == "anthropic":
        from anthropic import Anthropic
        return Anthropic(api_key=api_key)

    elif provider in ("openrouter", "openai_compatible"):
        from openai import OpenAI
        base_url = llm_config.api_base_url or "https://openrouter.ai/api/v1"
        extra_headers = {}
        if provider == "openrouter":
            # OpenRouter 推荐携带这两个 header
            extra_headers["HTTP-Referer"] = "https://github.com/MedRBench"
            extra_headers["X-Title"] = "MedRBench-MToolHub"
        return OpenAI(api_key=api_key, base_url=base_url, default_headers=extra_headers)

    else:
        raise ValueError(f"不支持的 provider: {provider}，可选值: anthropic / openrouter / openai_compatible")


def call_llm(client, llm_config: LLMConfig, messages: List[Dict], tools: List[Dict], system_prompt: str):
    """
    统一的 LLM 调用接口，屏蔽 Anthropic SDK 和 OpenAI SDK 的格式差异。

    返回统一格式：
    {
        "stop_reason": "end_turn" | "tool_use" | "tool_calls",
        "content_text": str,          # 文本内容
        "tool_calls": [               # 工具调用列表（无则为空列表）
            {"id": str, "name": str, "input": dict}
        ],
        "input_tokens": int,
        "output_tokens": int,
        "raw": <原始响应对象>
    }
    """
    provider = llm_config.provider

    if provider == "anthropic":
        kwargs = dict(
            model=llm_config.model,
            max_tokens=llm_config.max_tokens,
            temperature=llm_config.temperature,
            system=system_prompt,
            messages=messages,
        )
        if tools:
            # Anthropic 工具格式：{"name", "description", "input_schema"}
            kwargs["tools"] = [
                {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
                for t in tools
            ]
        resp = client.messages.create(**kwargs)

        tool_calls = []
        content_text = ""
        for block in resp.content:
            if hasattr(block, "text"):
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append({"id": block.id, "name": block.name, "input": block.input})

        return {
            "stop_reason": resp.stop_reason,
            "content_text": content_text,
            "tool_calls": tool_calls,
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "raw": resp,
        }

    else:
        # OpenAI 兼容接口（openrouter / openai_compatible）
        # system prompt 作为第一条 system 消息
        oai_messages = [{"role": "system", "content": system_prompt}] + messages

        kwargs = dict(
            model=llm_config.model,
            max_tokens=llm_config.max_tokens,
            temperature=llm_config.temperature,
            messages=oai_messages,
        )
        if tools:
            # OpenAI 工具格式：{"type": "function", "function": {...}}
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["input_schema"],
                    }
                }
                for t in tools
            ]
            kwargs["tool_choice"] = "auto"

        resp = client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        msg = choice.message

        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": json.loads(tc.function.arguments),
                })

        stop_reason = "tool_use" if tool_calls else "end_turn"

        usage = resp.usage
        return {
            "stop_reason": stop_reason,
            "content_text": msg.content or "",
            "tool_calls": tool_calls,
            "input_tokens": usage.prompt_tokens if usage else 0,
            "output_tokens": usage.completion_tokens if usage else 0,
            "raw": resp,
        }


def build_tool_result_messages(provider: str, tool_calls_result: List[Dict]) -> List[Dict]:
    """
    将工具执行结果打包成下一轮消息，格式因 provider 而异。

    tool_calls_result 每项：
        {"id": str, "name": str, "input": dict, "result": dict, "raw_response": dict}
    """
    if provider == "anthropic":
        # Anthropic 格式：先把 assistant 的 tool_use blocks 加进去，再加 tool_result
        # 调用方负责先 append assistant 消息，这里只返回 user 侧的 tool_result 消息
        return [{
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": json.dumps(tc["result"], ensure_ascii=False),
                }
                for tc in tool_calls_result
            ]
        }]
    else:
        # OpenAI 格式：每个工具结果是一条独立的 tool 角色消息
        return [
            {
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(tc["result"], ensure_ascii=False),
            }
            for tc in tool_calls_result
        ]


# ======================
# 核心函数
# ======================

def load_cases(data_path: str, limit: int = None) -> Dict[str, Any]:
    """加载病例数据"""
    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if limit:
        # 只取前 N 个病例用于快速测试
        limited_data = {k: v for k, v in list(data.items())[:limit]}
        return limited_data

    return data


def format_case_as_prompt(case: Dict[str, Any]) -> str:
    """将病例格式化为 prompt"""
    prompt_parts = []

    # 患者基本信息
    if 'patient_info' in case:
        prompt_parts.append("## Patient Information")
        for key, value in case['patient_info'].items():
            prompt_parts.append(f"- {key}: {value}")

    # 症状
    if 'symptoms' in case:
        prompt_parts.append("\n## Symptoms")
        if isinstance(case['symptoms'], list):
            for symptom in case['symptoms']:
                prompt_parts.append(f"- {symptom}")
        else:
            prompt_parts.append(str(case['symptoms']))

    # 检查结果
    if 'test_results' in case:
        prompt_parts.append("\n## Test Results")
        for key, value in case['test_results'].items():
            prompt_parts.append(f"- {key}: {value}")

    prompt_parts.append("\n## Task")
    prompt_parts.append("Based on the above information, please provide your diagnosis.")

    return "\n".join(prompt_parts)


def extract_diagnosis(response_text: str) -> str:
    """从模型响应中提取诊断结果"""
    import re

    # 尝试提取 ### Diagnosis: 后面的内容
    pattern = r'### Diagnosis:\s*(.+?)(?:\n|$)'
    match = re.search(pattern, response_text, re.IGNORECASE)

    if match:
        return match.group(1).strip()

    # 如果没有找到，返回整个响应的前 200 个字符
    return response_text[:200].strip()


async def process_case_with_tools(
    case_id: str,
    case: Dict[str, Any],
    adapter: ToolkitAdapter,
    client,
    config: Any
) -> Dict[str, Any]:
    """
    处理单个病例（支持工具调用，兼容 anthropic / openrouter）

    Returns:
        {
            "case_id": str,
            "ground_truth": str,
            "prediction": str,
            "correct": bool,
            "tools_used": List[dict],
            "reasoning": str,
            "response_time": float,
            "tokens_used": int
        }
    """
    import time

    provider = config.llm.provider
    start_time = time.time()

    # 格式化病例为 prompt
    query = format_case_as_prompt(case)

    # 获取相关工具（baseline 模式返回空列表）
    tools = await adapter.get_tools_for_query(query)

    # 构建消息（不含 system，system 由 call_llm 处理）
    messages = [{"role": "user", "content": query}]

    tools_used = []
    total_input_tokens = 0
    total_output_tokens = 0
    resp = None
    max_iterations = 5  # 最多 5 轮工具调用

    for _ in range(max_iterations):
        resp = call_llm(client, config.llm, messages, tools, SYSTEM_PROMPT)
        total_input_tokens += resp["input_tokens"]
        total_output_tokens += resp["output_tokens"]

        if resp["stop_reason"] == "tool_use":
            # 执行所有工具调用
            tc_results = []
            for tc in resp["tool_calls"]:
                tool_name = tc["name"]

                # 从 tools 列表中找到对应的原始 resource_id
                resource_id = None
                for t in tools:
                    if t["name"] == tool_name:
                        resource_id = t.get("_resource_id", tool_name.replace("_", ":", 1))
                        break
                if not resource_id:
                    resource_id = tool_name.replace("_", ":", 1)

                result = await adapter.execute_tool(
                    resource_id=resource_id,
                    arguments=tc["input"]
                )

                tools_used.append({
                    "resource_id": resource_id,
                    "arguments": tc["input"],
                    "result": result.get("result"),
                    "success": result.get("success"),
                    "trace": result.get("trace")
                })

                tc_results.append({
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["input"],
                    "result": result,
                })

            # 将 assistant 消息追加到历史（格式因 provider 而异）
            if provider == "anthropic":
                messages.append({"role": "assistant", "content": resp["raw"].content})
            else:
                # OpenAI 格式：assistant 消息带 tool_calls 字段
                messages.append({
                    "role": "assistant",
                    "content": resp["content_text"] or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["input"], ensure_ascii=False)
                            }
                        }
                        for tc in resp["tool_calls"]
                    ]
                })

            # 追加工具结果消息
            messages.extend(build_tool_result_messages(provider, tc_results))

        else:
            break

    final_text = resp["content_text"] if resp else ""
    prediction = extract_diagnosis(final_text)
    response_time = time.time() - start_time
    tokens_used = total_input_tokens + total_output_tokens
    ground_truth = case.get("diagnosis", "")
    correct = bool(ground_truth) and ground_truth.lower() in prediction.lower()

    return {
        "case_id": case_id,
        "ground_truth": ground_truth,
        "prediction": prediction,
        "correct": correct,
        "tools_used": tools_used,
        "reasoning": final_text,
        "response_time": response_time,
        "tokens_used": tokens_used
    }


async def run_inference(
    config_path: str,
    mode: str,
    output_path: str,
    limit: int = None
):
    """运行推理实验"""

    # 加载配置
    print(f"[INFO] 加载配置: {config_path}, 模式: {mode}")
    config = load_config(config_path, mode)

    # 初始化 LLM 客户端（根据 provider 自动选择 Anthropic SDK 或 OpenAI SDK）
    print(f"[INFO] LLM provider: {config.llm.provider}, model: {config.llm.model}")
    client = build_llm_client(config.llm)

    # 初始化 ToolkitAdapter
    async with ToolkitAdapter(config) as adapter:
        # 加载病例数据
        print(f"[INFO] 加载病例数据: {DATA_PATH}")
        cases = load_cases(DATA_PATH, limit=limit)
        print(f"[INFO] 共 {len(cases)} 个病例")

        # 处理所有病例
        results = []
        for case_id, case in tqdm(cases.items(), desc="处理病例"):
            try:
                result = await process_case_with_tools(
                    case_id=case_id,
                    case=case,
                    adapter=adapter,
                    client=client,
                    config=config
                )
                results.append(result)
            except Exception as e:
                print(f"[ERR] 处理病例 {case_id} 失败: {e}")
                results.append({
                    "case_id": case_id,
                    "error": str(e)
                })

        # 计算统计信息
        total_cases = len(results)
        successful_cases = len([r for r in results if "error" not in r])
        correct_cases = len([r for r in results if r.get("correct", False)])
        accuracy = correct_cases / successful_cases if successful_cases > 0 else 0

        tool_usage_rate = len([r for r in results if r.get("tools_used")]) / successful_cases if successful_cases > 0 else 0
        avg_tools_per_case = sum(len(r.get("tools_used", [])) for r in results) / successful_cases if successful_cases > 0 else 0
        avg_response_time = sum(r.get("response_time", 0) for r in results) / successful_cases if successful_cases > 0 else 0
        total_tokens = sum(r.get("tokens_used", 0) for r in results)

        # 构建输出
        output = {
            "config": {
                "mode": config.mode,
                "llm_model": config.llm.model,
                "mtoolhub_enabled": config.mtoolhub.enabled,
                "search_top_k": config.mtoolhub.search_top_k if config.mtoolhub.enabled else None
            },
            "results": results,
            "summary": {
                "total_cases": total_cases,
                "successful_cases": successful_cases,
                "accuracy": accuracy,
                "tool_usage_rate": tool_usage_rate,
                "avg_tools_per_case": avg_tools_per_case,
                "avg_response_time": avg_response_time,
                "total_tokens": total_tokens
            }
        }

        # 保存结果
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f"\n[OK] 结果已保存到: {output_path}")
        print(f"[INFO] 准确率: {accuracy:.2%}")
        print(f"[INFO] 工具使用率: {tool_usage_rate:.2%}")
        print(f"[INFO] 平均每病例工具数: {avg_tools_per_case:.2f}")
        print(f"[INFO] 平均响应时间: {avg_response_time:.2f}s")
        print(f"[INFO] 总 tokens: {total_tokens}")


def main():
    parser = argparse.ArgumentParser(description="MedRBench 单轮诊断推理（Claude + MToolHub）")
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="实验配置文件路径（如 configs/experiment_config.yaml）"
    )
    parser.add_argument(
        "--mode",
        type=str,
        required=True,
        help="实验模式（如 baseline, experimental, ablation.search_only）"
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="输出文件路径（如 results/baseline.json）"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="限制处理的病例数量（用于快速测试）"
    )

    args = parser.parse_args()

    # 运行推理
    asyncio.run(run_inference(
        config_path=args.config,
        mode=args.mode,
        output_path=args.output,
        limit=args.limit
    ))


if __name__ == '__main__':
    main()
