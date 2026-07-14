# IntelliDocPro

Schema 驱动的文档处理平台。上传样例文档自动推断字段 schema，批量抽取 PDF/图片中的
结构化数据（值 + 置信度 + 来源定位 + 复核标记），多 LLM 引擎可切换并带成本核算。

```
docstill/    抽取中间层: Python 包 (可独立复用) + FastAPI 服务 + SQLite 平台存储
webapp/      React + Vite + TS 前端 (助手管理 / 三步向导 / 结果表格 / Excel 导出)
docs/        设计文档
```

## 快速开始

```bash
# 1. 后端 (Python >= 3.10, 用 uv)
cd docstill
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.example .env    # 填入至少一家引擎的 key

# 2. 前端
cd ../webapp && npm install

# 3. 开发模式 (两个终端)
cd docstill && .venv/bin/python -m uvicorn server.app:app --port 8000
cd webapp && npm run dev          # http://localhost:5173

# 或生产模式 (单进程): 构建后 FastAPI 直接托管前端
cd webapp && npm run build
cd ../docstill && .venv/bin/python -m uvicorn server.app:app --port 8000
# 打开 http://localhost:8000
```

## 测试

```bash
cd docstill
.venv/bin/python -m pytest                    # 单元 + 服务测试, 无需网络
.venv/bin/python -m pytest tests/integration  # 真实 API 端到端, 按 key 自动跳过
```

引擎与库的用法详见 [docstill/README.md](docstill/README.md)。
