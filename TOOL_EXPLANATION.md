# MENTI 医疗工具部署指南

> 本文档面向另一个工程中的 Claude Code，用于在新项目里将 MENTI 的医疗工具封装成 API 服务。

---

## 一、工具概述

MENTI 提供两类医疗工具，均以 **JSON 数组文件** 形式存储，每个工具内嵌可执行的 Python 函数代码。

| 工具库 | 文件 | 数量 | 用途 |
|--------|------|------|------|
| 医疗评分计算器 | `CalcQA/tool_scale.json` | **44 个** | 评估患者健康状态（SOFA、APACHE、ARISCAT 等临床评分） |
| 医疗单位换算器 | `CalcQA/tool_unit.json` | **237 个** | 医学检验单位互转（mmol/L ↔ mg/dL 等） |

---

## 二、工具 JSON 字段结构

### 2.1 scale 工具字段（`tool_scale.json`）

```json
{
  "tool_name":      "ARISCAT Score for Postoperative Pulmonary Complications",
  "function_name":  "calculate_ariscat_score",
  "description":    "The ARISCAT score is a tool used to assess the risk of ...",
  "formula":        "Addition of the selected points:\nVariable\nPoints\nAge...",
  "docstring":      "Calculate the ARISCAT Score...\n\nParameters:\nage (int): ...\n\nReturns:\nint: The ARISCAT score...",
  "code":           "def calculate_ariscat_score(age, spo2, ...):\n    ...",
  "next_steps":     "ADVICE\nMay guide decision-making to reduce risk of..."
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `tool_name` | str | 可读的计算器名称，用于向量检索和 LLM 展示 |
| `function_name` | str | Python 函数名，exec 执行后通过此名调用 |
| `description` | str | 工具用途的详细描述，用于嵌入向量检索 |
| `formula` | str | 人类可读的计算公式/评分规则 |
| `docstring` | str | 函数文档，含参数名、类型、单位、返回值，**是参数提取 prompt 的核心输入** |
| `code` | str | 完整的 Python 函数实现，通过 `exec()` 动态执行 |
| `next_steps` | str | 临床建议（可选展示） |

### 2.2 unit 工具字段（`tool_unit.json`）

```json
{
  "function_name":  "convert_potassium_k_unit",
  "tool_name":      "Potassium (K), 钾 (K)",
  "description":    "Convert Potassium (K) measurements...\nunits list = ['mmol/L', 'mEq/L']",
  "docstring":      "Convert the value of Potassium (K) from input_unit to target_unit...\nParameters:\n  - input_value (float)...\n  - input_unit (int): index in units list\n  - target_unit (int): index in units list",
  "code":           "def convert_potassium_k_unit(input_value, input_unit, target_unit):\n    ..."
}
```

> unit 工具比 scale 工具少一个 `formula` 和 `next_steps` 字段。

---

## 三、工具执行机制（核心逻辑）

### 3.1 工具调用方式

所有工具通过 **`exec()` 动态执行代码字符串** 实现：

```python
import json

def run_tool(tool: dict, arguments: dict):
    """
    tool: 来自 JSON 的工具对象
    arguments: {"param_name": value, ...}  （纯 value 字典，已去除 Unit 层）
    """
    exec(tool["code"])
    func = locals()[tool["function_name"]]
    return func(**arguments)
```

### 3.2 参数格式

LLM 参数提取阶段输出的 JSON 格式（含单位信息）：

```json
{
  "age":                    {"Value": 65,  "Unit": "years"},
  "spo2":                   {"Value": 94,  "Unit": "%"},
  "respiratory_infection":  {"Value": 0,   "Unit": null},
  "anemia":                 {"Value": 1,   "Unit": null},
  "surgical_incision":      {"Value": 1,   "Unit": null},
  "surgery_duration":       {"Value": 2.5, "Unit": "hours"},
  "emergency":              {"Value": 0,   "Unit": null}
}
```

传入 `exec` 前需展开为纯 value 字典：

```python
arguments = {key: value["Value"] for key, value in param_json.items()}
# 得到: {"age": 65, "spo2": 94, "respiratory_infection": 0, ...}
```

### 3.3 工具返回值

- **scale 工具**：返回 `int` 或 `str`，通常是评分数值或带解释的文字结果。
- **unit 工具**：返回 `str`，固定格式为自然语言描述，如 `"140 mmol/L = 140 mEq/L"`。

---

## 四、完整的 5 阶段流水线

```
用户输入（查询 + 病历文本）
        │
        ▼
[1] 初步诊断（LLM）
    Prompt: preliminary_diagnosis_prompt
    输入: 病历文本
    输出: 异常发现分析文字
        │
        ▼
[2] 工具分类 classify（LLM）
    Prompt: metatool_classify_prompt
    输入: 用户查询
    输出: "scale" 或 "unit"
        │
        ▼
[3] 查询改写 rewrite（LLM）
    Prompt: metatool_rewrite_prompt_withtext / _outtext
    输入: 用户查询 + 诊断结果（可选）
    输出: 3 条改写后的检索 query（JSON list）
        │
        ▼
[4] 向量检索 + RRF 排序（Embedding）
    对工具库的 3 种字段组合做嵌入：
      - function_name + tool_name
      - function_name + tool_name + docstring
      - function_name + tool_name + description
    3 query × 3 字段 = 9 个排序列表，RRF 融合 → 最终排序
    输出: 工具索引排序列表
        │
        ▼
[5] LLM 分配 dispatch（LLM）
    Prompt: metatool_dispatch_prompt
    输入: Top-N 候选工具列表（含 tool_name + docstring）
    输出: 选定的 tool_name → 定位到 tool 对象
        │
        ▼
[6] 参数提取 extract（LLM）
    Prompt: configuration_extract_prompt
    输入: tool["docstring"] + 患者病历
    输出: 参数 JSON（含 Value 和 Unit）
        │
        ▼
[7] 单位反思 reflect（LLM）
    Prompt: configuration_reflect_exper_prompt
    输入: tool["docstring"] + 参数 JSON
    输出: {"chosen_decision_name": "calculate"|"toolcall", "supplementary_information": [...]}
        │
        ├─── "calculate" ──────────────────────────────────────────────────────▶ [8]
        │
        └─── "toolcall" ──→ 递归嵌套调用 MetaTool + Configuration（unit 工具）
                            将换算结果追加到 case 文本 → 重新执行 [6][7]
        │
        ▼
[8] 工具执行 calculate
    exec(tool["code"]) → 调用函数 → 返回结果
```

---

## 五、向量检索嵌入模型

| 模型 | 标识符 | 说明 |
|------|--------|------|
| **m3e-base**（默认） | `m3e` | 中文优化，权重路径 `../m3e-base`，用 sentence-transformers 加载 |
| sup-simcse-bert | `simcse` | 英文，用 simcse 库加载 |

加载方式：

```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('../m3e-base')  # 路径相对于项目根目录
embeddings = model.encode(["text1", "text2"])  # 返回 np.ndarray
```

---

## 六、LLM 接口

所有 LLM 调用均为单轮对话（无历史），统一接口：

```python
# OpenAI
from openai import OpenAI
client = OpenAI()  # 需要 OPENAI_API_KEY 环境变量
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": prompt_text}]
)
result = response.choices[0].message.content
```

支持模型：`gpt-3.5-turbo`、`gpt-4o`、`gpt-4`、`chatglm3`（本地）、`bianque`（本地）

---

## 七、LLM 输出解析规范

所有 LLM 输出均用正则从 ` ```json ... ``` ` 代码块中提取：

```python
import re, json

def parse_json_block(llm_output: str) -> dict | list:
    raw = re.findall(r"```json(.*?)```", llm_output, flags=re.DOTALL)[0].strip()
    return json.loads(raw)
```

各阶段输出结构：

| 阶段 | JSON 结构 |
|------|-----------|
| classify | `{"chosen_toolkit_name": "scale" \| "unit"}` |
| rewrite | `["query1", "query2", "query3"]` |
| dispatch | `{"chosen_tool_name": "工具名称（小写匹配）"}` |
| extract | `{"param": {"Value": val, "Unit": "单位或null"}, ...}` |
| reflect | `{"chosen_decision_name": "calculate"\|"toolcall", "supplementary_information": "..."\|[...]}` |


---

## 九、最小化 API 服务的依赖清单

```
openai>=1.0.0
sentence-transformers>=3.0.0
transformers>=4.40.0
torch>=2.0.0
numpy>=1.24.0
retry>=0.9.2
```

GPU 环境建议：CUDA 12.x + cuDNN 9.x（见 `requirements.txt` 中的 `nvidia-*` 包）

---

```

---

## 十一、工具数量汇总

| 文件 | 实际工具数 |
|------|-----------|
| `CalcQA/tool_scale.json` | **44 个**医疗评分计算器 |
| `CalcQA/tool_unit.json` | **237 个**医学单位换算工具 |
| 合计 | **281 个** |


## 十二、工具提取方式
 输入参数怎么判断的 — 解析 docstring 里 Parameters: 到 Returns: 之间的内容，用正则匹配 name (type): description 格式
