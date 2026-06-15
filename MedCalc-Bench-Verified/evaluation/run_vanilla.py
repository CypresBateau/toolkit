"""
run_vanilla.py - 裸 LLM 推理脚本（无工具）

基于原始 run.py，改用 OpenRouter 接口（OpenAI 兼容），支持 GLM-4.6V 等模型。
用途：验证 pipeline 与论文对齐（limit 50 跑出来应在 50% 左右）

运行方式：
    export OPENROUTER_API_KEY=sk-or-v1-xxxxx

    # limit 50 验证
    python run_vanilla.py --model z-ai/glm-4.6v --prompt zero_shot --limit 50

    # 全量
    python run_vanilla.py --model z-ai/glm-4.6v --prompt zero_shot
"""

import re
import os
import sys
import json
import math
import tqdm
import argparse
import numpy as np
import pandas as pd
from openai import OpenAI
from evaluate import check_correctness
from table_stats import compute_overall_accuracy

# ======================
# 配置
# ======================

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

DATA_PATH = "../datasets/test_data.csv"
ONE_SHOT_PATH = "one_shot_finalized_explanation.json"


# ======================
# 提示词构建（与原始 run.py 完全相同）
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
# 答案提取（与原始 run.py 完全相同）
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
# LLM 调用（OpenRouter）
# ======================

def call_llm(model, messages, max_retries=3):
    """通过 OpenRouter 调用 LLM"""
    if not OPENROUTER_API_KEY:
        raise ValueError("[ERR] 请设置环境变量 OPENROUTER_API_KEY")

    client = OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
        default_headers={
            "HTTP-Referer": "https://github.com/MedCalc-Bench",
            "X-Title": "MedCalc-Bench-Vanilla"
        }
    )

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.0,
                max_tokens=4096,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"[WARN] LLM 调用失败 ({attempt + 1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                return None
            import time
            time.sleep(3)

    return None


# ======================
# 主推理循环
# ======================

def run(model, prompt_style, limit=None):
    if not OPENROUTER_API_KEY:
        print("[ERR] 请设置环境变量 OPENROUTER_API_KEY")
        sys.exit(1)

    # 输出文件名
    model_safe = model.replace("/", "_")
    output_filename = f"{model_safe}_{prompt_style}_vanilla.jsonl"
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

        # 构建提示
        if prompt_style == "zero_shot":
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

        # 调用 LLM
        raw_answer = call_llm(model, messages)
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

        outputs = {
            "Row Number": int(row["Row Number"]),
            "Calculator Name": row["Calculator Name"],
            "Calculator ID": calculator_id,
            "Category": row["Category"],
            "Note ID": note_id,
            "Patient Note": patient_note,
            "Question": question,
            "LLM Answer": answer_value,
            "LLM Explanation": explanation if prompt_style != "direct_answer" else "N/A",
            "Ground Truth Answer": str(row["Ground Truth Answer"]),
            "Ground Truth Explanation": row["Ground Truth Explanation"],
            "Result": status
        }

        with open(output_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(outputs, ensure_ascii=False) + "\n")

    # 统计结果
    print(f"\n[OK] 推理完成，结果保存在 {output_path}")
    stats = compute_overall_accuracy(output_path, model_safe, f"{prompt_style}_vanilla")
    print("\n[INFO] 准确率统计：")
    for cat, s in stats.items():
        print(f"  {cat}: {s['average']}% (std={s['std']})")


# ======================
# 命令行入口
# ======================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MedCalc-Bench 裸 LLM 推理（OpenRouter）")
    parser.add_argument("--model", type=str, default="z-ai/glm-4.6v",
                        help="OpenRouter 模型 ID，如 z-ai/glm-4.6v")
    parser.add_argument("--prompt", type=str, default="zero_shot",
                        choices=["zero_shot", "one_shot", "direct_answer"],
                        help="提示策略")
    parser.add_argument("--limit", type=int, default=None,
                        help="限制处理行数（如 --limit 50 用于快速验证）")
    args = parser.parse_args()

    run(args.model, args.prompt, args.limit)
