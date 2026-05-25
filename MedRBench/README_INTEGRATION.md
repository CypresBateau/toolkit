# MedRBench + MToolHub 集成项目

严格控制变量的对比实验框架，用于评估医疗工具库（MToolHub）对 LLM 临床诊断性能的影响。

## 项目概述

本项目在 MedRBench 基准测试上集成 MToolHub 工具库，通过严格控制变量的实验设计，量化工具库对 LLM 诊断准确率的提升。

**核心问题**: 在相同 LLM 基座下，接入临床工具库能否提升诊断准确率？

**实验设计**:
- **控制变量**: LLM 模型、温度参数、数据集、Prompt 模板
- **自变量**: 是否启用 MToolHub 工具库
- **因变量**: 诊断准确率、工具使用率、响应时间、成本

---

## 快速开始

### 前置条件

1. **Python 环境**: Python 3.8+
2. **Claude API Key**: 从 Anthropic 获取
3. **MToolHub 服务**: 仅 experimental 模式需要（baseline 模式不需要）

### 安装依赖

```bash
cd D:\01_work\toolkit\MedRBench
pip install anthropic httpx pyyaml tqdm pydantic
```

### 设置 API Key

**Windows CMD**:
```bash
set ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
```

**Windows PowerShell**:
```powershell
$env:ANTHROPIC_API_KEY="sk-ant-api03-xxxxx"
```

**Linux/Mac**:
```bash
export ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
```

### 快速验证（10 个病例）

**Windows**:
```bash
scripts\quick_test.bat
```

**Linux/Mac**:
```bash
bash scripts/quick_test.sh
```

这将自动运行：
1. Baseline 测试（10 个病例）
2. Experimental 测试（10 个病例）
3. 生成对比报告

结果保存在 `results/quick_test/` 目录。

---

## 完整实验流程

### 1. 启动 MToolHub 服务（仅 experimental 模式需要）

```bash
cd D:\01_work\AgentHospital\MToolHub\backend
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

验证服务：
```bash
curl http://localhost:8080/api/health
```

### 2. 运行 Baseline 实验

```bash
python src/Inference/one_turn_claude.py \
    --config configs/experiment_config.yaml \
    --mode baseline \
    --output results/baseline_one_turn.json
```

### 3. 运行 Experimental 实验

```bash
python src/Inference/one_turn_claude.py \
    --config configs/experiment_config.yaml \
    --mode experimental \
    --output results/experimental_one_turn.json
```

### 4. 生成对比报告

```bash
python src/Evaluation/compare_results.py \
    --baseline results/baseline_one_turn.json \
    --experimental results/experimental_one_turn.json \
    --output results/comparison_report.json
```

---

## 消融实验

### 只搜索不执行（测试搜索质量）

```bash
python src/Inference/one_turn_claude.py \
    --config configs/experiment_config.yaml \
    --mode ablation.search_only \
    --output results/ablation_search_only.json
```

### 只返回 top-1 工具（测试工具数量影响）

```bash
python src/Inference/one_turn_claude.py \
    --config configs/experiment_config.yaml \
    --mode ablation.top1_only \
    --output results/ablation_top1.json
```

### 使用更强 LLM（测试模型能力影响）

```bash
python src/Inference/one_turn_claude.py \
    --config configs/experiment_config.yaml \
    --mode ablation.different_llm \
    --output results/ablation_opus.json
```

---

## 项目结构

```
MedRBench/
├── configs/
│   └── experiment_config.yaml          # 实验配置文件
├── src/
│   ├── Adapters/
│   │   ├── __init__.py
│   │   └── toolkit_adapter.py          # MToolHub 适配器
│   ├── Inference/
│   │   ├── one_turn_claude.py          # Claude 推理脚本（新增）
│   │   ├── one_turn.py                 # 原始推理脚本（其他模型）
│   │   ├── free_turn.py                # 多轮诊断
│   │   ├── oracle_diagnose.py          # Oracle 诊断
│   │   └── oracle_treatment_planning.py # 治疗规划
│   └── Evaluation/
│       ├── __init__.py
│       ├── toolkit_metrics.py          # 工具库指标计算（新增）
│       └── compare_results.py          # 对比分析（新增）
├── scripts/
│   ├── quick_test.sh                   # Linux/Mac 快速验证
│   └── quick_test.bat                  # Windows 快速验证
├── data/
│   └── MedRBench/
│       ├── diagnosis_957_cases_with_rare_disease_491.json
│       └── treatment_496_cases_with_rare_disease_165.json
├── results/                            # 实验结果目录
├── EXPERIMENT_DESIGN.md                # 完整实验设计文档
├── PHASE1_REPORT.md                    # 阶段 1 完成报告
├── PHASE2_REPORT.md                    # 阶段 2 完成报告
├── README_INTEGRATION.md               # 本文件
└── README.md                           # 原始 MedRBench 文档
```

---

## 配置说明

### 实验模式

配置文件 `configs/experiment_config.yaml` 支持以下模式：

| 模式 | 说明 | 工具库 | 用途 |
|------|------|--------|------|
| `baseline` | LLM 裸跑 | 禁用 | 基线对照组 |
| `experimental` | LLM + 工具库 | 启用（top-3） | 实验组 |
| `ablation.search_only` | 只搜索不执行 | 启用（不执行） | 测试搜索质量 |
| `ablation.top1_only` | 只返回 top-1 | 启用（top-1） | 测试工具数量影响 |
| `ablation.different_llm` | 更强 LLM | 启用（Opus） | 测试模型能力影响 |
| `ablation.top5` | 返回 top-5 | 启用（top-5） | 测试更多候选影响 |

### 修改配置

编辑 `configs/experiment_config.yaml`:

```yaml
experimental:
  mode: experimental
  llm:
    model: claude-sonnet-4-20250514  # 修改模型
    temperature: 0.0                 # 修改温度
  mtoolhub:
    url: http://localhost:8080       # 修改 MToolHub 地址
    search_top_k: 3                  # 修改返回工具数量
    enable_execution: true           # 是否执行工具
```

---

## 输出格式

### 推理结果文件

```json
{
  "config": {
    "mode": "experimental",
    "llm_model": "claude-sonnet-4-20250514",
    "mtoolhub_enabled": true,
    "search_top_k": 3
  },
  "results": [
    {
      "case_id": "case_001",
      "ground_truth": "Deep Vein Thrombosis",
      "prediction": "Deep Vein Thrombosis",
      "correct": true,
      "tools_used": [
        {
          "resource_id": "tool-mdcalc:wells_score_dvt",
          "arguments": {"active_cancer": 1, ...},
          "result": {"score": 3, "risk": "moderate"},
          "success": true
        }
      ],
      "reasoning": "患者有活动性癌症...",
      "response_time": 5.8,
      "tokens_used": 1234
    }
  ],
  "summary": {
    "total_cases": 957,
    "accuracy": 0.82,
    "tool_usage_rate": 0.65,
    "avg_tools_per_case": 1.3,
    "avg_response_time": 6.2,
    "total_tokens": 1234567
  }
}
```

### 对比报告文件

```json
{
  "accuracy_comparison": {
    "baseline": {"accuracy": 0.75},
    "experimental": {"accuracy": 0.82},
    "improvement": {
      "absolute_improvement": 0.07,
      "relative_improvement_pct": 9.33
    }
  },
  "toolkit_usage_comparison": {
    "experimental": {
      "tool_usage_rate": 0.65,
      "avg_tools_per_case": 1.3,
      "top_10_tools": {...}
    }
  },
  "error_analysis": {
    "both_correct": 700,
    "both_wrong": 150,
    "baseline_only_correct": 20,
    "experimental_only_correct": 87,
    "net_improvement": 67
  }
}
```

---

## 查看结果

### 使用 jq 查看 JSON

```bash
# 查看摘要
cat results/baseline.json | jq '.summary'

# 查看准确率
cat results/experimental.json | jq '.summary.accuracy'

# 查看工具使用率
cat results/experimental.json | jq '.summary.tool_usage_rate'

# 查看最常用的工具
cat results/experimental.json | jq '.results[].tools_used[].resource_id' | sort | uniq -c | sort -rn | head -10

# 查看对比报告
cat results/comparison.json | jq '.accuracy_comparison'
```

### 使用 Python 脚本

```bash
# 生成格式化的指标报告
python src/Evaluation/toolkit_metrics.py results/experimental.json

# 生成格式化的对比报告
python src/Evaluation/compare_results.py \
    --baseline results/baseline.json \
    --experimental results/experimental.json
```

---

## 常见问题

### Q1: 运行时报 "ANTHROPIC_API_KEY not set"
**解决**: 确保设置了环境变量，并在同一终端窗口运行脚本。

### Q2: 运行时报 "Connection refused to localhost:8080"
**解决**: 
1. 检查 MToolHub 服务是否启动: `curl http://localhost:8080/api/health`
2. 如果是 baseline 模式，不需要启动 MToolHub

### Q3: Claude 不调用工具
**可能原因**:
1. 搜索返回的工具与病例不相关
2. 病例描述不够明确
3. 工具描述不清晰

**调试方法**: 在 `one_turn_claude.py` 中添加调试输出查看搜索到的工具。

### Q4: 实验成本过高
**建议**:
1. 先用 `--limit 10` 测试
2. 使用 `temperature: 0.0` 确保可复现（不需要多次运行）
3. 考虑使用 Claude Haiku（更便宜但能力稍弱）

### Q5: 如何判断工具库是否有效？
**关键指标**:
- 准确率提升 > 5%（绝对值）
- 净改进 > 0
- 工具使用率 > 30%
- 执行成功率 > 90%

---

## 预期结果

### Baseline 模式
- 工具使用率: 0%
- 准确率: 基准值（如 75%）
- 平均响应时间: ~3-5 秒
- 平均 tokens: ~1000-1500

### Experimental 模式
- 工具使用率: 预期 40-60%
- 准确率: 预期比 baseline 高 5-15%
- 平均响应时间: ~5-8 秒（含工具调用）
- 平均 tokens: ~1500-2500（含工具结果）

---

## 技术栈

- **Python**: 3.8+
- **LLM**: Claude Sonnet 4 / Opus 4（Anthropic）
- **HTTP 客户端**: httpx（异步）
- **配置管理**: PyYAML + Pydantic
- **进度条**: tqdm
- **工具库**: MToolHub（FastAPI + FAISS + PubMedBERT）

---

## 参考文档

- [EXPERIMENT_DESIGN.md](EXPERIMENT_DESIGN.md) - 完整实验设计文档（11 个章节）
- [PHASE1_REPORT.md](PHASE1_REPORT.md) - 阶段 1 完成报告（适配器 + 推理脚本）
- [PHASE2_REPORT.md](PHASE2_REPORT.md) - 阶段 2 完成报告（评估指标 + 对比分析）
- [Claude Function Calling 文档](https://docs.anthropic.com/claude/docs/tool-use)
- [README.md](README.md) - 原始 MedRBench 项目文档

---

## 贡献者

- 项目设计: [Your Name]
- 技术实现: Claude Code (Anthropic)

---

## 许可证

本项目仅用于学术研究，不得用于商业用途。
