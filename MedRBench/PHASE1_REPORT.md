# MedRBench + MToolHub 集成 - 阶段 1 完成报告

## 完成时间
2026-05-24

## 本阶段目标
实现 MedRBench 与 MToolHub 的基础集成，支持严格控制变量的对比实验（LLM vs LLM+Toolkit）。

---

## 已完成工作

### 1. 创建 ToolkitAdapter 适配器层
**文件**: `src/Adapters/toolkit_adapter.py`

**功能**:
- 封装 MToolHub API 调用逻辑
- 支持 baseline 和 experimental 两种模式
- 提供 Claude function calling 格式的工具转换
- 支持异步工具搜索和执行

**核心类**:
```python
class ToolkitAdapter:
    async def get_tools_for_query(query: str) -> List[Dict]:
        # baseline 模式返回空列表
        # experimental 模式调用 MToolHub 搜索 API
    
    async def execute_tool(resource_id: str, arguments: dict) -> Dict:
        # 调用 MToolHub 执行 API
        # 返回执行结果
```

### 2. 创建实验配置系统
**文件**: `configs/experiment_config.yaml`

**支持的配置模式**:
- `baseline` - LLM 裸跑，不提供任何工具
- `experimental` - LLM + MToolHub 完整工具库
- `ablation.search_only` - 只搜索不执行（测试搜索质量）
- `ablation.top1_only` - 只返回 top-1 工具（测试工具数量影响）
- `ablation.different_llm` - 使用更强 LLM（测试模型能力影响）
- `ablation.top5` - 返回 top-5 工具（测试更多候选的影响）

**配置示例**:
```yaml
baseline:
  mode: baseline
  llm:
    model: claude-sonnet-4-20250514
    temperature: 0.0
  mtoolhub:
    enabled: false

experimental:
  mode: experimental
  llm:
    model: claude-sonnet-4-20250514  # 与 baseline 相同
    temperature: 0.0  # 与 baseline 相同
  mtoolhub:
    enabled: true
    url: http://localhost:8080
    search_top_k: 3
    enable_execution: true
```

### 3. 创建 Claude 推理脚本
**文件**: `src/Inference/one_turn_claude.py`

**功能**:
- 单轮诊断任务推理
- 集成 ToolkitAdapter
- 支持 Claude function calling
- 自动处理多轮工具调用
- 记录工具使用统计

**输出格式**:
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
    "total_tokens": 12345
  }
}
```

---

## 技术原理

### 1. 适配器模式（Adapter Pattern）
ToolkitAdapter 作为中间层，将 MToolHub 的 REST API 转换为 MedRBench 推理脚本可以直接使用的接口。这样做的好处：
- **解耦**: MedRBench 推理逻辑不需要知道 MToolHub 的具体实现
- **可测试**: 可以轻松 mock ToolkitAdapter 进行单元测试
- **可扩展**: 未来可以支持其他工具库，只需实现相同接口

### 2. 控制变量实验设计
通过配置文件严格控制实验变量：

**控制变量**（保持一致）:
- LLM 模型: `claude-sonnet-4-20250514`
- 温度参数: `0.0`
- 数据集: 相同的 957 个病例
- Prompt 模板: 相同的系统提示词

**自变量**（唯一变化）:
- baseline: `mtoolhub.enabled = false`
- experimental: `mtoolhub.enabled = true`

这样可以确保性能差异完全来自工具库的引入。

### 3. Claude Function Calling 工作流程

```
1. 用户查询 → ToolkitAdapter.get_tools_for_query()
   ↓
2. MToolHub 语义搜索 → 返回 top-3 相关工具
   ↓
3. 转换为 Claude tools 格式 → 传给 Claude API
   ↓
4. Claude 决定是否调用工具
   ↓
   如果调用 → ToolkitAdapter.execute_tool()
   ↓
   工具结果返回给 Claude → Claude 继续推理
   ↓
5. Claude 输出最终诊断
```

**关键点**:
- Claude 自主决定是否使用工具（不是强制调用）
- 支持多轮工具调用（最多 5 轮）
- 工具名称转换: `tool-mdcalc:wells_score_dvt` → `tool_mdcalc_wells_score_dvt`（Claude 不支持冒号）

### 4. 异步执行
使用 `asyncio` 和 `httpx.AsyncClient` 实现异步 HTTP 请求，提高效率：
- 工具搜索和执行都是异步的
- 支持并发处理多个工具调用
- 使用 `async with` 确保资源正确释放

---

## 使用说明

### 前置条件

1. **启动 MToolHub 服务**（仅 experimental 模式需要）:
```bash
cd D:\01_work\AgentHospital\MToolHub\backend
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

2. **设置 Claude API Key**:
```bash
# Windows CMD
set ANTHROPIC_API_KEY=sk-ant-api03-xxxxx

# Windows PowerShell
$env:ANTHROPIC_API_KEY="sk-ant-api03-xxxxx"

# Git Bash / Linux
export ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
```

3. **安装依赖**:
```bash
cd D:\01_work\toolkit\MedRBench
pip install anthropic httpx pyyaml tqdm pydantic
```

### 运行实验

#### 1. 快速测试（10 个病例）
```bash
cd D:\01_work\toolkit\MedRBench

# Baseline 模式
python src/Inference/one_turn_claude.py \
  --config configs/experiment_config.yaml \
  --mode baseline \
  --output results/test_baseline.json \
  --limit 10

# Experimental 模式
python src/Inference/one_turn_claude.py \
  --config configs/experiment_config.yaml \
  --mode experimental \
  --output results/test_experimental.json \
  --limit 10
```

#### 2. 完整实验（957 个病例）
```bash
# Baseline 模式
python src/Inference/one_turn_claude.py \
  --config configs/experiment_config.yaml \
  --mode baseline \
  --output results/baseline_one_turn.json

# Experimental 模式
python src/Inference/one_turn_claude.py \
  --config configs/experiment_config.yaml \
  --mode experimental \
  --output results/experimental_one_turn.json
```

#### 3. 消融实验
```bash
# 只搜索不执行
python src/Inference/one_turn_claude.py \
  --config configs/experiment_config.yaml \
  --mode ablation.search_only \
  --output results/ablation_search_only.json

# 只返回 top-1 工具
python src/Inference/one_turn_claude.py \
  --config configs/experiment_config.yaml \
  --mode ablation.top1_only \
  --output results/ablation_top1.json

# 使用更强 LLM
python src/Inference/one_turn_claude.py \
  --config configs/experiment_config.yaml \
  --mode ablation.different_llm \
  --output results/ablation_opus.json
```

### 查看结果

```bash
# 查看摘要
cat results/baseline_one_turn.json | jq '.summary'

# 查看第一个病例的详细结果
cat results/experimental_one_turn.json | jq '.results[0]'

# 统计工具使用情况
cat results/experimental_one_turn.json | jq '.results[] | select(.tools_used | length > 0) | .tools_used[].resource_id' | sort | uniq -c
```

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

### 消融实验预期
| 配置 | 预期准确率 | 工具使用率 |
|------|-----------|-----------|
| baseline | 75% | 0% |
| experimental | 85% | 50% |
| search_only | 78% | 0%（搜索但不执行） |
| top1_only | 82% | 45% |
| different_llm (Opus) | 90% | 60% |

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
1. 搜索返回的工具与病例不相关（检查 `input_schema` 是否正确）
2. 病例描述不够明确（Claude 认为不需要工具）
3. 工具描述不清晰（需要改进 MToolHub 的工具描述）

**调试方法**:
```python
# 在 one_turn_claude.py 中添加调试输出
print(f"[DEBUG] 搜索到的工具: {[t['name'] for t in tools]}")
print(f"[DEBUG] Claude 响应: {response.stop_reason}")
```

### Q4: 实验成本过高
**建议**:
1. 先用 `--limit 10` 测试
2. 使用 `temperature: 0.0` 确保可复现（不需要多次运行）
3. 考虑使用 Claude Haiku（更便宜但能力稍弱）

---

## 下一步工作

### 阶段 2: 评估指标模块（计划中）
- [ ] 实现 `src/Evaluation/toolkit_metrics.py`
- [ ] 实现 `src/Evaluation/compare_results.py`
- [ ] 生成对比报告（准确率、工具使用率、成本等）

### 阶段 3: 其他任务类型（计划中）
- [ ] 修改 `free_turn.py` 支持多轮诊断
- [ ] 修改 `oracle_diagnose.py` 支持 Oracle 诊断
- [ ] 修改 `oracle_treatment_planning.py` 支持治疗规划

### 阶段 4: 完整实验（计划中）
- [ ] 运行所有 4 种任务 × 5 种配置 = 20 组实验
- [ ] 生成完整对比报告
- [ ] 撰写论文

---

## 文件清单

### 新建文件
- `src/Adapters/__init__.py` - 适配器模块初始化
- `src/Adapters/toolkit_adapter.py` - MToolHub 适配器（核心）
- `configs/experiment_config.yaml` - 实验配置文件
- `src/Inference/one_turn_claude.py` - Claude 推理脚本
- `PHASE1_REPORT.md` - 本报告

### 依赖的已有文件
- `data/MedRBench/diagnosis_957_cases_with_rare_disease_491.json` - 病例数据
- `MToolHub/backend/` - MToolHub 后端服务（需单独启动）

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

- [EXPERIMENT_DESIGN.md](EXPERIMENT_DESIGN.md) - 完整实验设计文档
- [Claude Function Calling 文档](https://docs.anthropic.com/claude/docs/tool-use)
- [MToolHub API 文档](../AgentHospital/MToolHub/backend/README.md)
