# IntelliDocPro

Schema 驱动的文档处理平台。上传样例文档自动推断字段 schema，批量抽取 PDF/图片中的
结构化数据（值 + 置信度 + 来源定位 + 复核标记），多 LLM 引擎可切换并带成本核算。

```
backend/    Python 包 (可独立复用) + FastAPI 服务 + SQLite 存储
webapp/     React + Vite + TS 前端 (Document Agent 管理 / 三步向导 / 结果表格 / Excel 导出)
docs/       设计文档
```

## 快速开始

### Docker 一键起 (推荐)

```bash
# 方式 A: 直接跑发布镜像 (数据落在 intellidocpro-data 卷里)
docker run -p 8000:8000 -e OPENAI_API_KEY=sk-... \
  -v intellidocpro-data:/data ghcr.io/keyingwu/intellidocpro
# 打开 http://localhost:8000

# 方式 B: 本地构建 + docker compose
cp backend/.env.example backend/.env   # 填入至少一家引擎的 key, 不用的引擎整段删掉
docker compose up --build
```

引擎 key 也可以直接用宿主机环境变量传 (`export OPENAI_API_KEY=...` 后再
`docker compose up`), 同名时环境变量优先于 `backend/.env`。

### 源码开发模式

```bash
# 1. 后端 (Python >= 3.10, 用 uv)
cd backend
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.example .env    # 填入至少一家引擎的 key

# 2. 前端
cd ../webapp && npm install

# 3. 开发模式 (两个终端)
cd backend && .venv/bin/python -m uvicorn server.app:app --port 8000
cd webapp && npm run dev          # http://localhost:5173

# 或生产模式 (单进程): 构建后 FastAPI 直接托管前端
cd webapp && npm run build
cd ../backend && .venv/bin/python -m uvicorn server.app:app --port 8000
# 打开 http://localhost:8000
```

## 测试

```bash
cd backend
.venv/bin/python -m pytest                    # 单元 + 服务测试, 无需网络
.venv/bin/python -m pytest tests/integration  # 真实 API 端到端, 按 key 自动跳过
```

引擎与库的用法详见 [backend/README.md](backend/README.md)。
