"""
run_toolkit.py - LLM + MToolHub 工具调用推理脚本

基于 run_vanilla.py，新增 MToolHub 工具调用：
1. 根据计算器名称搜索 MToolHub 工具
2. 将工具注入 LLM function calling
3. 执行工具调用并将结果返回给 LLM
4. 输出格式与 run_vanilla.py 完全一致，可直接用原始评估脚本对比

运行方式：
    export OPENROUTER_API_KEY=sk-or-v1-xxxxx

    # limit 50 验证
    python run_toolkit.py --model z-ai/glm-4.6v --prompt zero_shot --limit 50

    # 全量
    python run_toolkit.py --model z-ai/glm-4.6v --prompt zero_shot
"""

import re
import os
import sys
import json
import math
import time
import asyncio
import tqdm
import argparse
import numpy as np
import pandas as pd
import httpx
from openai import OpenAI
from evaluate import check_correctness
from table_stats import compute_overall_accuracy

# ======================
# 配置
# ======================

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
MTOOLHUB_URL = os.environ.get("MTOOLHUB_URL", "http://localhost:8081")
MTOOLHUB_SEARCH_TOP_K = int(os.environ.get("MTOOLHUB_SEARCH_TOP_K", "3"))

DATA_PATH = "../datasets/test_data.csv"
ONE_SHOT_PATH = "one_shot_finalized_explanation.json"


# ======================
# 提示词构建（与 run_vanilla.py 完全相同）
# ======================

def zero_shot(note, question):
    system_msg = (
        'You are a helpful assistant for calculating a score for a given patient note. '
        'Please think step-by-step to solve the question and then generate the required score. '
        'Your output should only contain a JSON dict formatted as '
        '{"step_by_step_thinking": str(your_step_by_step_thinking_procress_to_solve_the_question), '
        '"answer": str(short_and_direct_answer_of_the_question)}.'
    )
    user_temp = (
        f'Here is the patient note:\n{note}\n\n'
        f'Here is the task:\n{question}\n\n'
        f'Please directly output the JSON dict formatted as '
        f'{{"step_by_step_thinking": str(your_step_by_step_thinking_procress_to_solve_the_question), '
        f'"answer": str(short_and_direct_answer_of_the_question)}}:'
    )
    return system_msg, user_temp


def zero_shot_with_tools(note, question):
    system_msg = (
        'You are a helpful assistant for calculating a score for a given patient note. '
        'You have access to medical calculator tools. '
        'You MUST call the appropriate tool to compute the answer — do not calculate manually. '
        'IMPORTANT: Before passing any parameter to a tool, convert the value to the unit specified '
        'in the tool parameter description. Do not pass raw values from the patient note if the units differ. '
        'After receiving the tool result, output only a JSON dict formatted as '
        '{"step_by_step_thinking": str(your_step_by_step_thinking_procress_to_solve_the_question), '
        '"answer": str(short_and_direct_answer_of_the_question)}.'
    )
    user_temp = (
        f'Here is the patient note:\n{note}\n\n'
        f'Here is the task:\n{question}\n\n'
        f'Please call the appropriate tool first, then output the JSON dict formatted as '
        f'{{"step_by_step_thinking": str(your_step_by_step_thinking_procress_to_solve_the_question), '
        f'"answer": str(short_and_direct_answer_of_the_question)}}:'
    )
    return system_msg, user_temp


def direct_answer(note, question):
    system_msg = (
        'You are a helpful assistant for calculating a score for a given patient note. '
        'Please output answer only without any other text. '
        'Your output should only contain a JSON dict formatted as '
        '{"answer": str(value which is the answer to the question)}.'
    )
    user_temp = (
        f'Here is the patient note:\n{note}\n\n'
        f'Here is the task:\n{question}\n\n'
        f'Please directly output the JSON dict formatted as '
        f'{{"answer": str(value which is the answer to the question)}}:'
    )
    return system_msg, user_temp


def one_shot(note, question, one_shot_question, example_note, example_output):
    system_msg = (
        'You are a helpful assistant for calculating a score for a given patient note. '
        'Please think step-by-step to solve the question and then generate the required score. '
        'Your output should only contain a JSON dict formatted as '
        '{{"step_by_step_thinking": str(your_step_by_step_thinking_procress_to_solve_the_question), '
        '"answer": str(short_and_direct_answer_of_the_question)}}.'
    )
    system_msg += f'Here is an example patient note:\n\n{example_note}'
    system_msg += f'\n\nHere is an example task:\n\n{one_shot_question}'
    system_msg += (
        f'\n\nPlease directly output the JSON dict formatted as '
        f'{{"step_by_step_thinking": str(your_step_by_step_thinking_procress_to_solve_the_question), '
        f'"answer": str(value which is the answer to the question)}}:\n\n{json.dumps(example_output)}'
    )
    user_temp = (
        f'Here is the patient note:\n\n{note}\n\n'
        f'Here is the task:\n\n{question}\n\n'
        f'Please directly output the JSON dict formatted as '
        f'{{"step_by_step_thinking": str(your_step_by_step_thinking_procress_to_solve_the_question), '
        f'"answer": str(short_and_direct_answer_of_the_question)}}:'
    )
    return system_msg, user_temp


# ======================
# 答案提取（与 run_vanilla.py 完全相同）
# ======================

def extract_answer(answer, calid):
    calid = int(calid)
    extracted_answer = re.findall(r'[Aa]nswer":\s*(.*?)\}', answer)
    matches = re.findall(r'"step_by_step_thinking":\s*"([^"]+)"\s*,\s*"[Aa]nswer"', answer)

    if matches:
        explanation = matches[-1]
    else:
        explanation = "No Explanation"

    if len(extracted_answer) == 0:
        extracted_answer = "Not Found"
    else:
        extracted_answer = extracted_answer[-1].strip().strip('"')
        if extracted_answer in [
            "str(short_and_direct_answer_of_the_question)",
            "str(value which is the answer to the question)",
            "X.XX"
        ]:
            extracted_answer = "Not Found"

    if calid in [13, 68]:
        match = re.search(r"^(0?[1-9]|1[0-2])\/(0?[1-9]|[12][0-9]|3[01])\/(\d{4})", extracted_answer)
        if match:
            month = int(match.group(1))
            day = int(match.group(2))
            year = match.group(3)
            answer = f"{month:02}/{day:02}/{year}"
        else:
            answer = "N/A"

    elif calid in [69]:
        extracted_answer = extracted_answer.replace("[", "(").replace("]", ")").replace("'", "").replace('"', "")
        match = re.search(r"\(?[\"\']?(\d+)\s*(weeks?)?[\"\']?,?\s*[\"\']?(\d+)\s*(days?)?[\"\']?\s*\)?", extracted_answer)
        if match:
            weeks = match.group(1)
            days = match.group(3)
            answer = f"({weeks}, {days})"
        else:
            answer = "N/A"

    elif calid in [4, 15, 16, 17, 18, 20, 21, 25, 27, 28, 29, 32, 33, 36, 43, 45, 48, 51]:
        match = re.search(r"(\d+) out of", extracted_answer)
        if match:
            answer = match.group(1)
        else:
            match = re.search(r"-?\d+(, ?-?\d+)+", extracted_answer)
            if match:
                answer = str(len(match.group(0).split(",")))
            else:
                match = re.findall(r"(-?\d+(\.\d+)?)", extracted_answer)
                if len(match) > 0:
                    answer = match[-1][0]
                else:
                    answer = "N/A"

    elif calid in [2, 3, 5, 6, 7, 8, 9, 10, 11, 19, 22, 23, 24, 26, 30, 31,
                   38, 39, 40, 44, 46, 49, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67]:
        match = re.search(r"str\((.*)\)", extracted_answer)
        if match:
            expression = (match.group(1)
                .replace("^", "**")
                .replace("is odd", "% 2 == 1")
                .replace("is even", "% 2 == 0")
                .replace("sqrt", "math.sqrt")
                .replace(".math", "")
                .replace("weight", "")
                .replace("height", "")
                .replace("mg/dl", "")
                .replace("g/dl", "")
                .replace("mmol/L", "")
                .replace("kg", "")
                .replace("g", "")
                .replace("mEq/L", ""))
            expression = expression.split('#')[0]
            if expression.count('(') > expression.count(')'):
                expression += ')' * (expression.count('(') - expression.count(')'))
            elif expression.count(')') > expression.count('('):
                expression = '(' * (expression.count(')') - expression.count('(')) + expression
            try:
                answer = eval(expression, {"__builtins__": None},
                              {"min": min, "pow": pow, "round": round, "abs": abs,
                               "int": int, "float": float, "math": math, "np": np, "numpy": np})
            except Exception:
                answer = "N/A"
        else:
            match = re.search(r"(-?\d+(\.\d+)?)\s*mL/min/1.73", extracted_answer)
            if match:
                answer = eval(match.group(1))
            else:
                match = re.findall(r"(-?\d+(\.\d+)?)\%", extracted_answer)
                if len(match) > 0:
                    answer = eval(match[-1][0]) / 100
                else:
                    match = re.findall(r"(-?\d+(\.\d+)?)", extracted_answer)
                    if len(match) > 0:
                        answer = eval(match[-1][0])
                    else:
                        answer = "N/A"
        if answer != "N/A":
            answer = str(answer)

    else:
        answer = "N/A"

    return answer, explanation


# ======================
# MToolHub 工具搜索与执行
# ======================

def search_tools(calculator_name: str, top_k: int = 3):
    """
    根据计算器名称搜索 MToolHub 工具，返回 OpenAI function calling 格式列表。
    搜索失败时返回空列表（不影响主流程）。
    """
    try:
        resp = httpx.post(
            f"{MTOOLHUB_URL}/api/tools/search",
            json={"query": calculator_name, "top_k": top_k},
            timeout=10.0
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])

        tools = []
        tool_id_map = {}  # function name -> resource_id

        for res in results:
            item = res.get("item", res)
            resource_id = item.get("id", "")
            if not resource_id:
                continue

            # function name 不能含冒号，替换为下划线
            func_name = resource_id.replace(":", "_").replace("-", "_")

            # 转换 input_schema
            raw_schema = item.get("input_schema")
            input_schema = _convert_schema(raw_schema)

            tools.append({
                "type": "function",
                "function": {
                    "name": func_name,
                    "description": item.get("description", ""),
                    "parameters": input_schema,
                }
            })
            tool_id_map[func_name] = resource_id

        return tools, tool_id_map

    except Exception as e:
        print(f"[WARN] 工具搜索失败 ({calculator_name}): {e}")
        return [], {}


def _convert_schema(input_schema):
    """将 MToolHub 的参数格式转换为 JSON Schema"""
    if not input_schema:
        return {"type": "object", "properties": {}, "required": []}
    if isinstance(input_schema, dict):
        return input_schema
    if isinstance(input_schema, str):
        return {
            "type": "object",
            "properties": {
                "arguments": {"type": "string", "description": input_schema}
            },
            "required": []
        }
    # 参数列表格式
    type_map = {
        "float": "number", "int": "integer", "integer": "integer",
        "str": "string", "string": "string", "bool": "boolean", "boolean": "boolean",
    }
    properties = {}
    required = []
    for param in input_schema:
        if not isinstance(param, dict):
            continue
        name = param.get("name", "")
        if not name:
            continue
        prop = {
            "type": type_map.get(param.get("type", "str"), "string"),
            "description": param.get("description", ""),
        }
        options = param.get("options")
        if options and isinstance(options, list):
            prop["enum"] = options
        elif options and isinstance(options, str):
            # 字符串格式的 options 追加到 description，让 LLM 知道合法值
            prop["description"] += f" (Valid values/range: {options})"
        properties[name] = prop
        required.append(name)
    return {"type": "object", "properties": properties, "required": required}


def execute_tool(resource_id: str, arguments: dict):
    """执行 MToolHub 工具调用"""
    try:
        resp = httpx.post(
            f"{MTOOLHUB_URL}/api/execute",
            json={"resource_id": resource_id, "arguments": arguments},
            timeout=30.0
        )
        if not resp.is_success:
            return {"success": False, "result": None, "error": f"HTTP {resp.status_code}: {resp.text}"}
        return resp.json()
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}


# ======================
# LLM 调用（支持 function calling 多轮）
# ======================

def call_llm_with_tools(model, messages, tools=None, tool_id_map=None, max_retries=3):
    """
    调用 LLM，支持 function calling。
    如果 LLM 发起工具调用，执行工具并将结果追加到消息中，再次调用 LLM。
    返回最终文本回复和工具调用记录。
    """
    if not OPENROUTER_API_KEY:
        raise ValueError("[ERR] 请设置环境变量 OPENROUTER_API_KEY")

    client = OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
        default_headers={
            "HTTP-Referer": "https://github.com/MedCalc-Bench",
            "X-Title": "MedCalc-Bench-Toolkit"
        }
    )

    tool_calls_log = []
    current_messages = list(messages)
    # 使用 tool_id_map 还原 resource_id，避免反推出错
    id_map = tool_id_map or {}

    # 最多 3 轮工具调用
    for turn in range(3):
        kwargs = dict(
            model=model,
            messages=current_messages,
            temperature=0.0,
            max_tokens=4096,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "required"  # 强制调用工具，避免 LLM 自行计算

        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(**kwargs)
                break
            except Exception as e:
                print(f"[WARN] LLM 调用失败 ({attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    return None, tool_calls_log
                time.sleep(3)

        choice = response.choices[0]
        msg = choice.message

        # 没有工具调用，直接返回文本
        if not msg.tool_calls:
            return msg.content or "", tool_calls_log

        # 有工具调用，执行并追加结果
        current_messages.append(msg.model_dump())

        for tc in msg.tool_calls:
            func_name = tc.function.name
            try:
                arguments = json.loads(tc.function.arguments)
            except Exception:
                arguments = {}

            # 从 tool_id_map 还原 resource_id（避免反推出错）
            resource_id = id_map.get(func_name, func_name)

            result = execute_tool(resource_id, arguments)
            success = result.get("success", False)
            error = result.get("error", "")
            tool_result = result.get("result")
            if success:
                # 只取 result 字段里的数值，避免打印整个 interpretation
                val = tool_result.get("result") if isinstance(tool_result, dict) else tool_result
                print(f"  [TOOL] {resource_id} -> OK | result={val}")
            else:
                print(f"  [TOOL] {resource_id} -> FAIL | {error}")
            tool_calls_log.append({
                "resource_id": resource_id,
                "arguments": arguments,
                "result": tool_result,
                "success": success,
                "error": error or None,
            })

            # 将工具结果追加到消息
            current_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(tool_result or "", ensure_ascii=False)
            })

    # 超过最大轮次，返回最后一条文本
    return msg.content or "", tool_calls_log


# ======================
# 主推理循环
# ======================

def run(model, prompt_style, limit=None):
    if not OPENROUTER_API_KEY:
        print("[ERR] 请设置环境变量 OPENROUTER_API_KEY")
        sys.exit(1)

    # 输出文件名
    model_safe = model.replace("/", "_")
    output_filename = f"{model_safe}_{prompt_style}_toolkit.jsonl"
    output_path = os.path.join("outputs", output_filename)

    os.makedirs("outputs", exist_ok=True)
    os.makedirs("results", exist_ok=True)

    # 加载已有结果（断点续跑）
    existing_keys = set()
    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                    existing_keys.add((str(d["Calculator ID"]), str(d["Note ID"])))
                except Exception:
                    pass
        print(f"[INFO] 已有 {len(existing_keys)} 条结果，跳过")

    # 加载数据
    df = pd.read_csv(DATA_PATH)
    if limit:
        df = df.iloc[:limit]
        print(f"[INFO] 限制处理前 {limit} 行")

    print(f"[INFO] 共 {len(df)} 个实例，模型: {model}，提示: {prompt_style}")
    print(f"[INFO] MToolHub: {MTOOLHUB_URL}，top_k={MTOOLHUB_SEARCH_TOP_K}")

    # 加载 one-shot 示例
    with open(ONE_SHOT_PATH, "r", encoding="utf-8") as f:
        one_shot_json = json.load(f)

    # 推理循环
    for index in tqdm.tqdm(range(len(df))):
        row = df.iloc[index]
        calculator_id = str(row["Calculator ID"])
        note_id = str(row["Note ID"])

        # 断点续跑
        if (calculator_id, note_id) in existing_keys:
            continue

        patient_note = row["Patient Note"]
        question = row["Question"]
        calculator_name = row["Calculator Name"]

        # 搜索相关工具（用计算器名称精确搜索，比病例摘要效果好）
        tools, tool_id_map = search_tools(calculator_name, top_k=MTOOLHUB_SEARCH_TOP_K)
        if tools:
            print(f"[DEBUG] {calculator_name} -> 找到 {len(tools)} 个工具: "
                  f"{[t['function']['name'] for t in tools]}")

        # 构建提示
        if prompt_style == "zero_shot":
            if tools:
                system, user = zero_shot_with_tools(patient_note, question)
            else:
                system, user = zero_shot(patient_note, question)
        elif prompt_style == "one_shot":
            one_shot_question = question
            if calculator_id == "24":
                one_shot_question = "Based on the patient's dose of Hydrocortisone IV, what is the equivalent dosage in mg of Dexamethasone PO?"
            example = one_shot_json[calculator_id]
            system, user = one_shot(
                patient_note, question, one_shot_question,
                example["Patient Note"],
                {"step_by_step_thinking": example["Response"]["step_by_step_thinking"],
                 "answer": example["Response"]["answer"]}
            )
        elif prompt_style == "direct_answer":
            system, user = direct_answer(patient_note, question)
        else:
            print(f"[ERR] 未知 prompt_style: {prompt_style}")
            sys.exit(1)

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ]

        # 调用 LLM（带工具）
        raw_answer, tool_calls_log = call_llm_with_tools(
            model, messages, tools=tools or None, tool_id_map=tool_id_map
        )
        if raw_answer is None:
            raw_answer = ""

        # 提取答案
        try:
            answer_value, explanation = extract_answer(raw_answer, calculator_id)
            correctness = check_correctness(
                answer_value,
                row["Ground Truth Answer"],
                calculator_id,
                row["Upper Limit"],
                row["Lower Limit"]
            )
            status = "Correct" if correctness else "Incorrect"
        except Exception as e:
            answer_value = str(e)
            explanation = str(e)
            status = "Incorrect"

        tool_used = len(tool_calls_log) > 0
        tool_ok = any(t["success"] for t in tool_calls_log)
        print(f"Row {row['Row Number']:>3} | {calculator_name[:40]:<40} | tool={'OK' if tool_ok else 'FAIL' if tool_used else 'NONE'} | {status} (pred={answer_value}, gt={row['Ground Truth Answer']})")

        outputs = {
            "Row Number": int(row["Row Number"]),
            "Calculator Name": calculator_name,
            "Calculator ID": calculator_id,
            "Category": row["Category"],
            "Note ID": note_id,
            "Patient Note": patient_note,
            "Question": question,
            "LLM Answer": answer_value,
            "LLM Explanation": explanation if prompt_style != "direct_answer" else "N/A",
            "Ground Truth Answer": str(row["Ground Truth Answer"]),
            "Ground Truth Explanation": row["Ground Truth Explanation"],
            "Result": status,
        }

        # 记录工具调用信息（额外字段，不影响评估）
        if tool_calls_log:
            outputs["Tools Used"] = tool_calls_log

        with open(output_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(outputs, ensure_ascii=False) + "\n")

    # 统计结果
    print(f"\n[OK] 推理完成，结果保存在 {output_path}")
    stats = compute_overall_accuracy(output_filename, model_safe, f"{prompt_style}_toolkit")
    print("\n[INFO] 准确率统计：")
    for cat, s in stats.items():
        print(f"  {cat}: {s['average']}% (std={s['std']})")


# ======================
# 命令行入口
# ======================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MedCalc-Bench LLM + MToolHub 推理")
    parser.add_argument("--model", type=str, default="z-ai/glm-4.6v",
                        help="OpenRouter 模型 ID，如 z-ai/glm-4.6v")
    parser.add_argument("--prompt", type=str, default="zero_shot",
                        choices=["zero_shot", "one_shot", "direct_answer"],
                        help="提示策略")
    parser.add_argument("--limit", type=int, default=None,
                        help="限制处理行数（如 --limit 50 用于快速验证）")
    parser.add_argument("--mtoolhub-url", type=str, default=None,
                        help="MToolHub 服务地址（默认读取 MTOOLHUB_URL 环境变量，或 http://localhost:8081）")
    parser.add_argument("--top-k", type=int, default=3,
                        help="工具搜索返回数量（默认 3）")
    args = parser.parse_args()

    if args.mtoolhub_url:
        MTOOLHUB_URL = args.mtoolhub_url
    MTOOLHUB_SEARCH_TOP_K = args.top_k

    run(args.model, args.prompt, args.limit)
