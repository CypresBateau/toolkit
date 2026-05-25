@echo off
REM quick_test.bat - Windows 快速验证脚本（10 个病例）
REM
REM 使用方式：
REM   quick_test.bat

echo ==========================================
echo MedRBench + MToolHub 快速验证测试
echo ==========================================

REM 检查环境变量
if "%ANTHROPIC_API_KEY%"=="" (
    echo [ERR] 请设置 ANTHROPIC_API_KEY 环境变量
    echo 使用方式: set ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
    exit /b 1
)

REM 检查 MToolHub 服务
echo.
echo [INFO] 检查 MToolHub 服务状态...
curl -s http://localhost:8080/api/health >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] MToolHub 服务正常运行
) else (
    echo [WARN] MToolHub 服务未运行（baseline 模式不需要）
)

REM 创建输出目录
if not exist results\quick_test mkdir results\quick_test

REM 运行 Baseline 测试
echo.
echo ==========================================
echo 运行 Baseline 测试（10 个病例）
echo ==========================================
python src\Inference\one_turn_claude.py ^
    --config configs\experiment_config.yaml ^
    --mode baseline ^
    --output results\quick_test\baseline.json ^
    --limit 10

if %errorlevel% neq 0 (
    echo [ERR] Baseline 测试失败
    exit /b 1
)

REM 运行 Experimental 测试
echo.
echo ==========================================
echo 运行 Experimental 测试（10 个病例）
echo ==========================================
python src\Inference\one_turn_claude.py ^
    --config configs\experiment_config.yaml ^
    --mode experimental ^
    --output results\quick_test\experimental.json ^
    --limit 10

if %errorlevel% neq 0 (
    echo [ERR] Experimental 测试失败
    exit /b 1
)

REM 生成对比报告
echo.
echo ==========================================
echo 生成对比报告
echo ==========================================
python src\Evaluation\compare_results.py ^
    --baseline results\quick_test\baseline.json ^
    --experimental results\quick_test\experimental.json ^
    --output results\quick_test\comparison.json

if %errorlevel% neq 0 (
    echo [ERR] 对比报告生成失败
    exit /b 1
)

echo.
echo ==========================================
echo 测试完成！
echo ==========================================
echo.
echo 结果文件：
echo   - Baseline: results\quick_test\baseline.json
echo   - Experimental: results\quick_test\experimental.json
echo   - 对比报告: results\quick_test\comparison.json
echo.

pause
