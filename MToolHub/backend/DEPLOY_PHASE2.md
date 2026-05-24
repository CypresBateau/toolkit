# Phase 2 部署指南

## 快速检查清单

在部署到远程服务器之前，运行以下检查：

```bash
cd MToolHub/backend

# 1. 检查代码完整性
python scripts/check_phase2.py

# 2. 检查注册表数据（如果已导入）
python scripts/test_import.py

# 3. 测试 Phase 2 功能
python scripts/test_phase2.py
```

## 远程部署步骤

### 1. 上传代码到远程服务器

```bash
# 在本地打包（排除不必要的文件）
cd D:\01_work\AgentHospital
tar --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='data/indexes/*' --exclude='.env' \
    -czf mtoolhub.tar.gz MToolHub/

# 上传到远程服务器
scp mtoolhub.tar.gz user@remote:/data/wxb/AgentHospital/

# 在远程服务器上解压
ssh user@remote
cd /data/wxb/AgentHospital
tar -xzf mtoolhub.tar.gz
```

### 2. 配置环境变量

```bash
cd /data/wxb/AgentHospital/MToolHub/backend

# 创建 .env 文件
cat > .env << 'EOF'
# Claude API
CLAUDE_API_KEY=sk-ant-api03-xxxxx
CLAUDE_MODEL=claude-sonnet-4-20250514
CLAUDE_MAX_TOKENS=4096

# Gateway
GATEWAY_BASE_URL=http://gateway:9000
GATEWAY_TIMEOUT=60

# Embedding
EMBEDDING_MODEL=pritamdeka/S-PubMedBert-MS-MARCO
EMBEDDING_DEVICE=cpu

# 路由阈值
DIRECT_CALL_THRESHOLD=0.85
CLAUDE_SELECT_THRESHOLD=0.60

# 服务配置
HOST=0.0.0.0
PORT=8080
DEBUG=false
EOF

# 修改权限
chmod 600 .env
```

### 3. 安装依赖

```bash
# 如果使用虚拟环境
python -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 4. 导入资源数据

```bash
# 从 Gateway 导入所有资源
python scripts/import_from_gateway.py http://gateway:9000

# 验证导入结果
python scripts/test_import.py

# 预期输出：
# [OK] 共 1206 个资源
# [INFO] 资源类型统计:
#    model: 2
#    skill: 54
#    tool: 1150
```

### 5. 运行检查

```bash
# 运行 Phase 2 检查
python scripts/check_phase2.py

# 预期输出：
# [OK] Phase 2 所有检查通过！代码可以部署到远程服务器。
```

### 6. 启动服务

```bash
# 前台运行（测试用）
uvicorn app.main:app --host 0.0.0.0 --port 8080

# 后台运行（生产环境）
nohup uvicorn app.main:app --host 0.0.0.0 --port 8080 > logs/mtoolhub.log 2>&1 &

# 或使用 systemd（推荐）
sudo systemctl start mtoolhub
sudo systemctl enable mtoolhub
```

### 7. 验证服务

```bash
# 检查服务状态
curl http://localhost:8080/

# 预期响应：
# {
#   "name": "MToolHub",
#   "version": "1.0.0",
#   "status": "running",
#   "docs": "/docs"
# }

# 检查健康状态
curl http://localhost:8080/api/health

# 测试直接执行接口
curl -X POST http://localhost:8080/api/execute \
  -H "Content-Type: application/json" \
  -d '{
    "resource_id": "tool-mdcalc:wells_score_dvt",
    "arguments": {
      "active_cancer": 1,
      "paralysis": 0,
      "bedridden": 0,
      "localized_tenderness": 1,
      "entire_leg_swollen": 0,
      "calf_swelling": 1,
      "pitting_edema": 0,
      "collateral_veins": 0,
      "alternative_diagnosis": 0
    }
  }' | jq
```

## 常见问题

### 1. 导入失败：无法连接 Gateway

**问题**：`python scripts/import_from_gateway.py` 报错 "Connection refused"

**解决**：
```bash
# 检查 Gateway 是否运行
curl http://gateway:9000/tools

# 如果失败，检查 Docker 网络
docker network inspect toolnet

# 确保 Gateway 容器在运行
docker ps | grep gateway
```

### 2. Claude API Key 无效

**问题**：启动时报错 "Invalid API key"

**解决**：
```bash
# 检查 .env 文件
cat .env | grep CLAUDE_API_KEY

# 确保 API Key 格式正确（sk-ant-api03-xxxxx）
# 测试 API Key
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $CLAUDE_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-sonnet-4-20250514","max_tokens":10,"messages":[{"role":"user","content":"Hi"}]}'
```

### 3. 模块导入失败

**问题**：`ModuleNotFoundError: No module named 'pydantic_settings'`

**解决**：
```bash
# 确保在虚拟环境中
source venv/bin/activate

# 重新安装依赖
pip install -r requirements.txt

# 检查安装
pip list | grep pydantic
```

### 4. 端口被占用

**问题**：启动时报错 "Address already in use"

**解决**：
```bash
# 查找占用端口的进程
lsof -i :8080

# 杀死进程
kill -9 <PID>

# 或使用其他端口
uvicorn app.main:app --host 0.0.0.0 --port 8081
```

## 更新流程

### 代码更新

```bash
# 1. 备份当前版本
cd /data/wxb/AgentHospital
cp -r MToolHub MToolHub.backup.$(date +%Y%m%d)

# 2. 上传新代码
scp mtoolhub.tar.gz user@remote:/data/wxb/AgentHospital/
tar -xzf mtoolhub.tar.gz

# 3. 重启服务
sudo systemctl restart mtoolhub
```

### 资源数据更新

```bash
# 当 Gateway 新增工具/模型/技能后
cd /data/wxb/AgentHospital/MToolHub/backend

# 重新导入
python scripts/import_from_gateway.py http://gateway:9000

# 验证
python scripts/test_import.py

# 重启服务
sudo systemctl restart mtoolhub
```

## 监控和日志

### 查看日志

```bash
# 实时查看日志
tail -f logs/mtoolhub.log

# 查看错误日志
grep ERROR logs/mtoolhub.log

# 查看最近 100 行
tail -n 100 logs/mtoolhub.log
```

### 性能监控

```bash
# 检查进程状态
ps aux | grep uvicorn

# 检查内存使用
free -h

# 检查磁盘使用
df -h
```

## 下一步：Phase 3

Phase 2 完成后，可以开始 Phase 3（向量检索和路由层）：

1. 实现 Embedding 模型加载
2. 构建 FAISS 索引
3. 实现语义搜索接口
4. 实现对话接口

详见 `PHASE3_PLAN.md`（待创建）。

## 回滚步骤

如果部署出现问题，可以快速回滚：

```bash
# 停止服务
sudo systemctl stop mtoolhub

# 恢复备份
cd /data/wxb/AgentHospital
rm -rf MToolHub
mv MToolHub.backup.YYYYMMDD MToolHub

# 重启服务
sudo systemctl start mtoolhub
```

## 联系支持

如果遇到无法解决的问题，请提供以下信息：

1. 错误日志：`tail -n 100 logs/mtoolhub.log`
2. 系统信息：`uname -a`
3. Python 版本：`python --version`
4. 依赖版本：`pip list`
5. Gateway 状态：`curl http://gateway:9000/tools`
