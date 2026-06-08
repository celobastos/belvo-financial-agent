import os
from functools import lru_cache


try:
    from pydantic import Field
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

        mcp_url: str = Field(default="http://localhost:8000/mcp", alias="MCP_URL")
        mcp_token: str = Field(default="belvo-demo-token", alias="MCP_TOKEN")
        model_provider: str = Field(default="anthropic", alias="MODEL_PROVIDER")
        model_name: str = Field(default="claude-haiku-4-5", alias="MODEL_NAME")
        anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
        enable_llm_polish: bool = Field(default=True, alias="ENABLE_LLM_POLISH")
        llm_polish_max_tokens: int = Field(default=350, alias="LLM_POLISH_MAX_TOKENS")
        log_level: str = Field(default="INFO", alias="LOG_LEVEL")
        enable_streaming: bool = Field(default=True, alias="ENABLE_STREAMING")
        mcp_max_pages: int = Field(default=20, alias="MCP_MAX_PAGES")
        mcp_page_size: int = Field(default=100, alias="MCP_PAGE_SIZE")

except ModuleNotFoundError:

    def _env_bool(name: str, default: bool) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return value.lower() in {"1", "true", "yes", "on"}

    class Settings:
        def __init__(self) -> None:
            self.mcp_url = os.getenv("MCP_URL", "http://localhost:8000/mcp")
            self.mcp_token = os.getenv("MCP_TOKEN", "belvo-demo-token")
            self.model_provider = os.getenv("MODEL_PROVIDER", "anthropic")
            self.model_name = os.getenv("MODEL_NAME", "claude-haiku-4-5")
            self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
            self.enable_llm_polish = _env_bool("ENABLE_LLM_POLISH", True)
            self.llm_polish_max_tokens = int(os.getenv("LLM_POLISH_MAX_TOKENS", "350"))
            self.log_level = os.getenv("LOG_LEVEL", "INFO")
            self.enable_streaming = _env_bool("ENABLE_STREAMING", True)
            self.mcp_max_pages = int(os.getenv("MCP_MAX_PAGES", "20"))
            self.mcp_page_size = int(os.getenv("MCP_PAGE_SIZE", "100"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
