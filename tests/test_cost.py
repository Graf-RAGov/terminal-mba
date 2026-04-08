"""Tests for cost calculation."""
from __future__ import annotations

from terminalmba.cost import compute_session_cost, get_model_pricing, MODEL_PRICING


def test_compute_cost_missing_session():
    """compute_session_cost returns zeros for non-existent session."""
    result = compute_session_cost("nonexistent-id-12345", "/no/such/project")
    assert result["cost"] == 0
    assert result["inputTokens"] == 0
    assert result["outputTokens"] == 0


def test_get_model_pricing_sonnet():
    pricing = get_model_pricing("claude-sonnet-4-6")
    assert pricing["input"] > 0
    assert pricing["output"] > 0
    assert pricing["cache_read"] > 0


def test_get_model_pricing_opus():
    pricing = get_model_pricing("claude-opus-4-6")
    assert pricing == MODEL_PRICING["claude-opus-4-6"]


def test_get_model_pricing_fallback():
    """Unknown model should fall back to sonnet pricing."""
    pricing = get_model_pricing("unknown-model-xyz")
    assert pricing == MODEL_PRICING["claude-sonnet-4-6"]


def test_get_model_pricing_empty():
    """Empty model should fall back to sonnet pricing."""
    pricing = get_model_pricing("")
    assert pricing == MODEL_PRICING["claude-sonnet-4-6"]


def test_get_model_pricing_haiku():
    pricing = get_model_pricing("claude-haiku-4-5")
    assert pricing == MODEL_PRICING["claude-haiku-4-5"]


def test_model_pricing_has_entries():
    assert len(MODEL_PRICING) >= 5
    for key, pricing in MODEL_PRICING.items():
        assert "input" in pricing
        assert "output" in pricing
        assert "cache_read" in pricing
        assert "cache_create" in pricing
