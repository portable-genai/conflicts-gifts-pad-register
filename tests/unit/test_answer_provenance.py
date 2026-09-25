"""The service half of the model pills: which model ANSWERED, and whether it searched.

The console shows two pills at the top right: the model that answered the last request, and
``Search`` when that answer used an online search tool. Both come from response headers the kit
emits (``install_answer_provenance`` in ``api/app.py``) for whatever the model adapters NOTED as
they called. Before a request is answered the pill shows ``generator_model`` from ``/healthz``,
so that value must be the model the bound adapter calls, never one a configuration flag names
while the adapter calls another.

The Vertex adapter is driven here through a FAKE ``vertexai`` module, so what is proved is this
repository's half: the model id each call notes, and the sampling each call sends (entity
resolution pinned at 0.0 because it is extraction; the rationale free, so no temperature at all).
"""

from __future__ import annotations

import dataclasses
import sys
import types
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hex_service_kit import provenance

from conflicts_gifts_pad_register import config
from conflicts_gifts_pad_register.adapters.gcp import llm as gcp_llm
from conflicts_gifts_pad_register.adapters.local.llm import STUB_MODEL, LocalLlmAdapter
from conflicts_gifts_pad_register.api import app as app_module

from tests import REPO_ROOT
from tests.conftest import local_settings
from tests.unit.test_api import _body

ANSWERED_BY = "x-answered-by"
SEARCH_USED = "x-search-used"


@pytest.fixture()
def local_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The API under ``local`` whatever the shell exported: CI runs with no profile set."""
    monkeypatch.setenv(config._PROFILE_ENV, "local")
    app_module._container.cache_clear()
    with TestClient(app_module.app, client=("127.0.0.1", 50000)) as client:
        yield client
    app_module._container.cache_clear()


def _assess(client: TestClient) -> dict[str, str]:
    response = client.post("/v1/assess", json=_body(), headers={"X-Dev-Persona": "auditor"})
    assert response.status_code == 200, response.text
    return dict(response.headers)


def test_the_local_model_answers_as_the_stub_the_pill_first_names(
    local_client: TestClient,
) -> None:
    headers = _assess(local_client)
    assert headers[ANSWERED_BY] == STUB_MODEL
    assert SEARCH_USED not in headers
    assert local_settings().generator_model == STUB_MODEL


def test_a_call_that_searched_says_so_and_the_next_request_starts_fresh(
    local_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = LocalLlmAdapter.generate

    def searching(self: LocalLlmAdapter, prompt: str, **kwargs: Any) -> str:
        provenance.note_model("fake-searching-model")
        provenance.note_search()
        return original(self, prompt, **kwargs)

    monkeypatch.setattr(LocalLlmAdapter, "generate", searching)
    headers = _assess(local_client)
    assert headers[ANSWERED_BY] == f"fake-searching-model, {STUB_MODEL}"
    assert headers[SEARCH_USED] == "true"
    monkeypatch.setattr(LocalLlmAdapter, "generate", original)
    headers = _assess(local_client)
    assert headers[ANSWERED_BY] == STUB_MODEL
    assert SEARCH_USED not in headers


def test_extraction_is_pinned_and_the_rationale_is_drafted_with_no_temperature(
    local_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, float | None] = {}
    original = LocalLlmAdapter.generate

    def recording(self: LocalLlmAdapter, prompt: str, **kwargs: Any) -> str:
        required = (kwargs.get("schema") or {}).get("required") or []
        for field in required:
            seen[field] = kwargs.get("temperature")
        return original(self, prompt, **kwargs)

    monkeypatch.setattr(LocalLlmAdapter, "generate", recording)
    _assess(local_client)
    assert seen["counterparty"] == 0.0, "entity resolution is extraction: pinned"
    assert "rationale" in seen and seen["rationale"] is None, "narration is free: none sent"


# --------------------------------------------------------------------------------------- #
# The Vertex adapter, through a fake SDK.
# --------------------------------------------------------------------------------------- #
class _FakeModel:
    calls: list[dict[str, Any]] = []

    def __init__(self, name: str) -> None:
        self.name = name

    def generate_content(self, prompt: str, **kwargs: Any) -> SimpleNamespace:
        _FakeModel.calls.append({"model": self.name, **kwargs})
        return SimpleNamespace(text="{}")


@pytest.fixture()
def fake_vertex(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    _FakeModel.calls = []
    vertexai = types.ModuleType("vertexai")
    generative = types.ModuleType("vertexai.generative_models")
    generative.GenerativeModel = _FakeModel  # type: ignore[attr-defined]
    vertexai.generative_models = generative  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "vertexai", vertexai)
    monkeypatch.setitem(sys.modules, "vertexai.generative_models", generative)
    return _FakeModel.calls


def _gcp_adapter() -> gcp_llm.VertexLlmAdapter:
    return gcp_llm.VertexLlmAdapter(dataclasses.replace(local_settings(), profile="gcp"))


def test_the_vertex_adapter_notes_its_model_and_sends_no_free_temperature(
    fake_vertex: list[dict[str, Any]],
) -> None:
    with provenance.scope() as record:
        _gcp_adapter().generate("narrate", schema={"required": ["rationale"]})
    assert record.models == [gcp_llm._MODEL]
    assert record.search_used is False
    assert fake_vertex == [{"model": gcp_llm._MODEL}], "free sampling sends no config at all"


def test_a_pinned_call_reaches_the_vertex_config(fake_vertex: list[dict[str, Any]]) -> None:
    _gcp_adapter().generate("resolve", temperature=0.0)
    assert fake_vertex[0]["generation_config"] == {"temperature": 0.0}


def test_generator_model_is_the_model_the_vertex_adapter_calls() -> None:
    settings = dataclasses.replace(local_settings(), profile="gcp")
    assert settings.generator_model == gcp_llm._MODEL


def test_no_flag_swaps_in_a_model_the_adapter_never_calls() -> None:
    """The latent false banner: a flag that moved the pill but not the model that answered."""
    models = SimpleNamespace(
        reasoning="the-model-the-adapter-calls",
        hard_reasoning="a-model-nobody-calls",
        use_hard_reasoning=True,
    )
    named = config._model_from_settings(SimpleNamespace(models=models), "models.reasoning")
    assert named == "the-model-the-adapter-calls"


def test_the_hard_reasoning_flag_does_not_exist() -> None:
    settings_file = (REPO_ROOT / "config" / "settings.yaml").read_text(encoding="utf-8")
    assert "use_hard_reasoning" not in settings_file
    for source in sorted((REPO_ROOT / "src").rglob("*.py")):
        assert "use_hard_reasoning" not in source.read_text(encoding="utf-8"), source
