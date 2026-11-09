import pytest

from civiclens.agent import fallback
from civiclens.agent.llm import LlmConfigError, build_llm
from civiclens.config import Settings
from civiclens.domain.investigation_models import RunRequest


@pytest.mark.parametrize(
    ("count", "sev", "expected"),
    [(10, 3.0, 1), (7, 3.0, 2), (4, 3.0, 3), (2, 3.0, 4), (1, 3.0, 5), (7, 3.57, 2), (3, 1.0, 5)],
)
def test_priority_rules(count, sev, expected):
    assert fallback.priority_for(count, sev) == expected


def test_confidence_is_monotonic_and_bounded():
    vals = [fallback.confidence_for(n) for n in (1, 3, 7, 50)]
    assert vals == sorted(vals) and 0 < vals[0] and vals[-1] < 1


class FakeTool:
    def __init__(self, data, ok=True):
        self.data, self.ok, self.calls = data, ok, []

    def invoke(self, args):
        self.calls.append(args)
        return {"ok": self.ok, "data": self.data}


def test_fallback_builds_labelled_grounded_drafts():
    spot = {"geo_cell": "C1_2", "category": "POTHOLE", "complaint_count": 7, "avg_severity": 3.6,
            "first_reported_at": "2026-10-01", "last_reported_at": "2026-10-20"}  # fmt: skip
    tools = {"hotspot_summary": FakeTool([spot]),
             "search_complaints": FakeTool([{"complaint_id": 4}, {"complaint_id": 9}])}  # fmt: skip
    res = fallback.run_fallback(tools, RunRequest(mode="fallback", max_hotspots=1))
    d = res.drafts[0]
    assert d.evidence_ids == [4, 9] and res.seen_ids == {4, 9}
    assert d.priority == 1 and "[RULE-BASED, NO LLM]" in d.rationale
    assert tools["search_complaints"].calls[0]["geo_cell"] == "C1_2"


def test_fallback_with_no_hotspots_returns_no_drafts():
    res = fallback.run_fallback(
        {"hotspot_summary": FakeTool([]), "search_complaints": FakeTool([])}, RunRequest()
    )
    assert res.drafts == []


def test_llm_provider_none_returns_no_client():
    assert build_llm(Settings(_env_file=None)) is None


@pytest.mark.parametrize(
    ("provider", "extra"),
    [("openai", {}), ("anthropic", {}), ("watsonx", {"watsonx_apikey": "k"})],
)
def test_missing_credentials_or_model_raise_config_error(provider, extra):
    with pytest.raises(LlmConfigError, match="LLM_MODEL"):
        build_llm(Settings(_env_file=None, llm_provider=provider, **extra))
    with pytest.raises(LlmConfigError):
        build_llm(Settings(_env_file=None, llm_provider=provider, llm_model="m", **extra))


@pytest.mark.parametrize(
    ("provider", "key_field", "cls"),
    [("openai", "openai_api_key", "ChatOpenAI"), ("anthropic", "anthropic_api_key", "ChatAnthropic")],
)
def test_client_construction_without_network(provider, key_field, cls):
    """Construction only (dummy key, no request is made). Does NOT prove the provider works."""
    pytest.importorskip({"openai": "langchain_openai", "anthropic": "langchain_anthropic"}[provider])
    handle = build_llm(
        Settings(
            _env_file=None, llm_provider=provider, llm_model="test-model", **{key_field: "dummy-not-a-key"}
        )
    )
    assert type(handle.model).__name__ == cls and handle.label == f"{provider}:test-model"
