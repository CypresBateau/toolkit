# MToolHub Backend - Phase 3

医疗工具智能调度平台 - 语义路由层

## 当前状态：Phase 3 已完成 [OK]

Phase 3 实现了向量检索和语义路由，用户可以通过自然语言查询医疗工具、模型和技能。

## 架构概览

```
用户请求
    ↓
MToolHub Backend (FastAPI, 端口 8080)
    ├── 路由决策 (router.py)
    ├── 编排器 (orchestrator.py)
    └── 统一执行器 (executor.py)
        ↓
Gateway (端口 9000)
    ↓
工具容器 (tool-mdcalc, tool-unit, mavl, etc.)
```

## 核心功能

### 已实现（Phase 3）
- [OK] 统一执行器（UnifiedExecutor）
- [OK] 根据 `gateway_interface` 自动路由（call/predict）
- [OK] Claude API 集成（参数提取 + 结果解读）
- [OK] `POST /api/execute` 直接执行接口
- [OK] 统一的资源注册表（resources.json）
- [OK] 从 Gateway 自动导入资源
- [OK] 向量检索（FAISS + Embedding）
- [OK] `GET /api/tools/search` 语义搜索接口
- [OK] `POST /api/chat` 对话接口
- [OK] 路由决策（direct_call / claude_select / chat_only）

### 待实现（Phase 4）
- [ ] 会话管理（Redis 持久化）
- [ ] 结果缓存
- [ ] 多语言支持
- [ ] 前端界面
- [ ] 监控告警
- [ ] 权限管理

## 快速开始

### 使用 Docker Compose（推荐）

```bash
# 1. 准备环境变量
cat > .env << 'EOF'
CLAUDE_API_KEY=sk-ant-api03-xxxxx
EOF

# 2. 构建并启动
docker compose build mtoolhub
docker compose up -d mtoolhub

# 3. 初始化数据
docker exec -it mtoolhub bash
python scripts/import_from_gateway.py http://toolkit-gateway:9000
python scripts/build_index.py
exit

# 4. 测试
curl http://localhost:8080/api/health
curl "http://localhost:8080/api/tools/search?q=Wells+DVT&top_k=3"
```

详细部署指南：[DEPLOY_DOCKER.md](DEPLOY_DOCKER.md)

## API 接口

### 根路径
```bash
GET /
```

### 健康检查
```bash
GET /api/health
```

### 直接执行
```bash
POST /api/execute
Content-Type: application/json

{
  "resource_id": "tool-mdcalc:wells_score_dvt",
  "arguments": {
    "active_cancer": 1,
    "paralysis": 0,
    ...
  }
}
```

### 语义搜索
```bash
GET /api/tools/search?q=Wells+DVT&top_k=5
```

### 对话接口
```bash
POST /api/chat
Content-Type: application/json

{
  "message": "帮我计算Wells DVT评分，患者有活动性癌症"
}
```

## 项目结构

```
MToolHub/backend/
├── app/
│   ├── main.py                  # FastAPI 入口
│   ├── config.py                # 配置管理
│   ├── models/                  # 数据模型
│   │   ├── registry.py          # ResourceMetadata
│   │   └── api.py               # 请求/响应模型
│   ├── core/                    # 核心模块
│   │   ├── registry.py          # 注册表管理
│   │   ├── claude_client.py     # Claude API 客户端
│   │   ├── embedding.py         # [OK] Embedding 模型
│   │   └── faiss_index.py       # [OK] FAISS 索引
│   ├── services/                # 业务逻辑
│   │   ├── executor.py          # [OK] 统一执行器
│   │   ├── orchestrator.py      # [OK] 编排器
│   │   └── router.py            # [OK] 路由决策
│   ├── routers/                 # API 路由
│   │   ├── execute.py           # [OK] 直接执行接口
│   │   ├── chat.py              # [OK] 对话接口
│   │   └── search.py            # [OK] 搜索接口
│   └── utils/                   # 工具函数
│       └── disclaimer.py        # 医疗免责声明
├── scripts/                     # 脚本
│   ├── import_from_gateway.py   # [OK] 从 Gateway 导入资源
│   ├── build_index.py           # [OK] 构建 FAISS 索引
│   ├── test_e2e.py              # [OK] 端到端测试
│   └── check_phase2.py          # [OK] 代码检查
├── data/                        # 数据目录
│   ├── registry/
│   │   └── resources.json       # 统一资源注册表
│   └── indexes/                 # FAISS 索引
├── Dockerfile                   # [OK] Docker 镜像
├── requirements.txt             # [OK] Python 依赖
├── PHASE1_SUMMARY.md            # Phase 1 总结
├── PHASE2_SUMMARY.md            # Phase 2 总结
├── PHASE3_SUMMARY.md            # Phase 3 总结
├── DEPLOY_DOCKER.md             # Docker 部署指南
└── CHECKLIST_PHASE2.md          # Phase 2 检查清单
```

## 技术栈

- **后端框架**: FastAPI + uvicorn
- **数据验证**: Pydantic v2
- **HTTP 客户端**: httpx (异步)
- **LLM**: Claude API (Anthropic)
- **向量检索**: FAISS + sentence-transformers
- **Embedding**: S-PubMedBert-MS-MARCO
- **容器化**: Docker + Docker Compose

## 环境变量

```env
# Claude API
CLAUDE_API_KEY=sk-ant-api03-xxxxx
CLAUDE_MODEL=claude-sonnet-4-20250514
CLAUDE_MAX_TOKENS=4096

# Gateway
GATEWAY_BASE_URL=http://toolkit-gateway:9000
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
```

## 开发指南

### 本地开发

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env

# 3. 启动服务
uvicorn app.main:app --reload --port 8080

# 4. 访问文档
open http://localhost:8080/docs
```

### 运行测试

```bash
# 代码检查
python scripts/check_phase2.py

# 端到端测试
python scripts/test_e2e.py
```

### 添加新资源

1. 在 Gateway 中注册新工具/模型
2. 重新导入资源：
   ```bash
   docker exec mtoolhub python scripts/import_from_gateway.py http://toolkit-gateway:9000
   ```
3. 重建索引：
   ```bash
   docker exec mtoolhub python scripts/build_index.py
   ```
4. 重启服务（可选）

## 文档

- [Phase 1 总结](PHASE1_SUMMARY.md) - 统一数据模型和注册表
- [Phase 2 总结](PHASE2_SUMMARY.md) - 统一执行器
- [Phase 3 总结](PHASE3_SUMMARY.md) - 向量检索和语义路由
- [Docker 部署指南](DEPLOY_DOCKER.md) - 完整部署流程
- [Phase 2 检查清单](CHECKLIST_PHASE2.md) - 验收标准

## 常见问题

### 1. 容器启动失败

```bash
# 查看日志
docker compose logs mtoolhub

# 常见原因：
# - CLAUDE_API_KEY 未设置
# - 端口 8080 被占用
# - Gateway 未启动
```

### 2. 无法连接 Gateway

```bash
# 检查网络
docker network inspect toolnet

# 测试连接
docker exec mtoolhub curl http://toolkit-gateway:9000/tools
```

### 3. 资源导入失败

```bash
# 确保 Gateway 已启动
docker ps | grep gateway

# 手动导入
docker exec -it mtoolhub bash
python scripts/import_from_gateway.py http://toolkit-gateway:9000
```

## 贡献指南

1. 遵循 [CLAUDE.md](../../CLAUDE.md) 中的编码规范
2. 禁止使用 Unicode 特殊符号（如 ✓✗★⚠🚀等）
3. 使用 ASCII 前缀：`[OK]`, `[ERR]`, `[WARN]`, `[INFO]`
4. 所有注释和文档使用中文

## 许可证

[待定]

## 联系方式

[待定]

---

**当前版本**: 1.0.0 (Phase 3)  
**最后更新**: 2026-05-20
