import pytest

import intellidocpro.compare as compare_module
from intellidocpro.compare import Candidate, compare_engines
from intellidocpro.errors import IntelliDocProError, EngineError
from intellidocpro.result import ExtractionResult

PDF = b"%PDF-1.4 fake"
SCHEMA = {"fields": [{"name": "Lieferant"}]}


class FakeEngine:
    def __init__(self, name, model, fail=False):
        self.name, self.model, self.fail = name, model, fail

    def extract(self, doc, schema):
        if self.fail:
            raise EngineError("boom", engine=self.name)
        return ExtractionResult(
            values=[], engine=self.name, model=self.model,
            usage={"input_tokens": 1_000_000, "output_tokens": 0},
        )


@pytest.fixture
def fake_engines(monkeypatch):
    def fake_get_engine(name, model=None):
        if name == "broken":
            return FakeEngine(name, "x", fail=True)
        return FakeEngine(name, model or f"{name}-default-model")

    monkeypatch.setattr(compare_module, "get_engine", fake_get_engine)


def test_compare_returns_entry_per_candidate_in_order(fake_engines):
    entries = compare_engines(
        PDF, SCHEMA,
        candidates=[
            {"engine": "claude", "model": "claude-haiku-4-5"},
            Candidate(engine="openai", model="gpt-5.6-luna"),
        ],
    )
    assert [e.engine for e in entries] == ["claude", "openai"]
    assert all(e.ok for e in entries)
    # 1M input tokens: haiku $1, luna $1
    assert entries[0].cost.total_cost == pytest.approx(1.0)
    assert entries[1].cost.total_cost == pytest.approx(1.0)
    assert entries[0].model == "claude-haiku-4-5"


def test_failed_candidate_does_not_break_comparison(fake_engines):
    entries = compare_engines(
        PDF, SCHEMA,
        candidates=[{"engine": "broken"}, {"engine": "openai", "model": "gpt-5.6-terra"}],
    )
    broken, ok = entries
    assert not broken.ok
    assert "boom" in broken.error
    assert broken.cost is None
    assert ok.ok
    assert ok.cost.pricing_known


def test_default_candidates_require_configured_engine(monkeypatch):
    monkeypatch.setattr(compare_module, "available_engines", lambda: {"claude": False})
    with pytest.raises(IntelliDocProError, match="no candidates"):
        compare_engines(PDF, SCHEMA)


def test_default_candidates_use_configured_engines(monkeypatch, fake_engines):
    monkeypatch.setattr(
        compare_module, "available_engines",
        lambda: {"claude": True, "openai": False, "azure_openai": True},
    )
    entries = compare_engines(PDF, SCHEMA)
    assert [e.engine for e in entries] == ["claude", "azure_openai"]
