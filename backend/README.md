# IntelliDocPro Python SDK and backend

Schema 驱动的文档字段抽取中间层：给定一份文档（PDF/PNG/JPEG）和一个字段 schema，
返回每个字段的归一化值、置信度、来源位置和复核标记。抽取引擎可插拔，
内置 Claude、OpenAI、Azure OpenAI 三个引擎，文档均以原生方式直传给模型
（无自建 OCR/文本抽取管线，扫描件开箱即用）。

设计文档: `../docs/superpowers/specs/2026-07-13-intellidocpro-backend-design.md`

## 安装

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

## 用法（Python 库）

```python
import intellidocpro

schema = {
    "fields": [
        {"name": "Lieferant", "type": "text"},
        {"name": "Rechnungsdatum", "type": "date"},
        {"name": "Gesamtbetrag", "type": "amount"},
        {"name": "MwSt-Satz", "type": "percent"},
    ]
}

result = intellidocpro.extract("rechnung.pdf", schema)
for v in result.values:
    print(v.field, v.value, v.confidence, v.source, v.needs_review)

# 从样例文档推断 schema
suggested = intellidocpro.suggest_schema("rechnung.pdf", engine="openai")
```

字段类型: `text` / `number` / `date` / `amount` / `percent` / `enum`（需 `enum_values`）。
归一化规则: date 转 ISO 8601，number/amount/percent 转 float（兼容德式 `10.055,50`
与英式 `10,055.50` 千分位），amount 附 `currency`。值缺失、置信度 low 或
归一化失败时 `needs_review=True`。

## 引擎与环境变量

| engine | 环境变量 | 默认模型 |
|---|---|---|
| `claude` | `ANTHROPIC_API_KEY` | `claude-opus-4-8`（`INTELLIDOCPRO_CLAUDE_MODEL` 覆盖） |
| `openai` | `OPENAI_API_KEY` | `gpt-5.6-luna`（`INTELLIDOCPRO_OPENAI_MODEL` 覆盖） |
| `azure_openai` | `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_DEPLOYMENT` | deployment 名即模型 |

大小上限: Claude 32MB，OpenAI/Azure 50MB，超限抛 `DocumentTooLarge`。

未指定 engine/model 时默认使用 OpenAI `gpt-5.6-luna`。

## 价格测算与引擎对比

```python
import intellidocpro

# 单次抽取的实际成本（基于返回的真实 token 用量）
result = intellidocpro.extract("rechnung.pdf", schema, engine="openai")
cost = intellidocpro.cost_of(result)
print(cost.total_cost, cost.input_cost, cost.output_cost)  # USD

# 同一文件跑多个 engine/model 候选, 并发执行, 返回每个候选的成本+结果+耗时
entries = intellidocpro.compare_engines("rechnung.pdf", schema, candidates=[
    {"engine": "claude"},                              # 引擎默认模型
    {"engine": "claude", "model": "claude-haiku-4-5"},
    {"engine": "openai", "model": "gpt-5.6-luna"},
])
for e in entries:
    print(e.engine, e.model, e.ok, e.cost.total_cost if e.ok else e.error)
```

价格表在 `intellidocpro.PRICES`（USD / 1M tokens，更新日期见 `intellidocpro.PRICES_AS_OF`），
可传自定义 `prices` 覆盖。未知模型返回 `pricing_known=False` 而不是报错；
Azure 的 deployment 名按最长子串匹配到底层模型（如 `prod-gpt-5.6-terra-eu`）。
单个候选失败不会中断整个对比（`ok=False` + `error`）。

## 批量处理（bulk）

```python
import intellidocpro

report = intellidocpro.bulk_extract(
    ["a.pdf", "b.pdf", ("scan.pdf", pdf_bytes)],   # 路径 / bytes / (文件名, bytes)
    schema,
    engine="openai", model="gpt-5.6-luna",
    max_workers=4,
    on_update=lambda snap: print(snap.completed, "/", snap.total),  # 每次状态变化回调
)
print(report.completed, report.failed, report.needs_review_files, report.total_cost_usd)
```

单个文件失败（坏文件、API 错误）只标记该条目，不中断整批。
`on_update` 收到的是不可变快照，可直接透传给 UI。

HTTP 版是异步 job + 轮询：

```bash
# 提交, 立即返回 job_id
curl -X POST http://localhost:8000/bulk \
  -F "files=@a.pdf" -F "files=@b.pdf" \
  -F 'schema={"fields":[{"name":"Lieferant"}]}' \
  -F "engine=openai" -F "model=gpt-5.6-luna"
# => 202 {"job_id": "7f6f71155c74", "total": 2}

# 前端每秒轮询进度: 每个文件 queued/running/done/failed + 累计成本
curl http://localhost:8000/bulk/7f6f71155c74
```

Job 状态存进程内存，多进程部署时换 Redis（接口不变）。

## HTTP 服务

```bash
uvicorn server.app:app --port 8000
```

```bash
curl -X POST http://localhost:8000/extract \
  -F "file=@rechnung.pdf" \
  -F 'schema={"fields":[{"name":"Lieferant"},{"name":"Gesamtbetrag","type":"amount"}]}' \
  -F "engine=claude"

curl -X POST http://localhost:8000/schema/suggest -F "file=@rechnung.pdf"
curl http://localhost:8000/health

# 多候选价格对比（candidates 省略 = 所有已配置引擎的默认模型）
curl -X POST http://localhost:8000/compare \
  -F "file=@rechnung.pdf" \
  -F 'schema={"fields":[{"name":"Lieferant"}]}' \
  -F 'candidates=[{"engine":"claude"},{"engine":"openai","model":"gpt-5.6-luna"}]'
```

错误映射: 422（文档类型/schema/engine 名非法）、413（超大小）、
503（引擎未配置）、502（上游 API 失败）。

## 测试

```bash
pytest                      # 单元 + 服务测试, 无需网络
pytest tests/integration    # 真实 API 端到端, 按已配置的 key 自动跳过未配置引擎
```
