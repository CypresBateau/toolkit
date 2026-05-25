# MedRBench + MToolHub 集成项目 - 完整总结

## 项目完成状态

✅ **阶段 1**: 适配器层 + 推理脚本（已完成）
✅ **阶段 2**: 评估指标 + 对比分析（已完成）
✅ **阶段 3**: 快速验证脚本（已完成）

---

## 已完成的工作

### 1. 核心适配器层
**文件**: `src/Adapters/toolkit_adapter.py`

实现了 MToolHub 与 MedRBench 的集成接口：
- 支持 baseline 和 experimental 两种模式
- 异步工具搜索和执行
- Claude function calling 格式转换
- 配置文件驱动的实验设计

### 2. Claude 推理脚本
**文件**: `src/Inference/one_turn_claude.py`

实现了单轮诊断任务的 Claude 推理：
- 集成 ToolkitAdapter
- 支持多轮工具调用（最多 5 轮）
- 记录工具使用统计
- 输出标准化的 JSON 结果

### 3. 实验配置系统
**文件**: `configs/experiment_config.yaml`

支持 6 种实验模式：
- `baseline` - LLM 裸跑
- `experimental` - LLM + 工具库
- `ablation.search_only` - 只搜索不执行
- `ablation.top1_only` - 只返回 top-1 工具
- `ablation.different_llm` - 使用更强 LLM
- `ablation.top5` - 返回 top-5 工具

### 4. 评估指标模块
**文件**: `src/Evaluation/toolkit_metrics.py`

计算工具库相关指标：
- 工具使用率
- 平均每病例工具数
- 执行成功率
- 响应时间统计
- Token 使用统计
- 成本估算

### 5. 对比分析脚本
**文件**: `src/Evaluation/compare_results.py`

对比 baseline 和 experimental：
- 准确率对比（绝对改进 + 相对改进）
- 工具库使用对比
- 性能对比（响应时间、tokens）
- 成本对比
- 错误病例分析（净改进计算）

### 6. 快速验证脚本
**文件**: `scripts/quick_test.bat` 和 `scripts/quick_test.sh`

一键运行完整测试流程：
- 检查环境变量和服务状态
- 运行 baseline 测试（10 个病例）
- 运行 experimental 测试（10 个病例）
- 生成对比报告

### 7. 文档系统
- `EXPERIMENT_DESIGN.md` - 完整实验设计文档（11 个章节）
- `PHASE1_REPORT.md` - 阶段 1 完成报告
- `PHASE2_REPORT.md` - 阶段 2 完成报告
- `README_INTEGRATION.md` - 集成项目使用指南

---

## 技术架构

```
用户查询
    ↓
one_turn_claude.py（推理脚本）
    ↓
ToolkitAdapter（适配器层）
    ├── baseline 模式 → 返回空工具列表
    └── experimental 模式 → 调用 MToolHub API
        ↓
    MToolHub Backend（语义路由层）
        ├── /api/tools/search → 语义搜索工具
        └── /api/execute → 执行工具调用
            ↓
        Gateway（工具调度层）
            ├── tool-mdcalc（871 个计算器）
            ├── tool-unit（237 个单位换算）
            ├── tool-skills（54 个医疗技能）
            └── mavl（胸片分析模型）
```

---

## 实验设计原理

### 控制变量实验
**控制变量**（保持一致）:
- LLM 模型: `claude-sonnet-4-20250514`
- 温度参数: `0.0`
- 数据集: 相同的 957 个病例
- Prompt 模板: 相同的系统提示词

**自变量**（唯一变化）:
- baseline: `mtoolhub.enabled = false`
- experimental: `mtoolhub.enabled = true`

**因变量**（测量指标）:
- 诊断准确率
- 工具使用率
- 响应时间
- Token 使用量
- API 成本

### 评估指标

#### 准确率指标
- **Exact Match Accuracy**: 完全匹配准确率
- **Absolute Improvement**: 绝对提升（experimental - baseline）
- **Relative Improvement**: 相对提升（(experimental - baseline) / baseline）

#### 工具库指标
- **Tool Usage Rate**: 使用了至少一个工具的病例比例
- **Avg Tools Per Case**: 平均每病例工具数
- **Execution Success Rate**: 工具调用成功率
- **Tool Usage Distribution**: 工具使用分布（最常用的工具）

#### 性能指标
- **Avg Response Time**: 平均响应时间
- **Total Tokens**: 总 token 使用量
- **Estimated Cost**: 估算 API 成本

#### 错误分析
- **Both Correct**: 两者都对（工具库无影响）
- **Both Wrong**: 两者都错（工具库无帮助）
- **Baseline Only Correct**: 工具库导致退化
- **Experimental Only Correct**: 工具库带来改进
- **Net Improvement**: 净改进（核心价值指标）

---

## 使用流程

### 快速验证（推荐首次使用）

```bash
# 1. 设置 API Key
set ANTHROPIC_API_KEY=sk-ant-api03-xxxxx

# 2. 启动 MToolHub（仅 experimental 需要）
cd D:\01_work\AgentHospital\MToolHub\backend
uvicorn app.main:app --host 0.0.0.0 --port 8080

# 3. 运行快速测试（10 个病例）
cd D:\01_work\toolkit\MedRBench
scripts\quick_test.bat

# 4. 查看结果
cat results/quick_test/comparison.json | jq '.accuracy_comparison'
```

### 完整实验

```bash
# 1. Baseline 实验（957 个病例）
python src/Inference/one_turn_claude.py \
    --config configs/experiment_config.yaml \
    --mode baseline \
    --output results/baseline_one_turn.json

# 2. Experimental 实验（957 个病例）
python src/Inference/one_turn_claude.py \
    --config configs/experiment_config.yaml \
    --mode experimental \
    --output results/experimental_one_turn.json

# 3. 生成对比报告
python src/Evaluation/compare_results.py \
    --baseline results/baseline_one_turn.json \
    --experimental results/experimental_one_turn.json \
    --output results/comparison_report.json
```

---

## 预期结果

### 假设场景 1: 工具库有效
```
准确率对比:
  Baseline: 75.13%
  Experimental: 82.45%
  绝对提升: +7.32%
  相对提升: +9.74%

工具库使用:
  工具使用率: 65.31%
  平均每病例工具数: 1.32
  执行成功率: 94.87%

错误分析:
  净改进: +67（87 个病例因工具库而改进，20 个退化）

结论: 工具库显著提升诊断准确率，集成成功 ✅
```

### 假设场景 2: 工具库无效
```
准确率对比:
  Baseline: 75.13%
  Experimental: 74.89%
  绝对提升: -0.24%
  相对提升: -0.32%

工具库使用:
  工具使用率: 12.45%
  平均每病例工具数: 0.15
  执行成功率: 67.23%

错误分析:
  净改进: -5（15 个病例因工具库而改进，20 个退化）

结论: 工具库未带来增益，需要优化 ❌
可能原因:
  1. 工具搜索不准确（使用率低）
  2. 工具执行失败率高（成功率低）
  3. 工具结果误导 Claude（净改进为负）
```

---

## 下一步工作

### 短期（1-2 天）
- [ ] 运行快速验证（10 个病例）
- [ ] 检查输出格式是否正确
- [ ] 验证对比报告是否合理
- [ ] 修复发现的问题

### 中期（1 周）
- [ ] 运行完整实验（957 个病例）
- [ ] 运行所有消融实验
- [ ] 分析结果并撰写报告
- [ ] 优化工具库（如果需要）

### 长期（2-4 周）
- [ ] 适配其他任务类型（多轮诊断、Oracle 诊断、治疗规划）
- [ ] 扩展到其他 LLM（GPT-4、Gemini 等）
- [ ] 撰写论文
- [ ] 发布代码和数据

---

## 常见问题排查

### 问题 1: 运行时报错 "ModuleNotFoundError: No module named 'anthropic'"
**解决**: 
```bash
pip install anthropic httpx pyyaml tqdm pydantic
```

### 问题 2: 运行时报错 "ANTHROPIC_API_KEY not set"
**解决**: 
```bash
set ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
```

### 问题 3: 运行时报错 "Connection refused to localhost:8080"
**解决**: 
1. 检查 MToolHub 是否启动: `curl http://localhost:8080/api/health`
2. 如果是 baseline 模式，不需要启动 MToolHub

### 问题 4: Claude 不调用工具
**调试步骤**:
1. 在 `one_turn_claude.py` 中添加调试输出:
   ```python
   print(f"[DEBUG] 搜索到的工具: {[t['name'] for t in tools]}")
   print(f"[DEBUG] Claude 响应: {response.stop_reason}")
   ```
2. 检查搜索到的工具是否与病例相关
3. 检查工具的 `input_schema` 是否正确
4. 尝试调整 `search_top_k` 参数

### 问题 5: 实验成本过高
**优化建议**:
1. 先用 `--limit 10` 测试
2. 使用 `temperature: 0.0` 确保可复现
3. 考虑使用 Claude Haiku（更便宜）
4. 实现结果缓存（相同病例不重复调用）

---

## 文件清单

### 核心代码文件
- `src/Adapters/__init__.py`
- `src/Adapters/toolkit_adapter.py` ⭐
- `src/Inference/one_turn_claude.py` ⭐
- `src/Evaluation/__init__.py`
- `src/Evaluation/toolkit_metrics.py` ⭐
- `src/Evaluation/compare_results.py` ⭐

### 配置文件
- `configs/experiment_config.yaml` ⭐

### 脚本文件
- `scripts/quick_test.sh`
- `scripts/quick_test.bat`

### 文档文件
- `EXPERIMENT_DESIGN.md` - 完整实验设计（11 章节）
- `PHASE1_REPORT.md` - 阶段 1 报告
- `PHASE2_REPORT.md` - 阶段 2 报告
- `README_INTEGRATION.md` - 使用指南
- `SUMMARY.md` - 本文件

---

## 技术亮点

### 1. 适配器模式
通过 ToolkitAdapter 解耦 MedRBench 和 MToolHub，使得：
- MedRBench 推理逻辑保持不变
- 可以轻松切换工具库实现
- 便于单元测试和调试

### 2. 配置驱动
通过 YAML 配置文件控制实验参数，使得：
- 无需修改代码即可切换模式
- 便于管理多组实验
- 确保实验可复现

### 3. 异步执行
使用 asyncio 和 httpx 实现异步 HTTP 请求，使得：
- 工具搜索和执行更高效
- 支持并发处理多个工具调用
- 资源管理更安全（async with）

### 4. 完整的评估体系
不仅评估准确率，还评估：
- 工具使用情况（使用率、分布）
- 性能指标（响应时间、tokens）
- 成本指标（API 费用）
- 错误分析（净改进）

### 5. 严格的控制变量
确保 baseline 和 experimental 之间：
- 相同的 LLM 模型和参数
- 相同的数据集和 prompt
- 唯一差异是工具库的启用与否

---

## 致谢

感谢以下项目和工具：
- **MedRBench**: 提供高质量的临床诊断基准测试
- **Anthropic Claude**: 提供强大的 LLM 和 function calling 能力
- **MToolHub**: 提供丰富的医疗工具库

---

## 联系方式

如有问题或建议，请联系：
- 项目负责人: [Your Name]
- 邮箱: [your.email@example.com]

---

**最后更新**: 2026-05-24
