# MedRBench + MToolHub 集成 - 阶段 2 完成报告

## 完成时间
2026-05-24

## 本阶段目标
实现评估指标模块和对比分析工具，支持量化工具库的性能增益。

---

## 已完成工作

### 1. 实现工具库指标计算模块
**文件**: `src/Evaluation/toolkit_metrics.py`

**功能**:
- 计算工具使用率（使用了至少一个工具的病例比例）
- 计算平均每病例工具数
- 计算执行成功率（所有工具调用中成功的比例）
- 统计响应时间和 token 使用量
- 分析工具使用分布（哪些工具最常用）
- 估算 API 成本

**核心函数**:
```python
def calculate_toolkit_metrics(results: List[Dict]) -> Dict:
    # 返回工具库使用相关的所有指标
    
def calculate_accuracy_metrics(results: List[Dict]) -> Dict:
    # 返回准确率相关指标
    
def calculate_cost_metrics(results: List[Dict], model: str) -> Dict:
    # 返回成本估算
    
def generate_metrics_report(result_file: str, output_file: str) -> Dict:
    # 从结果文件生成完整指标报告
```

**输出指标**:
```json
{
  "accuracy": {
    "total_cases": 957,
    "correct_cases": 789,
    "accuracy": 0.82
  },
  "toolkit": {
    "tool_usage_rate": 0.65,
    "avg_tools_per_case": 1.3,
    "execution_success_rate": 0.95,
    "avg_response_time": 6.2,
    "total_tokens": 1234567,
    "top_10_tools": {
      "tool-mdcalc:wells_score_dvt": 45,
      "tool-mdcalc:chads_vasc_score": 32,
      ...
    }
  },
  "cost": {
    "total_tokens": 1234567,
    "estimated_cost_usd": 12.34,
    "cost_per_case_usd": 0.0129
  }
}
```

### 2. 实现对比分析脚本
**文件**: `src/Evaluation/compare_results.py`

**功能**:
- 对比 baseline 和 experimental 的准确率
- 计算绝对改进和相对改进
- 对比工具库使用情况
- 对比性能指标（响应时间、tokens）
- 对比成本
- 分析错误病例（哪些病例因工具库而改进/退化）

**核心函数**:
```python
def compare_accuracy(baseline_results, experimental_results) -> Dict:
    # 对比准确率并计算改进幅度
    
def compare_toolkit_usage(baseline_results, experimental_results) -> Dict:
    # 对比工具库使用情况
    
def compare_performance(baseline_results, experimental_results) -> Dict:
    # 对比响应时间和 tokens
    
def analyze_error_cases(baseline_results, experimental_results) -> Dict:
    # 分析错误病例分布
```

**对比报告格式**:
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
  "error_analysis": {
    "both_correct": 700,
    "both_wrong": 150,
    "baseline_only_correct": 20,
    "experimental_only_correct": 87,
    "net_improvement": 67
  }
}
```

### 3. 创建快速验证脚本
**文件**: 
- `scripts/quick_test.sh` (Linux/Mac)
- `scripts/quick_test.bat` (Windows)

**功能**:
- 一键运行 baseline + experimental 测试（10 个病例）
- 自动生成对比报告
- 检查环境变量和服务状态
- 适合快速验证集成是否正常工作

---

## 技术原理

### 1. 改进幅度计算
对于任何指标（准确率、响应时间、成本等），我们计算两种改进：

**绝对改进**:
```
absolute_improvement = experimental_value - baseline_value
```

**相对改进**:
```
relative_improvement = (experimental_value - baseline_value) / baseline_value
```

例如：
- Baseline 准确率: 75%
- Experimental 准确率: 82%
- 绝对改进: +7%
- 相对改进: +9.33%

### 2. 错误病例分析
通过交叉对比 baseline 和 experimental 的预测结果，将病例分为 4 类：

| Baseline | Experimental | 分类 | 说明 |
|----------|--------------|------|------|
| ✓ | ✓ | both_correct | 两者都对（工具库无影响） |
| ✗ | ✗ | both_wrong | 两者都错（工具库无帮助） |
| ✓ | ✗ | baseline_only_correct | 工具库导致退化（需分析原因） |
| ✗ | ✓ | experimental_only_correct | 工具库带来改进（核心价值） |

**净改进** = experimental_only_correct - baseline_only_correct

这个指标直观反映了工具库的实际价值。

### 3. 成本估算
基于 Claude API 定价（2026 年 5 月）:

| 模型 | Input | Output | 平均 |
|------|-------|--------|------|
| Sonnet 4 | $3/1M tokens | $15/1M tokens | $9/1M tokens |
| Opus 4 | $15/1M tokens | $75/1M tokens | $45/1M tokens |

简化假设 input:output = 1:1，实际可能略有偏差。

### 4. 工具使用分布分析
统计每个工具被调用的次数，找出最常用的工具。这有助于：
- 识别高价值工具（经常被使用且有效）
- 发现冗余工具（很少被使用）
- 优化工具库（优先改进高频工具的质量）

---

## 使用说明

### 1. 生成单个结果的指标报告

```bash
# 从推理结果生成指标报告
python src/Evaluation/toolkit_metrics.py \
    results/experimental.json \
    results/experimental_metrics.json

# 输出示例：
# [OK] 指标报告已保存到: results/experimental_metrics.json
# 
# [配置]
#   模式: experimental
#   模型: claude-sonnet-4-20250514
#   工具库: 启用
# 
# [准确率]
#   总病例数: 957
#   正确病例数: 789
#   准确率: 82.45%
# 
# [工具库使用]
#   工具使用率: 65.31%
#   平均每病例工具数: 1.32
#   执行成功率: 94.87%
```

### 2. 对比两组实验结果

```bash
# 生成对比报告
python src/Evaluation/compare_results.py \
    --baseline results/baseline.json \
    --experimental results/experimental.json \
    --output results/comparison.json

# 输出示例：
# [OK] 对比报告已保存到: results/comparison.json
# 
# [准确率对比]
#   Baseline: 75.13%
#   Experimental: 82.45%
#   绝对提升: 7.32%
#   相对提升: 9.74%
# 
# [错误分析]
#   共同病例数: 957
#   两者都对: 700
#   两者都错: 150
#   仅 Baseline 对: 20
#   仅 Experimental 对: 87
#   净改进: +67
```

### 3. 快速验证（10 个病例）

**Windows**:
```bash
cd D:\01_work\toolkit\MedRBench
set ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
scripts\quick_test.bat
```

**Linux/Mac**:
```bash
cd /path/to/MedRBench
export ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
bash scripts/quick_test.sh
```

### 4. 查看结果文件

```bash
# 查看摘要
cat results/quick_test/baseline.json | jq '.summary'
cat results/quick_test/experimental.json | jq '.summary'

# 查看对比报告
cat results/quick_test/comparison.json | jq '.accuracy_comparison'

# 查看最常用的工具
cat results/quick_test/experimental.json | jq '.summary.tool_usage_distribution'

# 查看某个病例的详细结果
cat results/quick_test/experimental.json | jq '.results[0]'
```

---

## 预期输出示例

### Baseline 结果摘要
```json
{
  "summary": {
    "total_cases": 10,
    "successful_cases": 10,
    "accuracy": 0.60,
    "tool_usage_rate": 0.0,
    "avg_tools_per_case": 0.0,
    "avg_response_time": 3.2,
    "total_tokens": 12450
  }
}
```

### Experimental 结果摘要
```json
{
  "summary": {
    "total_cases": 10,
    "successful_cases": 10,
    "accuracy": 0.70,
    "tool_usage_rate": 0.50,
    "avg_tools_per_case": 0.8,
    "avg_response_time": 5.1,
    "total_tokens": 18320
  }
}
```

### 对比报告摘要
```json
{
  "accuracy_comparison": {
    "improvement": {
      "baseline": 0.60,
      "experimental": 0.70,
      "absolute_improvement": 0.10,
      "relative_improvement_pct": 16.67
    }
  },
  "error_analysis": {
    "net_improvement": 1
  }
}
```

---

## 常见问题

### Q1: 为什么 experimental 的响应时间更长？
**原因**: 
1. 需要调用 MToolHub 搜索 API（~100-200ms）
2. 需要执行工具（~500-2000ms，取决于工具复杂度）
3. Claude 需要处理工具结果（额外的 tokens）

**是否值得**: 如果准确率提升明显（如 +10%），额外 2-3 秒的延迟通常是可接受的。

### Q2: 为什么 experimental 的 tokens 更多？
**原因**:
1. 工具搜索结果作为 tools 参数传给 Claude（增加 input tokens）
2. 工具执行结果返回给 Claude（增加 input tokens）
3. Claude 需要生成工具调用参数（增加 output tokens）

**成本影响**: 通常增加 20-50%，但如果准确率提升显著，ROI 仍然为正。

### Q3: 如何判断工具库是否有效？
**关键指标**:
1. **准确率提升** > 5%（绝对值）
2. **净改进** > 0（experimental_only_correct > baseline_only_correct）
3. **工具使用率** > 30%（说明 Claude 认为工具有用）
4. **执行成功率** > 90%（说明工具调用稳定）

如果以上指标都满足，说明工具库集成成功。

### Q4: 如果 experimental 准确率反而下降怎么办？
**可能原因**:
1. 工具搜索不准确（返回了不相关的工具）
2. 工具执行失败（返回错误结果误导 Claude）
3. Claude 过度依赖工具（忽略了病例中的关键信息）

**调试方法**:
1. 检查 `experimental_only_correct_cases` 和 `baseline_only_correct_cases`
2. 查看这些病例中使用了哪些工具
3. 检查工具执行结果是否正确
4. 调整 `search_top_k` 参数（减少候选工具数量）

---

## 下一步工作

### 阶段 3: 小样本验证（当前任务）
- [ ] 运行 `scripts/quick_test.bat` 验证 10 个病例
- [ ] 检查输出文件格式是否正确
- [ ] 验证对比报告是否合理
- [ ] 修复发现的问题

### 阶段 4: 完整实验（计划中）
- [ ] 运行完整 957 个病例的 baseline 实验
- [ ] 运行完整 957 个病例的 experimental 实验
- [ ] 运行所有消融实验
- [ ] 生成完整对比报告

### 阶段 5: 其他任务类型（计划中）
- [ ] 适配 `free_turn.py`（多轮诊断）
- [ ] 适配 `oracle_diagnose.py`（Oracle 诊断）
- [ ] 适配 `oracle_treatment_planning.py`（治疗规划）

---

## 文件清单

### 新建文件
- `src/Evaluation/__init__.py` - 评估模块初始化
- `src/Evaluation/toolkit_metrics.py` - 工具库指标计算（核心）
- `src/Evaluation/compare_results.py` - 对比分析脚本（核心）
- `scripts/quick_test.sh` - Linux/Mac 快速验证脚本
- `scripts/quick_test.bat` - Windows 快速验证脚本
- `PHASE2_REPORT.md` - 本报告

### 依赖的已有文件
- `src/Inference/one_turn_claude.py` - 推理脚本（阶段 1 创建）
- `configs/experiment_config.yaml` - 实验配置（阶段 1 创建）
- `src/Adapters/toolkit_adapter.py` - 适配器（阶段 1 创建）

---

## 技术栈

- **Python**: 3.8+
- **数据处理**: JSON（标准库）
- **统计分析**: 自定义函数（无需 numpy/pandas）
- **命令行参数**: argparse
- **格式化输出**: 自定义打印函数

---

## 参考文档

- [PHASE1_REPORT.md](PHASE1_REPORT.md) - 阶段 1 完成报告
- [EXPERIMENT_DESIGN.md](EXPERIMENT_DESIGN.md) - 完整实验设计文档
