# docstill

Schema 驱动的文档字段抽取中间层：给定一份文档（PDF/PNG/JPEG）和一个字段 schema，
返回每个字段的归一化值、置信度、来源位置和复核标记。抽取引擎可插拔，
内置 Claude、OpenAI、Azure OpenAI 三个引擎，文档均以原生方式直传给模型
（无自建 OCR/文本抽取管线，扫描件开箱即用）。

设计文档: `../docs/superpowers/specs/2026-07-13-docstill-design.md`

## 安装

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

## 用法（Python 库）

```python
import docstill

schema = {
    "fields": [
        {"name": "Lieferant", "type": "text"},
        {"name": "Rechnungsdatum", "type": "date"},
        {"name": "Gesamtbetrag", "type": "amount"},
        {"name": "MwSt-Satz", "type": "percent"},
    ]
}

result = docstill.extract("rechnung.pdf", schema, engine="claude")
for v in result.values:
    print(v.field, v.value, v.confidence, v.source, v.needs_review)

# 从样例文档推断 schema
suggested = docstill.suggest_schema("rechnung.pdf", engine="openai")
```

字段类型: `text` / `number` / `date` / `amount` / `percent` / `enum`（需 `enum_values`）。
归一化规则: date 转 ISO 8601，number/amount/percent 转 float（兼容德式 `10.055,50`
与英式 `10,055.50` 千分位），amount 附 `currency`。值缺失、置信度 low 或
归一化失败时 `needs_review=True`。

## 引擎与环境变量

| engine | 环境变量 | 默认模型 |
|---|---|---|
| `claude` | `ANTHROPIC_API_KEY` | `claude-opus-4-8`（`DOCSTILL_CLAUDE_MODEL` 覆盖） |
| `openai` | `OPENAI_API_KEY` | `gpt-5.6-terra`（`DOCSTILL_OPENAI_MODEL` 覆盖） |
| `azure_openai` | `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_DEPLOYMENT` | deployment 名即模型 |

大小上限: Claude 32MB，OpenAI/Azure 50MB，超限抛 `DocumentTooLarge`。

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
```

错误映射: 422（文档类型/schema/engine 名非法）、413（超大小）、
503（引擎未配置）、502（上游 API 失败）。

## 测试

```bash
pytest                      # 单元 + 服务测试, 无需网络
pytest tests/integration    # 真实 API 端到端, 按已配置的 key 自动跳过未配置引擎
```
