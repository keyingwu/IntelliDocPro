"""Cost calculation from actual token usage.

Prices are USD per 1M tokens and need periodic manual refresh; see
PRICES_AS_OF. Unknown models still get a CostBreakdown, just with
pricing_known=False and zero costs, so callers can render "n/a".
"""

from pydantic import BaseModel

from .result import ExtractionResult

PRICES_AS_OF = "2026-07-14"


class ModelPrice(BaseModel):
    input_per_mtok: float
    output_per_mtok: float


PRICES: dict[str, ModelPrice] = {
    # Anthropic
    "claude-fable-5": ModelPrice(input_per_mtok=10.0, output_per_mtok=50.0),
    "claude-opus-4-8": ModelPrice(input_per_mtok=5.0, output_per_mtok=25.0),
    "claude-opus-4-7": ModelPrice(input_per_mtok=5.0, output_per_mtok=25.0),
    "claude-opus-4-6": ModelPrice(input_per_mtok=5.0, output_per_mtok=25.0),
    # intro price through 2026-08-31 (list: 3.0 / 15.0)
    "claude-sonnet-5": ModelPrice(input_per_mtok=2.0, output_per_mtok=10.0),
    "claude-sonnet-4-6": ModelPrice(input_per_mtok=3.0, output_per_mtok=15.0),
    "claude-haiku-4-5": ModelPrice(input_per_mtok=1.0, output_per_mtok=5.0),
    # OpenAI GPT-5.6 family (GA 2026-07-09)
    "gpt-5.6-sol": ModelPrice(input_per_mtok=5.0, output_per_mtok=30.0),
    "gpt-5.6-terra": ModelPrice(input_per_mtok=2.5, output_per_mtok=15.0),
    "gpt-5.6-luna": ModelPrice(input_per_mtok=1.0, output_per_mtok=6.0),
}


class CostBreakdown(BaseModel):
    engine: str
    model: str
    input_tokens: int
    output_tokens: int
    pricing_known: bool
    input_per_mtok: float | None = None
    output_per_mtok: float | None = None
    input_cost: float = 0.0
    output_cost: float = 0.0
    total_cost: float = 0.0  # USD


def lookup_price(model: str, prices: dict[str, ModelPrice] | None = None) -> ModelPrice | None:
    """Exact match first; otherwise the longest known model name contained in
    `model`. The substring pass makes Azure deployment names like
    'prod-gpt-5.6-terra-eu' resolve to their underlying model."""
    table = prices if prices is not None else PRICES
    if model in table:
        return table[model]
    matches = [key for key in table if key in model]
    if matches:
        return table[max(matches, key=len)]
    return None


def cost_of(
    result: ExtractionResult, prices: dict[str, ModelPrice] | None = None
) -> CostBreakdown:
    """Compute the actual cost of one extraction from its token usage."""
    input_tokens = int(result.usage.get("input_tokens", 0))
    output_tokens = int(result.usage.get("output_tokens", 0))
    price = lookup_price(result.model, prices)
    if price is None:
        return CostBreakdown(
            engine=result.engine,
            model=result.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            pricing_known=False,
        )
    input_cost = input_tokens / 1_000_000 * price.input_per_mtok
    output_cost = output_tokens / 1_000_000 * price.output_per_mtok
    return CostBreakdown(
        engine=result.engine,
        model=result.model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        pricing_known=True,
        input_per_mtok=price.input_per_mtok,
        output_per_mtok=price.output_per_mtok,
        input_cost=round(input_cost, 6),
        output_cost=round(output_cost, 6),
        total_cost=round(input_cost + output_cost, 6),
    )
