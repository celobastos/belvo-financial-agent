import pytest

from belvo_finance_agent.config import get_settings


@pytest.fixture(autouse=True)
def disable_llm_polish_for_tests(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_POLISH", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
