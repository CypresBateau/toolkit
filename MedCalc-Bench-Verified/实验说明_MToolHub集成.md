# MedCalc-Bench-Verified + MToolHub 集成实验说明

## 新增文件

| 文件 | 说明 |
|------|------|
| `evaluation/run_vanilla.py` | 裸 LLM 推理脚本，用于复现 baseline，验证 pipeline 与论文对齐 |
| `evaluation/run_toolkit.py` | LLM + MToolHub 工具调用推理脚本，端到端实验 |
| `实验说明_MToolHub集成.md` | 本文档 |

---

## 实验设计

| 实验组 | 脚本 | 工具库 | 目的 |
|--------|------|--------|------|
| Baseline | `run_vanilla.py` | 无 | 复现论文，验证 pipeline 正确性 |
| Experimental | `run_toolkit.py` | MToolHub | 量化工具库带来的准确率提升 |

**控制变量**：相同模型（GLM-4.6V via OpenRouter）、相同提示策略、相同测试数据、相同评估逻辑。唯一变量是是否使用 MToolHub 工具库。

---

## 运行方式

### 前提条件

```bash
# 设置 API Key
export OPENROUTER_API_KEY=sk-or-v1-xxxxx

# 如果跑 toolkit 实验，还需要 MToolHub 服务在运行
# 默认地址 http://localhost:8081，可通过环境变量覆盖
export MTOOLHUB_URL=http://localhost:8081
```

### 第一步：验证 pipeline（limit 50）

```bash
cd evaluation

python run_vanilla.py \
  --model z-ai/glm-4.6v \
  --prompt zero_shot \
  --limit 50
```

跑完后查看 `overall` 准确率，应在 **50% 左右**（论文 GPT-4 最佳为 50.91%），确认 pipeline 与论文对齐后再继续。

### 第二步：全量 Baseline

```bash
python run_vanilla.py \
  --model z-ai/glm-4.6v \
  --prompt zero_shot
```

### 第三步：Toolkit 实验（limit 50 验证）

```bash
python run_toolkit.py \
  --model z-ai/glm-4.6v \
  --prompt zero_shot \
  --limit 50
```

### 第四步：全量 Toolkit 实验

```bash
python run_toolkit.py \
  --model z-ai/glm-4.6v \
  --prompt zero_shot
```

### 可选参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--model` | OpenRouter 模型 ID | `z-ai/glm-4.6v` |
| `--prompt` | 提示策略：`zero_shot` / `one_shot` / `direct_answer` | `zero_shot` |
| `--limit` | 限制处理行数，用于快速验证 | 无限制 |
| `--mtoolhub-url` | MToolHub 服务地址（仅 run_toolkit.py） | `http://localhost:8081` |
| `--top-k` | 工具搜索返回数量（仅 run_toolkit.py） | `3` |

---

## 输出文件

所有输出在 `evaluation/` 目录下：

```
evaluation/
├── outputs/
│   ├── z-ai_glm-4.6v_zero_shot_vanilla.jsonl    # baseline 推理结果
│   └── z-ai_glm-4.6v_zero_shot_toolkit.jsonl    # toolkit 推理结果
└── results/
    ├── results_glm-4.6v_zero_shot_vanilla.json   # baseline 准确率统计
    └── results_glm-4.6v_zero_shot_toolkit.json   # toolkit 准确率统计
```

### JSONL 每行格式

```json
{
  "Row Number": 1,
  "Calculator Name": "Creatinine Clearance (Cockcroft-Gault Equation)",
  "Calculator ID": "2",
  "Category": "lab test",
  "Note ID": "pmc-7671985-1",
  "Patient Note": "...",
  "Question": "...",
  "LLM Answer": "25.24",
  "LLM Explanation": "step-by-step reasoning...",
  "Ground Truth Answer": "25.2381",
  "Ground Truth Explanation": "...",
  "Result": "Correct",
  "Tools Used": [...]   // 仅 toolkit 结果有此字段
}
```

### 准确率统计 JSON 格式

```json
{
  "lab test":  {"average": 55.2, "std": 0.03},
  "physical":  {"average": 62.1, "std": 0.03},
  "date":      {"average": 40.0, "std": 0.06},
  "dosage":    {"average": 45.0, "std": 0.08},
  "risk":      {"average": 48.3, "std": 0.03},
  "severity":  {"average": 51.2, "std": 0.06},
  "diagnosis": {"average": 53.3, "std": 0.06},
  "overall":   {"average": 52.4, "std": 0.02}
}
```

---

## 查看结果

### 快速查看整体准确率

```bash
# Baseline
cat evaluation/results/results_glm-4.6v_zero_shot_vanilla.json | python -m json.tool

# Toolkit
cat evaluation/results/results_glm-4.6v_zero_shot_toolkit.json | python -m json.tool
```

### 对比两组结果

```bash
python -c "
import json

with open('evaluation/results/results_glm-4.6v_zero_shot_vanilla.json') as f:
    baseline = json.load(f)
with open('evaluation/results/results_glm-4.6v_zero_shot_toolkit.json') as f:
    toolkit = json.load(f)

print(f'{'Category':<15} {'Baseline':>10} {'Toolkit':>10} {'Delta':>8}')
print('-' * 45)
for cat in ['lab test','physical','date','dosage','risk','severity','diagnosis','overall']:
    b = baseline.get(cat, {}).get('average', 0)
    t = toolkit.get(cat, {}).get('average', 0)
    print(f'{cat:<15} {b:>9.2f}% {t:>9.2f}% {t-b:>+7.2f}%')
"
```

### 查看工具调用情况（toolkit 结果）

```bash
python -c "
import json

total = tool_used = tool_success = 0
with open('evaluation/outputs/z-ai_glm-4.6v_zero_shot_toolkit.jsonl') as f:
    for line in f:
        d = json.loads(line)
        total += 1
        if d.get('Tools Used'):
            tool_used += 1
            if any(t.get('success') for t in d['Tools Used']):
                tool_success += 1

print(f'总实例数:     {total}')
print(f'工具调用率:   {tool_used/total*100:.1f}% ({tool_used}/{total})')
print(f'工具成功率:   {tool_success/tool_used*100:.1f}% ({tool_success}/{tool_used})' if tool_used else '无工具调用')
"
```

---

## 断点续跑

两个脚本均支持断点续跑。SSH 断开或 API 余额不足后，重新执行**相同命令**即可，已处理的行会自动跳过。

---

## 论文基准参考

| 模型 | 提示策略 | 准确率 |
|------|---------|--------|
| GPT-4 | One-shot CoT | **50.91%** |
| GPT-4 | Zero-shot CoT | 48.00% |
| GPT-3.5 | One-shot CoT | 30.64% |
| Llama-3-70B | One-shot CoT | 40.27% |

GLM-4.6V baseline 跑出来应在 40-55% 范围内视为 pipeline 对齐。

---

## 注意事项

1. `run_toolkit.py` 用**计算器名称**（`Calculator Name` 字段）搜索 MToolHub 工具，而非完整病例文本，搜索精度更高
2. 工具调用记录在 `Tools Used` 字段，不影响评估逻辑，与原始评估脚本完全兼容
3. 评估函数直接复用原始 `evaluate.py`，保证与论文评估标准一致
4. 输出文件名后缀 `_vanilla` / `_toolkit` 自动区分，不会互相覆盖
