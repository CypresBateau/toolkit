"""
one_turn_toolkit.py - 单轮诊断推理脚本（MToolHub 工具库版本）

基于原始 one_turn.py，最小改动：
1. gpt4o_workflow 和主模型改用 OpenRouter（OpenAI 兼容接口，同一个 key）
2. process_instance 注入 MToolHub toolkit（唯一新增变量）
3. 其他逻辑、提示词、输出格式完全不变

对比实验：
- baseline:     python one_turn_toolkit.py --mode baseline     （无工具，等价于原始 one_turn.py）
- experimental: python one_turn_toolkit.py --mode experimental （有工具）

控制变量：相同模型、相同提示词、相同温度、相同数据集，唯一差异是 toolkit。
"""

import os
import sys
import json
import re
import time
import random
import asyncio
import argparse
import tqdm
from pathlib import Path
from typing import List, Dict, Any, Optional
from openai import OpenAI

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.Adapters.toolkit_adapter import ToolkitAdapter, load_config

# ======================
# 配置常量（通过环境变量或命令行参数设置）
# ======================

# OpenRouter 统一入口（同时用于 GPT-4o 患者代理和主模型）
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# 主模型（DeepSeek-R1，与原始论文一致）
PRIMARY_MODEL = os.environ.get("PRIMARY_MODEL", "deepseek/deepseek-r1")

# 患者代理模型（GPT-4o，与原始论文一致）
PATIENT_AGENT_MODEL = os.environ.get("PATIENT_AGENT_MODEL", "openai/gpt-4o-2024-11-20")

# 路径常量
DATA_PATH = 'data/MedRBench/diagnosis_957_cases_with_rare_disease_491.json'
ASK_TEMPLATE_PATH = 'src/Inference/instructions/1turn_prompt_examination_recommend.txt'
FINAL_TEMPLATE_PATH = 'src/Inference/instructions/1turn_prompt_make_diagnosis.txt'
GPT_PROMPT_PATH = 'src/Inference/instructions/patient_agent_prompt.txt'

DEFAULT_SYSTEM_PROMPT = "You are a professional doctor"
VERBOSE = False

# ======================
# 工具函数（与原始脚本相同）
# ======================

def load_instruction(txt_path):
    """从文件加载提示词模板"""
    try:
        with open(txt_path, 'r', encoding='utf-8') as fp:
            return fp.read()
    except Exception as e:
        print(f"Error loading instruction from {txt_path}: {e}")
        return None


def parse_assessment_output(answer_text):
    """从阶段1响应中提取结论和额外信息请求（与原始脚本相同）"""
    pattern = r'### Conclusion:\s*(.*?)\s*### Additional Information Required:\s*(.*)'
    matches = re.search(pattern, answer_text, re.DOTALL)
    if matches:
        preliminary_conclusion = matches.group(1).strip()
        additional_info_required = matches.group(2).strip()
        return preliminary_conclusion, additional_info_required
    else:
        raise ValueError("Could not parse answer format - missing expected sections")


def ensure_output_dir(directory):
    """确保输出目录存在"""
    if not os.path.exists(directory):
        os.makedirs(directory)


# ======================
# 模型调用接口（改用 OpenRouter）
# ======================

def gpt4o_workflow(input_text, system_prompt=DEFAULT_SYSTEM_PROMPT):
    """
    患者代理：用 GPT-4o 回答医生请求的额外信息。
    与原始脚本逻辑相同，只是改用 OpenRouter 作为 API 入口。
    """
    if not OPENROUTER_API_KEY:
        raise ValueError("请设置环境变量 OPENROUTER_API_KEY")

    client = OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
        default_headers={
            "HTTP-Referer": "https://github.com/MedRBench",
            "X-Title": "MedRBench-MToolHub"
        }
    )

    max_retry = 3
    for curr_retry in range(max_retry):
        try:
            completion = client.chat.completions.create(
                model=PATIENT_AGENT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": input_text}
                ]
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"gpt4o_workflow Error ({curr_retry + 1}/{max_retry}): {e}")
            time.sleep(5)

    return None


def primary_model_workflow(messages, tools=None):
    """
    主模型调用（DeepSeek-R1 via OpenRouter）。
    支持可选的 function calling tools（experimental 模式注入）。
    返回 (answer, reasoning) 与原始脚本格式一致。
    """
    if not OPENROUTER_API_KEY:
        raise ValueError("请设置环境变量 OPENROUTER_API_KEY")

    client = OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
        default_headers={
            "HTTP-Referer": "https://github.com/MedRBench",
            "X-Title": "MedRBench-MToolHub"
        }
    )

    kwargs = dict(
        model=PRIMARY_MODEL,
        messages=messages,
        temperature=0.6,
        max_tokens=10000,
    )

    # experimental 模式：注入工具列表
    if tools:
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

    max_retry = 3
    for curr_retry in range(max_retry):
        try:
            response = client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            msg = choice.message
            content = msg.content or ""

            # 解析 reasoning（DeepSeek-R1 的 <think> 标签）
            if "</think>" in content:
                reasoning = content.split('</think>')[0].replace('<think>', '').strip()
                answer = content.split('</think>')[1].strip()
            else:
                reasoning = ""
                answer = content

            # 返回工具调用信息（供 experimental 模式使用）
            tool_calls = msg.tool_calls or []

            return answer, reasoning, tool_calls

        except Exception as e:
            print(f"primary_model_workflow Error ({curr_retry + 1}/{max_retry}): {e}")
            time.sleep(5)

    return None, None, []


# ======================
# 核心处理函数
# ======================

def process_instance(key, json_data, gpt_prompt, ask_template, final_template,
                     model_name, toolkit_adapter=None, loop=None):
    """
    处理单个病例。
    与原始 one_turn.py 的 process_instance 逻辑完全相同，
    唯一新增：toolkit_adapter 参数（None = baseline，有值 = experimental）。
    """
    output_dir = f'1_turn_{model_name.lower()}'
    output_file = f'{output_dir}/log_{key}.json'

    # 跳过已处理的病例
    if os.path.exists(output_file):
        return

    for try_idx in range(3):
        try:
            one_instance = json_data[key]
            case_summary = one_instance['generate_case']['case_summary']

            # 分离病例摘要和辅助检查（与原始脚本相同）
            case_summary_without_ancillary_test = case_summary
            ancillary_test = ""
            if "Ancillary Tests" in case_summary:
                case_summary_paragrapgh = case_summary.strip().split('\n')
                for idx in range(len(case_summary_paragrapgh)):
                    if "Ancillary Tests" in case_summary_paragrapgh[idx]:
                        case_summary_without_ancillary_test = "\n".join(case_summary_paragrapgh[:idx])
                        ancillary_test = "\n".join(case_summary_paragrapgh[idx:])
                        break

            # 准备提示词（与原始脚本相同）
            gpt_instruction = gpt_prompt.format(
                case=case_summary_without_ancillary_test,
                ancillary_test_results=ancillary_test
            )

            # 初始消息（与原始脚本相同）
            primary_messages = [
                {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
                {"role": "user", "content": ask_template.format(case=case_summary_without_ancillary_test)}
            ]
            messages_log = [
                {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
                {"role": "user", "content": ask_template.format(case=case_summary_without_ancillary_test)}
            ]

            # 获取工具列表（baseline=空列表，experimental=MToolHub 工具）
            tools = []
            if toolkit_adapter is not None and loop is not None:
                tools = loop.run_until_complete(
                    toolkit_adapter.get_tools_for_query(case_summary_without_ancillary_test)
                )

            # Step 1：初步诊断（与原始脚本相同，新增 tools 参数）
            primary_answer, primary_reasoning, tool_calls_1 = primary_model_workflow(
                primary_messages, tools=tools
            )

            if VERBOSE:
                print(f"Primary model reasoning:\n{primary_reasoning}")
                print(f"Primary model answer:\n{primary_answer}")

            if not primary_answer:
                print(f"Error: No response from primary model")
                continue

            primary_answer = primary_answer.replace('```', '').strip()
            preliminary_conclusion, additional_info_required = parse_assessment_output(primary_answer)

            # 执行工具调用（experimental 模式）
            # 构建 function_name -> resource_id 映射（从 tools 列表中取，避免反推出错）
            tool_name_to_resource_id = {t["name"]: t.get("_resource_id", t["name"]) for t in tools}

            tool_results_log = []
            if toolkit_adapter is not None and loop is not None and tool_calls_1:
                for tc in tool_calls_1:
                    import json as _json
                    resource_id = tool_name_to_resource_id.get(tc.function.name, tc.function.name)
                    arguments = _json.loads(tc.function.arguments)
                    result = loop.run_until_complete(
                        toolkit_adapter.execute_tool(resource_id=resource_id, arguments=arguments)
                    )
                    tool_results_log.append({
                        "resource_id": resource_id,
                        "arguments": arguments,
                        "result": result.get("result"),
                        "success": result.get("success")
                    })

            # 更新消息历史（与原始脚本相同）
            primary_messages.append({"role": "assistant", "content": primary_answer})
            messages_log.append({"role": "assistant", "content": {
                'reasoning': primary_reasoning,
                'answer': primary_answer
            }})

            # Step 2：GPT-4o 患者代理（与原始脚本完全相同）
            gpt_input = f"The junior physician wants the following information:\n{additional_info_required}"
            gpt_response = gpt4o_workflow(gpt_input, gpt_instruction)

            if VERBOSE:
                print(f"GPT-4o response:\n{gpt_response}")

            if not gpt_response:
                print(f"Error: No response from GPT-4o")
                continue

            formatted_response = final_template.format(additional_information=gpt_response)

            primary_messages.append({"role": "user", "content": formatted_response})
            messages_log.append({"role": "user", "content": formatted_response})

            # Step 3：最终诊断（与原始脚本相同，新增 tools 参数）
            final_answer, final_reasoning, tool_calls_2 = primary_model_workflow(
                primary_messages, tools=tools
            )

            if VERBOSE:
                print(f"Final answer:\n{final_answer}")

            if not final_answer:
                print(f"Error: No final response from primary model")
                continue

            final_answer = final_answer.replace('```', '').strip()

            # 执行工具调用（experimental 模式，Step 3）
            if toolkit_adapter is not None and loop is not None and tool_calls_2:
                for tc in tool_calls_2:
                    import json as _json
                    resource_id = tool_name_to_resource_id.get(tc.function.name, tc.function.name)
                    arguments = _json.loads(tc.function.arguments)
                    result = loop.run_until_complete(
                        toolkit_adapter.execute_tool(resource_id=resource_id, arguments=arguments)
                    )
                    tool_results_log.append({
                        "resource_id": resource_id,
                        "arguments": arguments,
                        "result": result.get("result"),
                        "success": result.get("success")
                    })

            primary_messages.append({"role": "assistant", "content": final_answer})
            messages_log.append({"role": "assistant", "content": {
                'reasoning': final_reasoning,
                'answer': final_answer
            }})

            # 构建输出（与原始脚本相同）
            output_messages = []
            for msg in messages_log:
                output_messages.append({
                    'role': msg['role'],
                    'content': msg['content']
                })

            log_data = {
                'output_messages': output_messages,
            }

            # experimental 模式额外记录工具使用信息
            if tool_results_log:
                log_data['tools_used'] = tool_results_log

            with open(output_file, 'w', encoding='utf-8') as fp:
                json.dump(log_data, fp, ensure_ascii=False, indent=4)

            print(f"Successfully processed {key} with {model_name}")
            return

        except Exception as e:
            if try_idx == 2:
                print(f"Failed to process {key} after 3 retries: {e}")
            else:
                print(f"Error processing {key} (retry {try_idx + 1}/3): {e}")
                time.sleep(2)


# ======================
# 推理入口
# ======================

def run_inference(model_name, config_path=None, mode="baseline", limit=None, case_ids=None):
    """
    运行推理实验。

    Parameters:
    -----------
    model_name : str
        输出目录名称（如 "deepseek-r1"）
    config_path : str
        实验配置文件路径（experimental 模式需要）
    mode : str
        "baseline"（无工具）或 "experimental"（有工具）
    limit : int
        限制处理的病例数（用于快速测试）
    case_ids : list
        指定要处理的病例 ID 列表（如果提供，则只处理这些病例）
    """
    print(f"[INFO] 运行模式: {mode}, 模型: {model_name}")

    # 加载提示词模板
    ask_template = load_instruction(ASK_TEMPLATE_PATH)
    final_template = load_instruction(FINAL_TEMPLATE_PATH)
    gpt_prompt = load_instruction(GPT_PROMPT_PATH)

    if not all([ask_template, final_template, gpt_prompt]):
        print("[ERR] 无法加载提示词模板")
        return

    # 加载病例数据
    try:
        with open(DATA_PATH, 'r', encoding='utf-8') as fp:
            json_data = json.load(fp)
    except Exception as e:
        print(f"[ERR] 加载数据失败: {e}")
        return

    # 筛选病例
    keys = list(json_data.keys())

    if case_ids:
        # 如果指定了 case_ids，只处理这些病例
        keys = [k for k in keys if k in case_ids]
        print(f"[INFO] 指定处理 {len(case_ids)} 个病例，找到 {len(keys)} 个")
        if len(keys) < len(case_ids):
            missing = set(case_ids) - set(keys)
            print(f"[WARN] 以下病例 ID 不存在: {missing}")
    elif limit:
        # 否则使用 limit 限制
        keys = keys[:limit]
        print(f"[INFO] 限制处理 {limit} 个病例")

    print(f"[INFO] 共 {len(keys)} 个病例")

    # 创建输出目录
    output_dir = f'1_turn_{model_name.lower()}'
    ensure_output_dir(output_dir)

    # 初始化 toolkit（experimental 模式）
    toolkit_adapter = None
    loop = None

    if mode == "experimental":
        if not config_path:
            print("[ERR] experimental 模式需要 --config 参数")
            return

        config = load_config(config_path, mode)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        toolkit_adapter = loop.run_until_complete(_init_adapter(config))
        print(f"[INFO] MToolHub 工具库已初始化")

    try:
        # 顺序处理（与原始脚本的多进程不同，因为 toolkit 是异步的）
        for key in tqdm.tqdm(keys, desc=f"Processing with {model_name} ({mode})"):
            process_instance(
                key, json_data, gpt_prompt, ask_template, final_template,
                model_name,
                toolkit_adapter=toolkit_adapter,
                loop=loop
            )
    finally:
        if loop and toolkit_adapter:
            loop.run_until_complete(_close_adapter(toolkit_adapter))
            loop.close()

    print(f"[OK] 完成，结果保存在 {output_dir}/")


async def _init_adapter(config):
    """初始化 ToolkitAdapter"""
    adapter = ToolkitAdapter(config)
    await adapter.__aenter__()
    return adapter


async def _close_adapter(adapter):
    """关闭 ToolkitAdapter"""
    await adapter.__aexit__(None, None, None)


# ======================
# 命令行入口
# ======================

def main():
    parser = argparse.ArgumentParser(
        description="MedRBench 单轮诊断推理（支持 MToolHub 工具库）"
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="baseline",
        choices=["baseline", "experimental"],
        help="实验模式：baseline（无工具）或 experimental（有工具）"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="实验配置文件路径（experimental 模式必填）"
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default="deepseek-r1",
        help="输出目录名称，同时也是评估脚本中的模型标识（默认: deepseek-r1）"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="限制处理的病例数（用于快速测试，如 --limit 5）"
    )
    parser.add_argument(
        "--case-ids",
        type=str,
        default=None,
        help="指定要处理的病例 ID 列表，逗号分隔（如 --case-ids PMC11385788,PMC11416466）"
    )

    args = parser.parse_args()

    if not OPENROUTER_API_KEY:
        print("[ERR] 请设置环境变量 OPENROUTER_API_KEY")
        sys.exit(1)

    # 解析 case_ids
    case_ids = None
    if args.case_ids:
        case_ids = [cid.strip() for cid in args.case_ids.split(',')]

    run_inference(
        model_name=args.model_name,
        config_path=args.config,
        mode=args.mode,
        limit=args.limit,
        case_ids=case_ids
    )


if __name__ == '__main__':
    main()
