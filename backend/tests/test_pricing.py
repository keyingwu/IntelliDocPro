import pytest

from intellidocpro.pricing import PRICES, ModelPrice, cost_of, lookup_price
from intellidocpro.result import ExtractionResult


def _result(model, engine="openai", usage=None):
    return ExtractionResult(
        values=[], engine=engine, model=model,
        usage=usage if usage is not None else {"input_tokens": 720, "output_tokens": 315},
    )


def test_exact_lookup():
    price = lookup_price("gpt-5.6-terra")
    assert price == ModelPrice(input_per_mtok=2.5, output_per_mtok=15.0)


def test_substring_lookup_for_azure_deployments():
    price = lookup_price("prod-gpt-5.6-terra-eu")
    assert price is not None
    assert price.input_per_mtok == 2.5


def test_substring_prefers_longest_match():
    prices = {
        "gpt-5.6": ModelPrice(input_per_mtok=99, output_per_mtok=99),
        "gpt-5.6-luna": ModelPrice(input_per_mtok=1, output_per_mtok=6),
    }
    assert lookup_price("my-gpt-5.6-luna", prices).input_per_mtok == 1


def test_unknown_model():
    assert lookup_price("mystery-model-9000") is None


def test_cost_math():
    cost = cost_of(_result("gpt-5.6-terra"))
    # 720 / 1M * 2.5 + 315 / 1M * 15
    assert cost.pricing_known
    assert cost.input_cost == pytest.approx(0.0018)
    assert cost.output_cost == pytest.approx(0.004725)
    assert cost.total_cost == pytest.approx(0.006525)
    assert cost.input_per_mtok == 2.5


def test_cost_unknown_model_flagged():
    cost = cost_of(_result("mystery-model-9000"))
    assert not cost.pricing_known
    assert cost.total_cost == 0.0
    assert cost.input_tokens == 720


def test_cost_missing_usage():
    cost = cost_of(_result("gpt-5.6-terra", usage={}))
    assert cost.total_cost == 0.0
    assert cost.pricing_known


def test_custom_price_table():
    prices = {"my-model": ModelPrice(input_per_mtok=100.0, output_per_mtok=200.0)}
    cost = cost_of(_result("my-model", usage={"input_tokens": 1_000_000, "output_tokens": 500_000}), prices)
    assert cost.total_cost == pytest.approx(200.0)


def test_all_default_engine_models_priced():
    # the three engines' default models must always be in the table
    for model in ("claude-opus-4-8", "gpt-5.6-luna"):
        assert model in PRICES
