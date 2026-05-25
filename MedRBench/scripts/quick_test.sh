#!/bin/bash
# quick_test.sh - 快速验证脚本（10 个病例）
#
# 使用方式：
#   bash scripts/quick_test.sh

set -e  # 遇到错误立即退出

echo "=========================================="
echo "MedRBench + MToolHub 快速验证测试"
echo "=========================================="

# 检查环境变量
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "[ERR] 请设置 ANTHROPIC_API_KEY 环境变量"
    exit 1
fi

# 检查 MToolHub 服务（仅 experimental 模式需要）
echo ""
echo "[INFO] 检查 MToolHub 服务状态..."
if curl -s http://localhost:8080/api/health > /dev/null 2>&1; then
    echo "[OK] MToolHub 服务正常运行"
else
    echo "[WARN] MToolHub 服务未运行（baseline 模式不需要）"
fi

# 创建输出目录
mkdir -p results/quick_test

# 运行 Baseline 测试
echo ""
echo "=========================================="
echo "运行 Baseline 测试（10 个病例）"
echo "=========================================="
python src/Inference/one_turn_claude.py \
    --config configs/experiment_config.yaml \
    --mode baseline \
    --output results/quick_test/baseline.json \
    --limit 10

# 运行 Experimental 测试
echo ""
echo "=========================================="
echo "运行 Experimental 测试（10 个病例）"
echo "=========================================="
python src/Inference/one_turn_claude.py \
    --config configs/experiment_config.yaml \
    --mode experimental \
    --output results/quick_test/experimental.json \
    --limit 10

# 生成对比报告
echo ""
echo "=========================================="
echo "生成对比报告"
echo "=========================================="
python src/Evaluation/compare_results.py \
    --baseline results/quick_test/baseline.json \
    --experimental results/quick_test/experimental.json \
    --output results/quick_test/comparison.json

echo ""
echo "=========================================="
echo "测试完成！"
echo "=========================================="
echo ""
echo "结果文件："
echo "  - Baseline: results/quick_test/baseline.json"
echo "  - Experimental: results/quick_test/experimental.json"
echo "  - 对比报告: results/quick_test/comparison.json"
echo ""
