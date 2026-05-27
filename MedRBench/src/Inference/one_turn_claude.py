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
SYSTEM_PROMPT = "You are a professional doctor"

# 提示词模板路径
ASK_TEMPLATE_PATH = 'src/Inference/instructions/1turn_prompt_examination_recommend.txt'
FINAL_TEMPLATE_PATH = 'src/Inference/instructions/1turn_prompt_make_diagnosis.txt'


# ======================
# 辅助函数
# ======================

def load_instruction(txt_path):
    """从文件加载提示词模板"""
    try:
        with open(txt_path, 'r', encoding='utf-8') as fp:
            return fp.read()
    except Exception as e:
        print(f"[ERR] 加载提示词失败 {txt_path}: {e}")
        return None


def parse_response_sections(response_text: str) -> Dict[str, str]:
    """解析 LLM 响应，提取 Chain of Thought 和 Conclusion"""
    reasoning = ""
    answer = ""

    # 提取 Chain of Thought
    if "### Chain of Thought:" in response_text:
        parts = response_text.split("### Chain of Thought:")
        if len(parts) > 1:
            cot_part = parts[1].split("###")[0].strip()
            reasoning = cot_part

    # 提取 Conclusion
    if "### Conclusion:" in response_text:
        parts = response_text.split("### Conclusion:")
        if len(parts) > 1:
            conclusion_part = parts[1].split("###")[0].strip()
            answer = conclusion_part

    return {"reasoning": reasoning, "answer": response_text}  # answer 保留完整响应


def parse_assessment_output(answer_text: str):
    """从阶段1响应中提取结论和额外信息请求"""
    import re
    pattern = r'### Conclusion:\s*(.*?)\s*### Additional Information Required:\s*(.*)'
    matches = re.search(pattern, answer_text, re.DOTALL)
    if matches:
        preliminary_conclusion = matches.group(1).strip()
        additional_info_required = matches.group(2).strip()
        return preliminary_conclusion, additional_info_required
    else:
        # 如果解析失败，返回默认值
        return answer_text, "Not required."


def extract_case_summary_without_tests(case: Dict[str, Any]) -> str:
    """提取病例摘要，排除辅助检查结果"""
    gc = case.get("generate_case", {})
    case_summary = gc.get("case_summary", "")

    if not case_summary:
        return case.get("raw_case", "")

    # 简化实现：移除包含 "Laboratory" 或 "Imaging" 的段落
    lines = case_summary.split('\n')
    filtered_lines = []
    skip = False
    for line in lines:
        if any(keyword in line for keyword in ['Laboratory', 'Imaging', 'Test Results', 'Examination Results']):
            skip = True
        if not skip:
            filtered_lines.append(line)

    return '\n'.join(filtered_lines).strip()


def extract_ancillary_tests(case: Dict[str, Any]) -> str:
    """提取辅助检查结果"""
    gc = case.get("generate_case", {})
    case_summary = gc.get("case_summary", "")

    if not case_summary:
        return "No additional test results available."

    # 提取包含 "Laboratory" 或 "Imaging" 的段落
    lines = case_summary.split('\n')
    test_lines = []
    capture = False
    for line in lines:
        if any(keyword in line for keyword in ['Laboratory', 'Imaging', 'Test Results', 'Examination Results']):
            capture = True
        if capture:
            test_lines.append(line)

    return '\n'.join(test_lines).strip() if test_lines else "No additional test results available."


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
    gc = case.get("generate_case", {})

    # 优先用 generate_case.case_summary（结构化摘要）
    case_summary = gc.get("case_summary", "")
    if case_summary:
        return (
            "## Patient Case\n"
            f"{case_summary}\n\n"
            "## Task\n"
            "Based on the above information, please provide your diagnosis."
        )

    # 回退到 raw_case（原始病例文本）
    raw_case = case.get("raw_case", "")
    if raw_case:
        return (
            "## Patient Case\n"
            f"{raw_case}\n\n"
            "## Task\n"
            "Based on the above information, please provide your diagnosis."
        )

    return "## Task\nPlease provide your diagnosis based on the available information."


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
    处理单个病例（两阶段推理，输出格式与原始 MedRBench 一致）

    Returns:
        {
            "output_messages": List[Dict],  # 消息历史
            "tools_used": List[dict],       # 工具使用记录
            "response_time": float,
            "tokens_used": int
        }
    """
    import time
    start_time = time.time()

    provider = config.llm.provider

    # 加载提示词模板
    ask_template = load_instruction(ASK_TEMPLATE_PATH)
    final_template = load_instruction(FINAL_TEMPLATE_PATH)

    if not ask_template or not final_template:
        raise ValueError("无法加载提示词模板")

    # 提取病例摘要（不含辅助检查）
    case_summary_without_tests = extract_case_summary_without_tests(case)

    # 提取辅助检查结果
    ancillary_tests = extract_ancillary_tests(case)

    # 初始化消息历史
    output_messages = []
    tools_used = []
    total_input_tokens = 0
    total_output_tokens = 0

    # ===== 阶段 1：初步评估 =====
    stage1_prompt = ask_template.format(case=case_summary_without_tests)

    # 添加 system 消息到输出历史
    output_messages.append({
        "role": "system",
        "content": SYSTEM_PROMPT
    })

    # 添加 user 消息
    output_messages.append({
        "role": "user",
        "content": stage1_prompt
    })

    # 获取相关工具（baseline 模式返回空列表）
    tools = await adapter.get_tools_for_query(case_summary_without_tests)

    # 调用 LLM（阶段 1）
    messages = [{"role": "user", "content": stage1_prompt}]
    resp1 = call_llm(client, config.llm, messages, tools, SYSTEM_PROMPT)
    total_input_tokens += resp1["input_tokens"]
    total_output_tokens += resp1["output_tokens"]

    # 处理工具调用（如果有）
    if resp1["stop_reason"] == "tool_use":
        for tc in resp1["tool_calls"]:
            tool_name = tc["name"]
            resource_id = None
            for t in tools:
                if t["name"] == tool_name:
                    resource_id = t.get("_resource_id", tool_name.replace("_", ":", 1))
                    break
            if not resource_id:
                resource_id = tool_name.replace("_", ":", 1)

            result = await adapter.execute_tool(resource_id=resource_id, arguments=tc["input"])
            tools_used.append({
                "resource_id": resource_id,
                "arguments": tc["input"],
                "result": result.get("result"),
                "success": result.get("success")
            })

    # 获取阶段 1 响应文本
    stage1_response = resp1["content_text"]
    stage1_response = stage1_response.replace('```', '').strip()

    # 解析阶段 1 响应
    stage1_parsed = parse_response_sections(stage1_response)

    # 添加 assistant 消息（阶段 1）
    output_messages.append({
        "role": "assistant",
        "content": {
            "reasoning": stage1_parsed["reasoning"],
            "answer": stage1_response  # 完整响应
        }
    })

    # 提取额外信息请求
    try:
        preliminary_conclusion, additional_info_required = parse_assessment_output(stage1_response)
    except:
        additional_info_required = "Not required."

    # ===== 阶段 2：最终诊断 =====
    # 模拟患者代理提供辅助检查结果
    stage2_prompt = final_template.format(additional_information=ancillary_tests)

    # 添加 user 消息（阶段 2）
    output_messages.append({
        "role": "user",
        "content": stage2_prompt
    })

    # 更新消息历史
    messages.append({"role": "assistant", "content": stage1_response})
    messages.append({"role": "user", "content": stage2_prompt})

    # 调用 LLM（阶段 2）
    resp2 = call_llm(client, config.llm, messages, tools, SYSTEM_PROMPT)
    total_input_tokens += resp2["input_tokens"]
    total_output_tokens += resp2["output_tokens"]

    # 处理工具调用（如果有）
    if resp2["stop_reason"] == "tool_use":
        for tc in resp2["tool_calls"]:
            tool_name = tc["name"]
            resource_id = None
            for t in tools:
                if t["name"] == tool_name:
                    resource_id = t.get("_resource_id", tool_name.replace("_", ":", 1))
                    break
            if not resource_id:
                resource_id = tool_name.replace("_", ":", 1)

            result = await adapter.execute_tool(resource_id=resource_id, arguments=tc["input"])
            tools_used.append({
                "resource_id": resource_id,
                "arguments": tc["input"],
                "result": result.get("result"),
                "success": result.get("success")
            })

    # 获取阶段 2 响应文本
    stage2_response = resp2["content_text"]
    stage2_response = stage2_response.replace('```', '').strip()

    # 解析阶段 2 响应
    stage2_parsed = parse_response_sections(stage2_response)

    # 添加 assistant 消息（阶段 2）
    output_messages.append({
        "role": "assistant",
        "content": {
            "reasoning": stage2_parsed["reasoning"],
            "answer": stage2_response  # 完整响应
        }
    })

    # 返回结果
    response_time = time.time() - start_time
    tokens_used = total_input_tokens + total_output_tokens

    return {
        "output_messages": output_messages,
        "tools_used": tools_used,
        "response_time": response_time,
        "tokens_used": tokens_used
    }


async def run_inference(
    config_path: str,
    mode: str,
    output_dir: str,
    limit: int = None
):
    """运行推理实验（输出格式与原始 MedRBench 一致）"""

    # 加载配置
    print(f"[INFO] 加载配置: {config_path}, 模式: {mode}")
    config = load_config(config_path, mode)

    # 获取模型名称（用于输出目录）
    model_name = getattr(config.llm, 'output_model_name', 'deepseek-r1')

    # 初始化 LLM 客户端
    print(f"[INFO] LLM provider: {config.llm.provider}, model: {config.llm.model}")
    client = build_llm_client(config.llm)

    # 创建输出目录
    output_path = Path(output_dir) / f"1_turn_{model_name}"
    output_path.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] 输出目录: {output_path}")

    # 初始化 ToolkitAdapter
    async with ToolkitAdapter(config) as adapter:
        # 加载病例数据
        print(f"[INFO] 加载病例数据: {DATA_PATH}")
        cases = load_cases(DATA_PATH, limit=limit)
        print(f"[INFO] 共 {len(cases)} 个病例")

        # 统计信息
        successful_cases = 0
        failed_cases = 0
        total_tools_used = 0
        total_response_time = 0
        total_tokens = 0

        # 处理所有病例
        for case_id, case in tqdm(cases.items(), desc="处理病例"):
            try:
                result = await process_case_with_tools(
                    case_id=case_id,
                    case=case,
                    adapter=adapter,
                    client=client,
                    config=config
                )

                # 构建输出消息（MedRBench 格式）
                output_messages = result.get("output_messages", [])

                # 保存单个病例文件
                case_output_file = output_path / f"log_{case_id}.json"
                with open(case_output_file, 'w', encoding='utf-8') as f:
                    json.dump({"output_messages": output_messages}, f, ensure_ascii=False, indent=2)

                # 更新统计
                successful_cases += 1
                total_tools_used += len(result.get("tools_used", []))
                total_response_time += result.get("response_time", 0)
                total_tokens += result.get("tokens_used", 0)

            except Exception as e:
                print(f"[ERR] 处理病例 {case_id} 失败: {e}")
                failed_cases += 1

        # 打印统计信息
        total_cases = successful_cases + failed_cases
        print(f"\n[OK] 处理完成")
        print(f"[INFO] 成功: {successful_cases}/{total_cases}")
        print(f"[INFO] 失败: {failed_cases}/{total_cases}")
        if successful_cases > 0:
            print(f"[INFO] 平均工具调用数: {total_tools_used / successful_cases:.2f}")
            print(f"[INFO] 平均响应时间: {total_response_time / successful_cases:.2f}s")
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
        help="输出目录路径（如 results/，会在其中创建 1_turn_{model}/ 子目录）"
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
        output_dir=args.output,
        limit=args.limit
    ))


if __name__ == '__main__':
    main()
