from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class ConfigSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AppSettings(ConfigSection):
    environment: Literal["development", "test", "production"] = "development"
    auth_required: bool = True
    secret_key: SecretStr = SecretStr("")
    auth_token_ttl_seconds: int = Field(default=604800, ge=60, le=2_592_000)
    runtime_dir: Path = Path("./runtime")
    workspace_storage_dir: Path = Path("./runtime/workspaces")
    artifact_storage_dir: Path = Path("./runtime/artifacts")


class APISettings(ConfigSection):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )


class DatabaseSettings(ConfigSection):
    url: str = "sqlite+aiosqlite:///./runtime/ai_qa_platform.db"
    echo: bool = False
    pool_size: int = Field(default=20, ge=1, le=256)
    max_overflow: int = Field(default=10, ge=0, le=512)
    sqlite_timeout_seconds: float = Field(default=30.0, gt=0, le=300)


class AIBudgetSettings(ConfigSection):
    enabled: bool = True
    max_request_tokens: int = Field(default=1_000_000, ge=512)
    max_daily_requests: int = Field(default=1000, ge=1)
    max_task_calls: int = Field(default=8, ge=1)
    max_requests_per_run: int = Field(default=50, ge=1)
    max_input_tokens_per_run: int = Field(default=100_000, ge=1)
    max_output_tokens_per_run: int = Field(default=50_000, ge=1)


class AISettings(ConfigSection):
    enabled: bool = True
    provider: str = "fake"
    api_key: SecretStr = SecretStr("")
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    retries: int = Field(default=3, ge=0, le=10)
    budget: AIBudgetSettings = Field(default_factory=AIBudgetSettings)


class JevFailurePolicy(ConfigSection):
    allow_local_fallback: bool = False


class JevSettings(ConfigSection):
    enabled: bool = False
    provider: Literal["jev"] = "jev"
    api_key: SecretStr = SecretStr("")
    model: str = "jev-1.13.0"
    base_url: str = "https://api.typesafe.ai/v1/systemone"
    timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    retries: int = Field(default=1, ge=0, le=5)
    minimum_confidence: float = Field(default=0.60, ge=0, le=1)
    failure_policy: JevFailurePolicy = Field(default_factory=JevFailurePolicy)


class RepairSettings(ConfigSection):
    enabled: bool = True
    mode: Literal["OFF", "ASSISTED", "AUTO"] = "OFF"
    auto_start_on_failure: bool = True
    max_attempts: int = Field(
        default=2,
        ge=1,
        le=10,
        description="Legacy compatibility field; automatic repair retries are disabled.",
    )
    auto_rollback: bool = True
    require_jev: bool = True
    # Automatic repair cannot disable browser evidence verification.
    require_candidate_verification: Literal[True] = True
    locator_same_function_threshold: float = Field(default=0.7, ge=0, le=1)
    # Total budget for one failure analysis. On expiry the analysis ends as TIMEOUT with a retry
    # action instead of staying RUNNING while the operator waits without an answer. Progress events
    # are written per stage and the AI call itself is bounded by ai.timeout_seconds, so this budget
    # only bounds the whole run; it never has to paper over an unbounded provider call.
    analysis_timeout_seconds: float = Field(default=300.0, gt=0, le=600)
    rerun_exact_nodeid: bool = True
    allowed_paths: list[str] = Field(default_factory=lambda: ["tests/**", "pages/**", "helpers/**"])
    denied_paths: list[str] = Field(
        default_factory=lambda: [".github/**", "migrations/**", "secrets/**", "pyproject.toml", "package-lock.json"]
    )


class BrowserSettings(ConfigSection):
    headless: bool = True
    timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    navigation_timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    session_idle_timeout_seconds: float = Field(default=1800.0, gt=0, le=86_400)
    viewport_width: int = Field(default=1280, ge=320, le=7680)
    viewport_height: int = Field(default=720, ge=240, le=4320)
    locale: str = "en-US"
    timezone: str = "UTC"
    args: list[str] = Field(default_factory=lambda: ["--no-sandbox", "--disable-dev-shm-usage"])
    proxy_url: SecretStr = SecretStr("")
    proxy_bypass: str = ""


class RunSettings(ConfigSection):
    default_timeout_seconds: float = Field(default=120.0, gt=0, le=86_400)
    max_parallel_runs: int = Field(default=4, ge=1, le=256)


class PytestSettings(ConfigSection):
    workers: int = Field(default=1, ge=1, le=16)
    timeout_seconds: float = Field(default=120.0, gt=0, le=86_400)
    default_args: list[str] = Field(default_factory=list)


class AgentBrowserSettings(ConfigSection):
    require_jev: bool = False
    max_actions: int = Field(default=30, ge=1, le=500)
    max_candidates: int = Field(default=10, ge=1, le=100)


class AgentSettings(ConfigSection):
    enabled: bool = True
    max_steps: int = Field(default=30, ge=1, le=500)
    max_runtime_seconds: float = Field(default=900.0, gt=0, le=86_400)
    max_retries: int = Field(default=2, ge=0, le=20)
    browser: AgentBrowserSettings = Field(default_factory=AgentBrowserSettings)


class DiscoverySettings(ConfigSection):
    enabled: bool = True
    require_ai: bool = True
    require_jev: bool = True
    max_actions: int = Field(default=30, ge=1, le=300)
    max_failures: int = Field(default=20, ge=1, le=100)
    max_depth: int = Field(default=8, ge=1, le=32)
    max_states: int = Field(default=100, ge=1, le=500)
    max_runtime_minutes: int = Field(default=45, ge=1, le=240)
    max_candidates: int = Field(default=5, ge=1, le=20)
    screenshot: bool = True
    capture_console: bool = True
    capture_network: bool = True
    safe_mode: Literal[True] = True
    allowed_domains: list[str] = Field(default_factory=list, max_length=20)
    state_similarity_threshold: float = Field(default=0.9, ge=0.5, le=1)
    feature_mapping_confidence: float = Field(default=0.75, ge=0, le=1)
    max_events: int = Field(default=500, ge=20, le=5000)
    max_evidence_chars: int = Field(default=9000, ge=1000, le=100_000)
    max_screenshots: int = Field(default=20, ge=0, le=200)
    #: Frame cadence of the live discovery stream; frames are viewport-only and never persisted.
    live_frame_interval_ms: int = Field(default=1000, ge=100, le=10_000)
    #: Structured evidence capture (dom_element / locator_candidate / network_request / user_action).
    #: Every limit here is a resource budget: the run records how much it filtered, never silently drops.
    capture_evidence: bool = True
    max_evidence_records: int = Field(default=6000, ge=0, le=100_000)
    max_network_evidence: int = Field(default=200, ge=0, le=2000)
    max_payload_chars: int = Field(default=2000, ge=200, le=20_000)


class FailureSettings(ConfigSection):
    auto_create: bool = True
    capture_screenshot: bool = True
    capture_dom: bool = True
    capture_console: bool = True
    capture_network: bool = True
    traceback_chars: int = Field(default=8000, ge=0, le=1_000_000)
    source_context_chars: int = Field(default=8000, ge=0, le=1_000_000)
    storage_state_ttl_seconds: int = Field(default=604800, ge=60, le=2_592_000)


class EvidenceSettings(ConfigSection):
    # Current failure records attach at most one last-frame screenshot per failure.
    max_screenshots: int = Field(default=1, ge=0, le=1)
    max_console_entries: int = Field(default=30, ge=0, le=100_000)
    max_network_entries: int = Field(default=30, ge=0, le=100_000)
    max_dom_chars: int = Field(default=14_000, ge=0, le=10_000_000)


class RecorderSettings(ConfigSection):
    enabled: bool = True
    locator_strategy: Literal["semantic", "role", "test_id", "label", "placeholder", "text", "css", "xpath"] = (
        "semantic"
    )
    candidate_limit: int = Field(default=10, ge=1, le=100)


class DebuggerSettings(ConfigSection):
    startup_timeout_seconds: float = Field(default=10.0, gt=0, le=300)
    attach_timeout_seconds: float = Field(default=10.0, gt=0, le=300)
    shutdown_grace_timeout_seconds: float = Field(default=3.0, gt=0, le=60)
    shutdown_force_timeout_seconds: float = Field(default=2.0, gt=0, le=60)


class WorkerSettings(ConfigSection):
    api_url: str = "http://127.0.0.1:8000"
    auth_token: SecretStr = SecretStr("")
    name: str = "Runner-Node-1"
    capabilities: list[str] = Field(
        default_factory=lambda: ["playwright", "chromium", "firefox", "webkit", "pytest", "python3"]
    )
    max_concurrency: int = Field(default=4, ge=1, le=256)
    heartbeat_interval_seconds: float = Field(default=10.0, gt=0, le=3600)
    poll_interval_seconds: float = Field(default=3.0, gt=0, le=3600)
    http_timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    workspace_storage_dir: Path = Path("./runtime/workspaces")
    artifact_storage_dir: Path = Path("./runtime/artifacts")


class IntegrationServiceSettings(ConfigSection):
    enabled: bool = False
    base_url: str = ""
    username: str = ""
    token: SecretStr = SecretStr("")


class IntegrationSettings(ConfigSection):
    github: IntegrationServiceSettings = Field(default_factory=IntegrationServiceSettings)
    jira: IntegrationServiceSettings = Field(default_factory=IntegrationServiceSettings)
    testrail: IntegrationServiceSettings = Field(default_factory=IntegrationServiceSettings)
    jenkins: IntegrationServiceSettings = Field(default_factory=IntegrationServiceSettings)


class FeatureSettings(ConfigSection):
    ai_repair: bool = True
    jev_decision: bool = True
    auto_repair: bool = True
    recorder: bool = True
    debugger: bool = True
    live_browser: bool = True


class LoggingSettings(ConfigSection):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


class AppConfig(ConfigSection):
    version: Literal[1] = 1
    app: AppSettings = Field(default_factory=AppSettings)
    api: APISettings = Field(default_factory=APISettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    ai: AISettings = Field(default_factory=AISettings)
    jev: JevSettings = Field(default_factory=JevSettings)
    repair: RepairSettings = Field(default_factory=RepairSettings)
    browser: BrowserSettings = Field(default_factory=BrowserSettings)
    run: RunSettings = Field(default_factory=RunSettings)
    pytest: PytestSettings = Field(default_factory=PytestSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    discovery: DiscoverySettings = Field(default_factory=DiscoverySettings)
    failure: FailureSettings = Field(default_factory=FailureSettings)
    evidence: EvidenceSettings = Field(default_factory=EvidenceSettings)
    recorder: RecorderSettings = Field(default_factory=RecorderSettings)
    debugger: DebuggerSettings = Field(default_factory=DebuggerSettings)
    worker: WorkerSettings = Field(default_factory=WorkerSettings)
    integrations: IntegrationSettings = Field(default_factory=IntegrationSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    features: FeatureSettings = Field(default_factory=FeatureSettings)

    @model_validator(mode="after")
    def validate_cross_field_policy(self) -> AppConfig:
        if self.app.environment == "production" and len(self.app.secret_key.get_secret_value()) < 32:
            raise ValueError("app.secret_key must be at least 32 characters in production")
        if self.repair.enabled and self.repair.mode == "AUTO" and self.repair.require_jev and not self.jev.enabled:
            raise ValueError("repair.mode=AUTO with repair.require_jev=true requires jev.enabled=true")
        if self.repair.enabled and self.repair.mode == "AUTO" and self.features.ai_repair and not self.ai.enabled:
            raise ValueError("repair.mode=AUTO with features.ai_repair=true requires ai.enabled=true")
        if self.agent.browser.require_jev and self.agent.enabled and not self.jev.enabled:
            # Jev is optional for an OFF repair policy; agent browser decisions are a separate policy.
            raise ValueError("agent.browser.require_jev=true requires jev.enabled=true")
        return self


def secret_values(config: AppConfig) -> dict[str, str]:
    """Return secret fields for runtime consumers; never use these in serialized diagnostics."""
    return {
        "app.secret_key": config.app.secret_key.get_secret_value(),
        "ai.api_key": config.ai.api_key.get_secret_value(),
        "jev.api_key": config.jev.api_key.get_secret_value(),
        "browser.proxy_url": config.browser.proxy_url.get_secret_value(),
        "worker.auth_token": config.worker.auth_token.get_secret_value(),
        "integrations.github.token": config.integrations.github.token.get_secret_value(),
        "integrations.jira.token": config.integrations.jira.token.get_secret_value(),
        "integrations.testrail.token": config.integrations.testrail.token.get_secret_value(),
        "integrations.jenkins.token": config.integrations.jenkins.token.get_secret_value(),
    }
