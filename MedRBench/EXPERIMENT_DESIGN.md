# MedRBench + MToolHub 实验设计文档

## 1. 实验目标

通过严格控制变量的对比实验，量化 MToolHub 工具库对临床诊断和治疗规划任务的性能增益。

**核心研究问题**：
- 在相同 LLM 基座下，接入临床工具库能否提升诊断准确率？
- 工具库对不同任务类型（单轮/多轮/Oracle）的增益是否一致？
- 哪些因素影响工具库的有效性（搜索质量、工具数量、LLM 能力等）？

---

## 2. 实验设计

### 2.1 控制变量设计

**自变量**（唯一变化）：
- **Baseline 组**：LLM 裸跑，不提供任何工具
- **Experimental 组**：LLM + MToolHub 工具库（可搜索和调用 1200+ 临床工具）

**控制变量**（保持一致）：
- LLM 模型：`claude-sonnet-4-20250514`
- 温度参数：`0.0`（确保可复现）
- 数据集：相同的 MedRBench 病例
- Prompt 模板：相同的任务指令
- 评估指标：相同的评分标准

### 2.2 实验组设置

所有实验默认通过 **OpenRouter** 调用 LLM（OpenAI 兼容接口），无需直接申请 Anthropic API Key。

| 组别 | 模式 | 工具库 | 搜索 top-k | 执行 | 说明 | 默认模型 |
|------|------|---------|-----------|------|------|---------|
| Baseline | baseline | 禁用 | - | - | LLM 裸跑 | anthropic/claude-sonnet-4-5 |
| Experimental | experimental | 启用 | 3 | 启用 | 完整工具库 | anthropic/claude-sonnet-4-5 |
| Ablation-1 | search_only | 启用 | 3 | 禁用 | 仅搜索不执行 | anthropic/claude-sonnet-4-5 |
| Ablation-2 | top1_only | 启用 | 1 | 启用 | 仅 top-1 工具 | anthropic/claude-sonnet-4-5 |
| Ablation-3 | different_llm | 启用 | 3 | 启用 | 更强 LLM（Opus） | anthropic/claude-opus-4-5 |
| Ablation-4 | top5 | 启用 | 5 | 启用 | 返回 top-5 工具 | anthropic/claude-sonnet-4-5 |

**切换其他模型**：只需修改 `configs/experiment_config.yaml` 中对应组别的 `model` 字段，无需改代码。OpenRouter 支持 Claude、GPT-4、Gemini、Llama 等主流模型，详见第 12 节。

### 2.3 任务类型覆盖

| 任务类型 | 数据集 | 病例数 | 评估指标 |
|---------|--------|--------|---------|
| 单轮诊断 | diagnosis_957_cases | 957 | 诊断准确率、推理质量 |
| 多轮诊断 | diagnosis_957_cases | 957 | 诊断准确率、对话轮数 |
| Oracle 诊断 | diagnosis_957_cases | 957 | 推理质量、证据使用 |
| Oracle 治疗 | treatment_496_cases | 496 | 治疗方案合理性、安全性 |

**总计**：4 任务 × 5 组别 = 20 组实验

---

## 3. 技术架构

### 3.1 系统架构图

```
MedRBench 推理脚本（保持不变）
    ↓
ToolkitAdapter（新增适配层）
    ├── baseline 模式 → 返回空工具列表
    └── experimental 模式 → 调用 MToolHub API
        ↓
MToolHub Backend（已有服务）
    ├── /api/tools/search → 语义搜索工具
    ├── /api/execute → 执行工具调用
    └── FAISS 索引（1201 个资源）
        ↓
Gateway（已有服务）
    ├── tool-mdcalc（871 个计算器）
    ├── tool-unit（237 个单位换算）
    ├── tool-skills（54 个医疗技能）
    └── mavl（胸片分析模型）
```

### 3.2 ToolkitAdapter 接口设计

```python
class ToolkitAdapter:
    """MToolHub 工具库适配器"""
    
    async def get_tools_for_query(self, query: str) -> List[ClaudeTool]:
        """
        根据查询获取相关工具（Claude function calling 格式）
        
        Args:
            query: 病例描述或诊断问题
        
        Returns:
            Claude tools 列表（baseline 模式返回空列表）
        """
    
    async def execute_tool(self, resource_id: str, arguments: dict) -> dict:
        """
        执行工具调用
        
        Args:
            resource_id: 工具 ID（如 "tool-mdcalc:wells_score_dvt"）
            arguments: 工具参数
        
        Returns:
            执行结果（包含 success、result、trace 字段）
        """
```

### 3.3 配置文件结构

配置文件位于 `configs/experiment_config.yaml`，通过 `provider`、`model`、`api_base_url`、`api_key_env` 四个字段控制 LLM 来源。

**三种 provider 说明**：

| provider | 接口 | 需要的环境变量 | model 格式示例 |
|----------|------|--------------|--------------|
| `openrouter` | OpenRouter（推荐） | `OPENROUTER_API_KEY` | `anthropic/claude-sonnet-4-5` |
| `anthropic` | Anthropic 直连 | `ANTHROPIC_API_KEY` | `claude-sonnet-4-20250514` |
| `openai_compatible` | 任意 OpenAI 兼容接口 | 自定义（`api_key_env` 指定） | 取决于服务 |

```yaml
# configs/experiment_config.yaml

baseline:
  mode: baseline
  llm:
    provider: openrouter                        # 使用 OpenRouter
    model: anthropic/claude-sonnet-4-5          # OpenRouter 格式的模型名
    temperature: 0.0
    max_tokens: 4096
    api_base_url: https://openrouter.ai/api/v1  # OpenRouter 接口地址
    api_key_env: OPENROUTER_API_KEY             # 读取 API Key 的环境变量名
  mtoolhub:
    enabled: false

experimental:
  mode: experimental
  llm:
    provider: openrouter
    model: anthropic/claude-sonnet-4-5
    temperature: 0.0
    max_tokens: 4096
    api_base_url: https://openrouter.ai/api/v1
    api_key_env: OPENROUTER_API_KEY
  mtoolhub:
    enabled: true
    url: http://localhost:8080
    search_top_k: 3
    enable_execution: true
    timeout: 30

ablation:
  search_only:
    mode: experimental
    llm:
      provider: openrouter
      model: anthropic/claude-sonnet-4-5
      temperature: 0.0
      max_tokens: 4096
      api_base_url: https://openrouter.ai/api/v1
      api_key_env: OPENROUTER_API_KEY
    mtoolhub:
      enabled: true
      search_top_k: 3
      enable_execution: false  # 关键：只搜索不执行

  top1_only:
    mode: experimental
    llm:
      provider: openrouter
      model: anthropic/claude-sonnet-4-5
      temperature: 0.0
      max_tokens: 4096
      api_base_url: https://openrouter.ai/api/v1
      api_key_env: OPENROUTER_API_KEY
    mtoolhub:
      enabled: true
      search_top_k: 1  # 关键：只返回 top-1
      enable_execution: true

  different_llm:
    mode: experimental
    llm:
      provider: openrouter
      model: anthropic/claude-opus-4-5          # 关键：更强模型
      temperature: 0.0
      max_tokens: 4096
      api_base_url: https://openrouter.ai/api/v1
      api_key_env: OPENROUTER_API_KEY
    mtoolhub:
      enabled: true
      search_top_k: 3
      enable_execution: true
```

**切换到 GPT-4 或其他模型**：只需修改 `model` 字段，其余不变。详见第 12 节。

---

## 4. 实验流程

### 4.1 准备阶段

```bash
# 1. 设置 OpenRouter API Key（推荐方式）
# Windows CMD:
set OPENROUTER_API_KEY=sk-or-v1-xxxxx
# Windows PowerShell:
$env:OPENROUTER_API_KEY="sk-or-v1-xxxxx"
# Linux/Mac:
export OPENROUTER_API_KEY=sk-or-v1-xxxxx

# 如果使用 Anthropic 直连（可选）：
# set ANTHROPIC_API_KEY=sk-ant-api03-xxxxx

# 2. 启动 MToolHub 服务
cd /data/wxb/toolkit/MToolHub/backend
uvicorn app.main:app --host 0.0.0.0 --port 8080

# 3. 验证服务可用性
curl http://localhost:8080/api/health
curl http://localhost:8080/api/tools | jq '.count'  # 应返回 1201

# 4. 修复中文描述问题（首次运行）
python scripts/enrich_descriptions.py
python scripts/build_index.py

# 5. 验证搜索功能
curl "http://localhost:8080/api/tools/search?q=Wells+DVT&top_k=3" | jq
```

### 4.2 实验执行

```bash
cd D:\01_work\toolkit\MedRBench

# 单轮诊断任务
python src/Inference/one_turn.py \
  --config configs/experiment_config.yaml \
  --mode baseline \
  --output results/one_turn_baseline.json

python src/Inference/one_turn.py \
  --config configs/experiment_config.yaml \
  --mode experimental \
  --output results/one_turn_experimental.json

# 多轮诊断任务
python src/Inference/free_turn.py \
  --config configs/experiment_config.yaml \
  --mode baseline \
  --output results/free_turn_baseline.json

python src/Inference/free_turn.py \
  --config configs/experiment_config.yaml \
  --mode experimental \
  --output results/free_turn_experimental.json

# Oracle 诊断任务
python src/Inference/oracle_diagnose.py \
  --config configs/experiment_config.yaml \
  --mode baseline \
  --output results/oracle_diagnose_baseline.json

python src/Inference/oracle_diagnose.py \
  --config configs/experiment_config.yaml \
  --mode experimental \
  --output results/oracle_diagnose_experimental.json

# Oracle 治疗任务
python src/Inference/oracle_treatment_planning.py \
  --config configs/experiment_config.yaml \
  --mode baseline \
  --output results/oracle_treatment_baseline.json

python src/Inference/oracle_treatment_planning.py \
  --config configs/experiment_config.yaml \
  --mode experimental \
  --output results/oracle_treatment_experimental.json

# 消融实验（以单轮诊断为例）
python src/Inference/one_turn.py \
  --config configs/experiment_config.yaml \
  --mode ablation.search_only \
  --output results/one_turn_search_only.json

python src/Inference/one_turn.py \
  --config configs/experiment_config.yaml \
  --mode ablation.top1_only \
  --output results/one_turn_top1.json

python src/Inference/one_turn.py \
  --config configs/experiment_config.yaml \
  --mode ablation.different_llm \
  --output results/one_turn_opus.json
```

### 4.3 评估阶段

```bash
# 对比 baseline vs experimental
python src/Evaluation/compare_results.py \
  --baseline results/one_turn_baseline.json \
  --experimental results/one_turn_experimental.json \
  --output results/one_turn_comparison.json

# 生成完整报告
python src/Evaluation/generate_report.py \
  --results_dir results/ \
  --output report.html
```

---

## 5. 评估指标

### 5.1 原有 MedRBench 指标

**诊断任务**：
- **Exact Match Accuracy**：完全匹配准确率
- **Top-3 Recall**：前 3 个候选中包含正确诊断的比例
- **Reasoning Quality**：推理过程的连贯性和逻辑性（人工评分）
- **Evidence Usage**：是否正确使用病例中的证据

**治疗任务**：
- **Guideline Adherence**：治疗方案是否符合临床指南
- **Safety Score**：治疗方案的安全性评分
- **Completeness**：治疗方案的完整性（是否覆盖所有必要环节）

### 5.2 新增工具库指标

**工具使用统计**：
- **Tool Usage Rate**：使用工具的病例比例
- **Avg Tools Per Case**：每个病例平均调用的工具数
- **Tool Selection Accuracy**：选择的工具是否与病例相关（人工标注）
- **Execution Success Rate**：工具调用成功率

**性能指标**：
- **Avg Response Time**：平均响应时间（含工具调用）
- **API Cost**：Claude API 调用成本（tokens）

**增益分析**：
- **Accuracy Gain**：experimental 相对 baseline 的准确率提升
- **Reasoning Improvement**：推理质量改善程度
- **Error Reduction**：错误诊断减少比例

---

## 6. 预期结果

### 6.1 主要假设

**H1**：接入工具库后，诊断准确率显著提升（预期 +5% ~ +15%）

**H2**：工具库对复杂病例（罕见病、多症状）的增益更明显

**H3**：多轮诊断任务中，工具库能减少对话轮数（更快收敛）

**H4**：Oracle 任务中，工具库能提升推理质量（更多证据支持）

### 6.2 消融实验预期

| 配置 | 预期准确率 | 说明 |
|------|-----------|------|
| Baseline | 基准值 | LLM 裸跑 |
| Experimental | 基准值 + 10% | 完整工具库 |
| Search Only | 基准值 + 3% | 仅搜索提供上下文，无执行 |
| Top-1 Only | 基准值 + 6% | 工具数量限制影响性能 |
| Opus | 基准值 + 15% | 更强 LLM 更好利用工具 |

### 6.3 失败场景分析

**可能导致工具库无增益的情况**：
1. 搜索质量差（中文描述未翻译、Embedding 模型不匹配）
2. LLM 不调用工具（prompt 引导不足、模型能力限制）
3. 工具覆盖不足（病例需要的工具不在库中）
4. 执行失败（参数提取错误、Gateway 超时）

---

## 7. 实施计划

### 7.1 开发任务（预计 3-5 天）

**Phase 1：适配器开发**（1 天）
- [ ] 实现 `ToolkitAdapter` 类
- [ ] 实现配置加载逻辑
- [ ] 编写单元测试

**Phase 2：推理脚本修改**（1 天）
- [ ] 修改 `one_turn.py`
- [ ] 修改 `free_turn.py`
- [ ] 修改 `oracle_diagnose.py`
- [ ] 修改 `oracle_treatment_planning.py`

**Phase 3：评估指标扩展**（1 天）
- [ ] 实现 `toolkit_metrics.py`
- [ ] 实现 `compare_results.py`
- [ ] 实现 `generate_report.py`

**Phase 4：小样本验证**（1 天）
- [ ] 在 10 个病例上测试 baseline vs experimental
- [ ] 验证工具调用流程
- [ ] 修复发现的问题

**Phase 5：完整实验**（1 天）
- [ ] 运行所有 20 组实验
- [ ] 生成对比报告
- [ ] 分析结果并撰写论文

### 7.2 风险缓解

| 风险 | 缓解措施 |
|------|---------|
| MToolHub 服务不稳定 | 添加重试机制（最多 3 次）；记录失败病例 |
| 工具搜索不准确 | 先运行 `enrich_descriptions.py` 修复中文描述 |
| LLM 不调用工具 | 在 prompt 中明确引导："如需计算临床评分，请使用提供的工具" |
| 实验成本过高 | 先在 50 个病例上验证；使用缓存避免重复调用 |
| 评估指标不全面 | 人工抽查 50 个病例，补充定性分析 |

---

## 8. 数据记录规范

### 8.1 输出文件格式

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
          "arguments": {"active_cancer": 1, "paralysis": 0, ...},
          "result": {"score": 3, "risk": "moderate"},
          "execution_time": 1.2
        }
      ],
      "reasoning": "患者有活动性癌症和小腿肿胀，Wells 评分为 3 分...",
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
    "total_cost": 12.34
  }
}
```

### 8.2 日志记录

```python
# 每次工具调用都记录到日志
logger.info(f"[TOOL_CALL] case={case_id}, resource={resource_id}, args={arguments}")
logger.info(f"[TOOL_RESULT] case={case_id}, success={success}, result={result}")
logger.error(f"[TOOL_ERROR] case={case_id}, error={error_message}")
```

---

## 9. 论文撰写大纲

### 9.1 标题

**"Enhancing Clinical Reasoning with Tool-Augmented Large Language Models: A Benchmark Study on MedRBench"**

### 9.2 摘要

- 背景：LLM 在临床推理中的应用
- 问题：缺乏系统性评估工具库对 LLM 性能的影响
- 方法：在 MedRBench 上对比 LLM vs LLM+Toolkit
- 结果：工具库显著提升诊断准确率（+X%）
- 结论：工具增强是提升 LLM 临床应用的有效途径

### 9.3 章节结构

1. **Introduction**
   - LLM 在医疗领域的应用现状
   - 工具增强 LLM 的必要性
   - 研究问题和贡献

2. **Related Work**
   - 医疗 LLM 基准测试（MedQA、MedMCQA、MedRBench）
   - 工具增强 LLM（ReAct、Toolformer、Function Calling）
   - 临床决策支持系统

3. **Method**
   - MToolHub 工具库架构
   - ToolkitAdapter 设计
   - 实验设置（控制变量、任务类型、评估指标）

4. **Results**
   - 主实验结果（4 任务 × baseline vs experimental）
   - 消融实验结果（搜索 vs 执行、top-1 vs top-3、不同 LLM）
   - 工具使用分析（使用率、选择准确率、失败原因）

5. **Discussion**
   - 工具库增益的来源分析
   - 失败案例分析
   - 局限性和未来工作

6. **Conclusion**
   - 主要发现总结
   - 对临床 AI 应用的启示

---

## 10. 附录

### 10.1 环境依赖

```txt
# MedRBench 原有依赖
tqdm>=4.65.0
pandas>=2.0.0
numpy>=1.24.0

# LLM SDK（两者都装，代码会根据 provider 自动选择）
anthropic>=0.39.0      # provider: anthropic 时使用
openai>=1.0.0          # provider: openrouter / openai_compatible 时使用

# 新增依赖
httpx>=0.25.0          # 调用 MToolHub API（异步）
pyyaml>=6.0            # 加载配置文件
pydantic>=2.0.0        # 配置数据模型
pytest>=7.4.0          # 单元测试
```

### 10.2 快速开始

```bash
# 1. 进入项目目录（远程主机）
cd /data/wxb/toolkit/MedRBench

# 2. 安装依赖
pip install anthropic openai httpx pyyaml pydantic tqdm

# 3. 配置 OpenRouter API Key
export OPENROUTER_API_KEY=sk-or-v1-xxxxx

# 4. 启动 MToolHub（experimental 模式需要）
cd /data/wxb/toolkit/MToolHub/backend
uvicorn app.main:app --port 8080 &

# 5. 运行小样本测试（10 个病例）
cd /data/wxb/toolkit/MedRBench
python src/Inference/one_turn_claude.py \
  --config configs/experiment_config.yaml \
  --mode baseline \
  --limit 10 \
  --output results/test_baseline.json

python src/Inference/one_turn_claude.py \
  --config configs/experiment_config.yaml \
  --mode experimental \
  --limit 10 \
  --output results/test_experimental.json

# 6. 查看对比结果
python src/Evaluation/compare_results.py \
  --baseline results/test_baseline.json \
  --experimental results/test_experimental.json
```

### 10.3 常见问题

**Q1: MToolHub 搜索不到相关工具？**
- 检查是否运行了 `enrich_descriptions.py` 翻译中文描述
- 检查是否重建了 FAISS 索引（`build_index.py`）
- 尝试调整 `search_top_k` 参数

**Q2: LLM 不调用工具？**
- 检查 prompt 是否明确引导使用工具
- 检查 `tools` 参数是否正确传递给 Claude API
- 尝试使用更强的模型（Opus）

**Q3: 工具执行失败？**
- 检查 MToolHub 服务是否正常运行
- 检查 Gateway 服务是否正常运行
- 查看日志中的错误信息

**Q4: 实验成本过高？**
- 先在小样本（10-50 个病例）上验证
- 使用缓存机制避免重复调用
- 考虑使用本地模型（如 Llama-3-70B）

---

## 12. 多模型测试指南（通过 OpenRouter）

### 12.1 为什么用 OpenRouter

OpenRouter 是一个统一的 LLM API 代理，支持 100+ 模型，使用 OpenAI 兼容接口。优势：
- 一个 API Key 访问 Claude、GPT-4、Gemini、Llama 等所有主流模型
- 无需分别申请各家 API Key
- 统一的计费和用量管理
- 注册地址：https://openrouter.ai

### 12.2 常用模型名称对照表

| 模型 | OpenRouter model 字段 | 说明 |
|------|----------------------|------|
| Claude Sonnet 4.5 | `anthropic/claude-sonnet-4-5` | 默认推荐，性价比高 |
| Claude Opus 4.5 | `anthropic/claude-opus-4-5` | 最强 Claude，成本较高 |
| Claude Haiku 4.5 | `anthropic/claude-haiku-4-5` | 最快最便宜，能力稍弱 |
| GPT-4o | `openai/gpt-4o` | OpenAI 旗舰模型 |
| GPT-4o mini | `openai/gpt-4o-mini` | GPT-4 系列中最便宜 |
| GPT-4 Turbo | `openai/gpt-4-turbo` | 旧版 GPT-4 Turbo |
| Gemini 1.5 Pro | `google/gemini-pro-1.5` | Google 旗舰模型 |
| Gemini Flash 1.5 | `google/gemini-flash-1.5` | Google 快速版 |
| Llama 3.1 70B | `meta-llama/llama-3.1-70b-instruct` | 开源模型，免费额度 |
| Llama 3.1 405B | `meta-llama/llama-3.1-405b-instruct` | 最大开源模型 |
| Qwen 2.5 72B | `qwen/qwen-2.5-72b-instruct` | 阿里开源模型 |
| DeepSeek V3 | `deepseek/deepseek-chat` | 国产高性价比模型 |

完整模型列表：https://openrouter.ai/models

### 12.3 切换模型的操作步骤

**只需修改 `configs/experiment_config.yaml` 中的 `model` 字段**，其他配置不变。

**示例：将 baseline 切换为 GPT-4o**

```yaml
baseline:
  mode: baseline
  llm:
    provider: openrouter
    model: openai/gpt-4o          # 改这一行
    temperature: 0.0
    max_tokens: 4096
    api_base_url: https://openrouter.ai/api/v1
    api_key_env: OPENROUTER_API_KEY
  mtoolhub:
    enabled: false
```

**示例：消融实验 different_llm 改用 GPT-4o**

```yaml
ablation:
  different_llm:
    mode: experimental
    llm:
      provider: openrouter
      model: openai/gpt-4o        # 改这一行
      temperature: 0.0
      max_tokens: 4096
      api_base_url: https://openrouter.ai/api/v1
      api_key_env: OPENROUTER_API_KEY
    mtoolhub:
      enabled: true
      url: http://localhost:8080
      search_top_k: 3
      enable_execution: true
```

### 12.4 跨模型对比实验

如果要对比多个模型（如 Claude vs GPT-4 vs Gemini），建议在 `ablation` 下新增配置节：

```yaml
ablation:
  # 原有消融实验...

  # 跨模型对比
  gpt4o_baseline:
    mode: baseline
    llm:
      provider: openrouter
      model: openai/gpt-4o
      temperature: 0.0
      max_tokens: 4096
      api_base_url: https://openrouter.ai/api/v1
      api_key_env: OPENROUTER_API_KEY
    mtoolhub:
      enabled: false

  gpt4o_experimental:
    mode: experimental
    llm:
      provider: openrouter
      model: openai/gpt-4o
      temperature: 0.0
      max_tokens: 4096
      api_base_url: https://openrouter.ai/api/v1
      api_key_env: OPENROUTER_API_KEY
    mtoolhub:
      enabled: true
      url: http://localhost:8080
      search_top_k: 3
      enable_execution: true

  gemini_baseline:
    mode: baseline
    llm:
      provider: openrouter
      model: google/gemini-pro-1.5
      temperature: 0.0
      max_tokens: 4096
      api_base_url: https://openrouter.ai/api/v1
      api_key_env: OPENROUTER_API_KEY
    mtoolhub:
      enabled: false
```

运行命令：

```bash
# 运行 GPT-4o baseline
python src/Inference/one_turn_claude.py \
  --config configs/experiment_config.yaml \
  --mode ablation.gpt4o_baseline \
  --output results/gpt4o_baseline.json

# 运行 GPT-4o experimental
python src/Inference/one_turn_claude.py \
  --config configs/experiment_config.yaml \
  --mode ablation.gpt4o_experimental \
  --output results/gpt4o_experimental.json

# 对比
python src/Evaluation/compare_results.py \
  --baseline results/gpt4o_baseline.json \
  --experimental results/gpt4o_experimental.json \
  --output results/gpt4o_comparison.json
```

### 12.5 注意事项

1. **工具调用兼容性**：并非所有模型都支持 function calling。OpenRouter 上支持工具调用的模型包括：Claude 全系列、GPT-4 全系列、Gemini 1.5 Pro/Flash、Llama 3.1（部分版本）。使用前确认模型支持。

2. **模型名称格式**：OpenRouter 使用 `provider/model-name` 格式，与 Anthropic 直连的 `claude-sonnet-4-20250514` 格式不同。

3. **成本差异**：不同模型价格差异较大。建议先用 `--limit 10` 小样本测试，确认效果后再跑完整实验。

4. **温度参数**：保持 `temperature: 0.0` 确保实验可复现，不同模型在相同温度下行为可能有差异。

5. **max_tokens**：部分模型（如 Gemini）对 max_tokens 的解释不同，如遇截断问题可适当调大。

- 项目负责人：[Your Name]
- 邮箱：[your.email@example.com]
- 代码仓库：[GitHub URL]
- 问题反馈：[GitHub Issues URL]
