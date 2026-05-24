# MToolHub Docker 部署指南

## 概述

整个系统通过 Docker Compose 统一管理，包含以下容器：

| 容器名 | 镜像 | 端口 | 说明 |
|--------|------|------|------|
| `toolkit-gateway` | toolkit-gateway:latest | 9000 | 统一推理网关（对外入口） |
| `mavl-serving` | mavl-serving:latest | 8000（内网） | MAVL 胸片分析模型（GPU） |
| `mvfa-ad-serving` | mvfa-ad-serving:latest | 8000（内网） | MVFA-AD 模型（GPU） |
| `tool-scale` | med-calc:latest | 8000（内网） | 医疗评分计算器（44 个，CPU） |
| `tool-unit` | med-calc:latest | 8000（内网） | 医学单位换算（237 个，CPU） |
| `tool-mdcalc` | mdcalc:latest | 8000（内网） | MDCalc 计算器（871 个，CPU） |
| `mtoolhub` | mtoolhub:latest | 8080 | **MToolHub 语义路由层（新增）** |

所有容器通过 `toolnet` 网络互联。

---

## 部署前准备

### 1. 检查远程服务器环境

```bash
# SSH 登录远程服务器
ssh user@remote

# 检查 Docker 和 Docker Compose
docker --version
docker compose version

# 检查 GPU（如果有）
nvidia-smi

# 检查已有容器
docker ps
```

### 2. 准备 Claude API Key

在本地创建 `.env` 文件（**不要提交到 Git**）：

```bash
# 在本地 AgentHospital 根目录
cat > .env << 'EOF'
CLAUDE_API_KEY=sk-ant-api03-xxxxx
EOF
```

---

## 部署步骤

### 方式一：完整部署（推荐，首次部署）

```bash
# 1. 上传整个项目到远程服务器
cd D:\01_work\AgentHospital
tar --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='MToolHub/backend/data/indexes/*' \
    -czf agenthospital.tar.gz .

scp agenthospital.tar.gz user@remote:/data/wxb/
scp .env user@remote:/data/wxb/AgentHospital/

# 2. 在远程服务器上解压
ssh user@remote
cd /data/wxb
tar -xzf agenthospital.tar.gz
cd AgentHospital

# 3. 构建并启动所有服务
docker compose build
docker compose up -d

# 4. 查看启动状态
docker compose ps
```

### 方式二：仅部署 MToolHub（已有其他容器运行）

```bash
# 1. 只上传 MToolHub 代码
cd D:\01_work\AgentHospital
tar -czf mtoolhub.tar.gz MToolHub/

scp mtoolhub.tar.gz user@remote:/data/wxb/AgentHospital/
scp .env user@remote:/data/wxb/AgentHospital/

# 2. 在远程服务器上解压
ssh user@remote
cd /data/wxb/AgentHospital
tar -xzf mtoolhub.tar.gz

# 3. 只构建 mtoolhub 镜像
docker compose build mtoolhub

# 4. 启动 mtoolhub 容器
docker compose up -d mtoolhub

# 5. 查看日志
docker compose logs -f mtoolhub
```

---

## 初始化数据

### 1. 导入资源注册表

MToolHub 启动后，需要从 Gateway 导入资源元数据：

```bash
# 进入 mtoolhub 容器
docker exec -it mtoolhub bash

# 从 Gateway 导入所有资源
python scripts/import_from_gateway.py http://toolkit-gateway:9000

# 验证导入结果
python scripts/test_import.py

# 预期输出：
# [OK] 共 1206 个资源
# [INFO] 资源类型统计:
#    model: 2
#    skill: 54
#    tool: 1150

# 退出容器
exit
```

### 2. 构建 FAISS 索引（Phase 3 需要）

```bash
# 进入容器
docker exec -it mtoolhub bash

# 构建向量索引
python scripts/build_index.py

# 验证索引文件
ls -lh data/indexes/

# 退出
exit
```

---

## 验证部署

### 1. 检查容器状态

```bash
# 查看所有容器
docker compose ps

# 预期输出：所有容器状态为 Up
# NAME                IMAGE                      STATUS
# toolkit-gateway     toolkit-gateway:latest     Up
# mavl-serving        mavl-serving:latest        Up
# mvfa-ad-serving     mvfa-ad-serving:latest     Up
# tool-scale          med-calc:latest            Up
# tool-unit           med-calc:latest            Up
# tool-mdcalc         mdcalc:latest              Up
# mtoolhub            mtoolhub:latest            Up
```

### 2. 检查网络连接

```bash
# 检查 mtoolhub 能否访问 gateway
docker exec mtoolhub curl http://toolkit-gateway:9000/tools

# 预期输出：Gateway 注册的所有工具列表
```

### 3. 测试 MToolHub API

```bash
# 测试根路径
curl http://localhost:8080/

# 预期响应：
# {
#   "name": "MToolHub",
#   "version": "1.0.0",
#   "status": "running",
#   "docs": "/docs"
# }

# 测试健康检查
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

### 4. 查看日志

```bash
# 查看 mtoolhub 日志
docker compose logs -f mtoolhub

# 查看最近 100 行
docker compose logs --tail=100 mtoolhub

# 查看所有容器日志
docker compose logs -f
```

---

## 常见问题

### 1. mtoolhub 容器启动失败

**问题**：`docker compose ps` 显示 mtoolhub 状态为 Exit

**排查**：
```bash
# 查看启动日志
docker compose logs mtoolhub

# 常见原因：
# - CLAUDE_API_KEY 未设置或无效
# - 端口 8080 被占用
# - Python 依赖安装失败
```

**解决**：
```bash
# 检查环境变量
docker exec mtoolhub env | grep CLAUDE

# 如果 API Key 未设置，重新启动并传入环境变量
docker compose down mtoolhub
docker compose up -d mtoolhub
```

### 2. 无法连接 Gateway

**问题**：`docker exec mtoolhub curl http://toolkit-gateway:9000/tools` 失败

**排查**：
```bash
# 检查 gateway 容器是否运行
docker ps | grep gateway

# 检查网络连接
docker network inspect toolnet

# 确认 mtoolhub 和 gateway 在同一网络
docker inspect mtoolhub | grep -A 10 Networks
docker inspect toolkit-gateway | grep -A 10 Networks
```

**解决**：
```bash
# 重启 gateway
docker compose restart gateway

# 重启 mtoolhub
docker compose restart mtoolhub
```

### 3. 导入资源失败

**问题**：`python scripts/import_from_gateway.py` 返回 0 个资源

**排查**：
```bash
# 在容器内测试 Gateway 连接
docker exec -it mtoolhub bash
curl http://toolkit-gateway:9000/tools
```

**解决**：
```bash
# 确保 Gateway 已启动并注册了工具
docker compose logs gateway | grep "Registered"

# 检查 gateway/tools/ 目录下的 config.yaml
docker exec toolkit-gateway ls -la /app/tools/
```

### 4. Embedding 模型下载慢

**问题**：首次启动时下载 Embedding 模型很慢

**解决**：
```bash
# 方式 1：使用国内镜像（在 Dockerfile 中添加）
ENV HF_ENDPOINT=https://hf-mirror.com

# 方式 2：手动下载模型到宿主机，然后挂载
# 在宿主机下载
mkdir -p /data/wxb/huggingface_cache
docker run --rm -v /data/wxb/huggingface_cache:/root/.cache/huggingface \
  python:3.10-slim \
  pip install sentence-transformers && \
  python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('pritamdeka/S-PubMedBert-MS-MARCO')"

# 修改 docker-compose.yml，添加 volume
volumes:
  - /data/wxb/huggingface_cache:/root/.cache/huggingface
```

### 5. 端口冲突

**问题**：`docker compose up` 报错 "port is already allocated"

**解决**：
```bash
# 查找占用端口的进程
lsof -i :8080

# 修改 docker-compose.yml 中的端口映射
ports:
  - "8081:8080"  # 改为其他端口
```

---

## 更新流程

### 更新 MToolHub 代码

```bash
# 1. 在本地修改代码后，重新打包
cd D:\01_work\AgentHospital
tar -czf mtoolhub.tar.gz MToolHub/

# 2. 上传到远程服务器
scp mtoolhub.tar.gz user@remote:/data/wxb/AgentHospital/

# 3. 在远程服务器上解压
ssh user@remote
cd /data/wxb/AgentHospital
tar -xzf mtoolhub.tar.gz

# 4. 重新构建并重启
docker compose build mtoolhub
docker compose up -d mtoolhub

# 5. 查看日志确认启动成功
docker compose logs -f mtoolhub
```

### 更新资源数据

```bash
# 当 Gateway 新增工具/模型后
docker exec -it mtoolhub bash
python scripts/import_from_gateway.py http://toolkit-gateway:9000
python scripts/build_index.py  # 如果已实现 Phase 3
exit

# 重启 mtoolhub（可选）
docker compose restart mtoolhub
```

### 更新 Gateway 配置

```bash
# 1. 修改 gateway/tools/*/config.yaml

# 2. 重启 gateway
docker compose restart gateway

# 3. 重新导入资源到 mtoolhub
docker exec mtoolhub python scripts/import_from_gateway.py http://toolkit-gateway:9000
```

---

## 监控和维护

### 查看资源使用

```bash
# 查看所有容器资源使用
docker stats

# 查看特定容器
docker stats mtoolhub

# 查看磁盘使用
docker system df
```

### 清理无用资源

```bash
# 清理停止的容器
docker compose down

# 清理无用镜像
docker image prune -a

# 清理无用卷
docker volume prune
```

### 备份数据

```bash
# 备份 MToolHub 数据目录
docker cp mtoolhub:/app/data /data/wxb/backup/mtoolhub_data_$(date +%Y%m%d)

# 备份整个项目
cd /data/wxb
tar -czf AgentHospital_backup_$(date +%Y%m%d).tar.gz AgentHospital/
```

---

## 完整部署命令速查

```bash
# ========== 首次部署 ==========
# 1. 上传代码和环境变量
scp agenthospital.tar.gz .env user@remote:/data/wxb/AgentHospital/

# 2. 解压并构建
cd /data/wxb/AgentHospital
tar -xzf agenthospital.tar.gz
docker compose build

# 3. 启动所有服务
docker compose up -d

# 4. 初始化数据
docker exec -it mtoolhub bash
python scripts/import_from_gateway.py http://toolkit-gateway:9000
python scripts/test_import.py
exit

# 5. 验证
curl http://localhost:8080/
docker compose ps

# ========== 仅更新 MToolHub ==========
# 1. 上传代码
scp mtoolhub.tar.gz user@remote:/data/wxb/AgentHospital/

# 2. 解压并重建
cd /data/wxb/AgentHospital
tar -xzf mtoolhub.tar.gz
docker compose build mtoolhub
docker compose up -d mtoolhub

# 3. 查看日志
docker compose logs -f mtoolhub
```

---

## 下一步：Phase 3

Phase 3 将实现向量检索和对话接口，需要：

1. 实现 Embedding 模型加载
2. 构建 FAISS 索引
3. 实现 `GET /api/tools/search` 接口
4. 实现 `POST /api/chat` 接口

部署流程相同，只需重新构建镜像即可。

---

## 故障排查流程图

```
容器启动失败？
  ├─ 查看日志：docker compose logs mtoolhub
  ├─ 检查环境变量：docker exec mtoolhub env
  └─ 检查端口占用：lsof -i :8080

无法访问 Gateway？
  ├─ 检查 gateway 状态：docker ps | grep gateway
  ├─ 检查网络：docker network inspect toolnet
  └─ 测试连接：docker exec mtoolhub curl http://toolkit-gateway:9000/tools

API 调用失败？
  ├─ 检查资源是否导入：docker exec mtoolhub cat data/registry/resources.json
  ├─ 检查 Claude API Key：docker exec mtoolhub env | grep CLAUDE
  └─ 查看实时日志：docker compose logs -f mtoolhub
```
