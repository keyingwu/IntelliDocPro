# docstill: schema 驱动的文档抽取中间层设计

日期: 2026-07-13
状态: 已确认

## 背景与目标

IntelliDocPro 是一个文档处理平台（现有产物是一个纯 UI 原型 `Dokumenten-Assistent (standalone).html`，无真实解析逻辑）。第一步是把核心能力抽成一个可复用的中间层:

> 输入一份文档和一个用户定义的 schema，抽取出每个字段的值，并附带置信度、来源位置和复核标记。

设计目标:

1. **可复用**: 其他项目可以 `pip install` 直接调用（Python 库），或通过 HTTP 调用（FastAPI 薄封装）。
2. **多引擎**: 抽取引擎可插拔，第一版实现 Claude、OpenAI 原生、Azure OpenAI 三个引擎。
3. **原生文档处理**: PDF/图片直接发给模型（已调研确认三家均原生支持 PDF 直传 + structured outputs），不自建 OCR/文本抽取管线。

## 范围

### 包含（v1）

- `extract(document, schema, engine=...)`: 给定 schema 抽取字段值
- `suggest_schema(document, engine=...)`: 从样例文档推断 schema
- 输入类型: PDF（含扫描件）、PNG/JPG 图片
- 引擎: `claude`、`openai`、`azure_openai`
- FastAPI 服务: `POST /extract`、`POST /schema/suggest`、`GET /health`

### 不包含（明确排除，后续迭代）

- 批量并发处理（调用方自行循环）
- docx/xlsx/eml 输入
- 人工复核的状态存储、UI
- 结果持久化

## 目录结构

```
docstill/
  pyproject.toml            # 包名 docstill, 可独立安装
  src/docstill/
    __init__.py             # 顶层 API: extract(), suggest_schema()
    schema.py               # FieldType / FieldSpec / ExtractionSchema
    result.py               # FieldValue / ExtractionResult
    document.py             # Document: 从路径或 bytes 加载, MIME 判断, 大小校验
    prompts.py              # 抽取与 schema 推断的 prompt 模板（引擎共享）
    errors.py               # 类型化异常
    engines/
      __init__.py           # 引擎注册表: get_engine(name)
      base.py               # Extractor 抽象接口
      claude.py             # ClaudeExtractor (anthropic SDK)
      openai_common.py      # OpenAI/Azure 共享: Responses API 请求构造与解析
      openai.py             # OpenAIExtractor (api.openai.com)
      azure_openai.py       # AzureOpenAIExtractor
  server/
    app.py                  # FastAPI 应用
  tests/
    test_schema.py
    test_document.py
    test_engines.py         # mock 引擎响应
    test_server.py
    integration/            # 需真实 API key, 环境变量存在才跑
```

## 数据模型（对外契约）

```python
class FieldType(str, Enum):
    TEXT = "text"       # 原型: Text
    NUMBER = "number"   # Zahl
    DATE = "date"       # Datum
    AMOUNT = "amount"   # Betrag
    PERCENT = "percent" # Prozent
    ENUM = "enum"       # Auswahl

class FieldSpec(BaseModel):
    name: str                          # 如 "Rechnungsnummer"
    type: FieldType = FieldType.TEXT
    description: str | None = None     # 给模型的抽取提示
    enum_values: list[str] | None = None  # 仅 type=ENUM 时有效
    required: bool = False

class ExtractionSchema(BaseModel):
    fields: list[FieldSpec]            # 非空; 字段名唯一

class SourceRef(BaseModel):
    page: int | None = None            # 1 起始页码
    location: str | None = None        # 区域描述, 如 "Kopfzeile" / "表格第 3 行"

class FieldValue(BaseModel):
    field: str
    value: str | float | None          # 归一化值: date 转 ISO 8601, number/amount/percent 转 float
    raw_text: str | None               # 文档中的原文
    currency: str | None = None        # 仅 AMOUNT 类型
    confidence: Literal["high", "medium", "low"]
    source: SourceRef | None
    needs_review: bool                 # value 为 None 或 confidence == "low" 时为 True

class ExtractionResult(BaseModel):
    values: list[FieldValue]           # 与 schema.fields 一一对应, 顺序一致
    engine: str
    model: str
    usage: dict                        # input_tokens / output_tokens 等
```

## 引擎层

```python
class Extractor(ABC):
    @abstractmethod
    def extract(self, doc: Document, schema: ExtractionSchema) -> ExtractionResult: ...
    @abstractmethod
    def suggest_schema(self, doc: Document) -> ExtractionSchema: ...
```

引擎注册表: `ENGINES = {"claude": ..., "openai": ..., "azure_openai": ...}`，新引擎实现接口后注册一行即可。

### ClaudeExtractor

- SDK: `anthropic`，默认模型 `claude-opus-4-8`（`DOCSTILL_CLAUDE_MODEL` 可覆盖）
- PDF 用 `document` content block（base64），图片用 `image` block
- structured outputs: `client.messages.parse()` + Pydantic 输出模型
- 已知取舍: citations 与 structured outputs 不能同用（API 返回 400），因此来源定位由模型在输出 JSON 中自报（页码 + 区域描述），不用 citations

### OpenAIExtractor / AzureOpenAIExtractor

- 共用 `openai_common.py`: Responses API 的 `input_file`（base64 data URL）/ `input_image` 构造、`responses.parse()` + Pydantic、结果解析
- OpenAI 原生: `OPENAI_API_KEY`，默认模型 `gpt-5.6-terra`（2026-07 最新 GPT-5.6 家族的平衡档，支持 PDF 输入 + structured outputs；`DOCSTILL_OPENAI_MODEL` 可覆盖，如 `gpt-5.6-sol` 冲精度、`gpt-5.6-luna` 降成本）
- Azure: `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_DEPLOYMENT`，用 v1 API；模型参数填 deployment 名
- v1 只用 base64 直传，不用 Files API（规避 Azure `purpose="user_data"` 未支持的问题）

### Prompt 策略（三引擎共享模板）

- 抽取: 系统指令说明任务 + 每字段的 name/type/description/enum_values + 归一化规则（日期 ISO、金额数字+货币）+ 要求自报 confidence 和 source + 找不到时返回 null 而不是编造
- schema 推断: 要求识别文档中适合结构化抽取的关键字段，返回 FieldSpec 列表（含类型推断和 description）

## 输入校验与限制

| 校验 | 规则 |
|---|---|
| 类型 | 仅 `application/pdf`、`image/png`、`image/jpeg`，按魔数判断而非扩展名 |
| 大小 | Claude: 32MB; OpenAI/Azure: 50MB。发请求前校验，超限抛 `DocumentTooLarge` |
| schema | fields 非空、名字唯一、ENUM 必须带 enum_values，Pydantic 校验 |

## 错误处理

```python
class DocstillError(Exception): ...
class UnsupportedDocumentType(DocstillError): ...
class DocumentTooLarge(DocstillError): ...
class SchemaValidationError(DocstillError): ...
class EngineError(DocstillError): ...   # 包 API 异常, 附引擎名/request id
class EngineNotConfigured(DocstillError): ...  # 缺环境变量
```

抽取失败的单个字段不抛异常: `value=None, needs_review=True`。整个请求失败（API 错误、超时）抛 `EngineError`。

## FastAPI 服务

- `POST /extract`: multipart，`file`（文档）+ `schema`（JSON 字符串表单字段）+ `engine`（表单字段，默认 `claude`）→ `ExtractionResult` JSON
- `POST /schema/suggest`: multipart，`file` + `engine` → `ExtractionSchema` JSON
- `GET /health`: 返回可用引擎列表（按环境变量配置判断）
- 错误映射: `UnsupportedDocumentType`/`SchemaValidationError` → 422，`DocumentTooLarge` → 413，`EngineNotConfigured` → 503，`EngineError` → 502
- 启动: `uvicorn server.app:app`

## 测试策略

- 单元测试: schema 校验、document 加载/校验、prompt 构造、引擎响应解析（mock SDK 返回）
- 服务测试: FastAPI TestClient + mock 引擎
- 集成测试（`tests/integration/`）: 对应环境变量存在才跑，用小样例 PDF（一张模拟发票）验证三引擎端到端抽取
- 验收: 用样例发票 PDF + 6 字段 schema（对应原型 Rechnungen），三引擎都能返回结构完整的 ExtractionResult

## 环境变量汇总

| 变量 | 用途 |
|---|---|
| `ANTHROPIC_API_KEY` | claude 引擎 |
| `DOCSTILL_CLAUDE_MODEL` | 可选，默认 `claude-opus-4-8` |
| `OPENAI_API_KEY` | openai 引擎 |
| `DOCSTILL_OPENAI_MODEL` | 可选，默认 `gpt-5.6-terra` |
| `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_DEPLOYMENT` | azure_openai 引擎 |
