"""Pydantic configuration models for AI-SDLC framework."""

from pydantic import BaseModel, Field


from utils.claude_models import DEFAULT_CLAUDE_MODEL


class ClaudeConfig(BaseModel):
    model: str = DEFAULT_CLAUDE_MODEL
    temperature: float = 0.0
    max_retries: int = 3
    timeout_seconds: int = 120
    api_key: str = ""


class CacheConfig(BaseModel):
    enabled: bool = True
    directory: str = "cache/"
    ttl_seconds: int = 86400


class KnowledgeConfig(BaseModel):
    embedding_model: str = "all-MiniLM-L6-v2"
    chroma_persist_dir: str = "knowledge/vector_db/"
    top_k: int = 5
    collections: list[str] = Field(
        default_factory=lambda: [
            "glue_patterns",
            "synapse_patterns",
            "corrections",
            "business_rules",
        ]
    )


class AgentConfig(BaseModel):
    max_context_tokens: int = 24000
    max_output_tokens: int = 4096
    prompt_version: str = "1.0"
    validation_threshold: int = 85
    max_implement_iterations: int = 3
    max_review_iterations: int = 3
    reuse_artifacts: bool = True
    poc_mode: bool = True


class PromptConfig(BaseModel):
    mode: str = "on"


class DemoConfig(BaseModel):
    enabled: bool = True
    default_repo: str = "GlueRepo"
    default_job: str = "data_cleaning_and_lambda"
    stage_delay_seconds: float = 0.35
    auto_approve_plan: bool = True


class ScannerConfig(BaseModel):
    max_file_size_mb: int = 10
    ignore_patterns: list[str] = Field(
        default_factory=lambda: ["__pycache__", ".git", "node_modules", "*.pyc", ".venv"]
    )


class CostEstimationConfig(BaseModel):
    input_price_per_million: float = 3.0
    output_price_per_million: float = 15.0


class CodingStandardsConfig(BaseModel):
    python_version: str = "3.12"
    style: str = "PEP8"
    type_hints: bool = True
    logging_module: str = "logging"
    error_handling: bool = True
    rules: list[str] = Field(default_factory=list)


class AppConfig(BaseModel):
    name: str = "AI-SDLC Framework"
    version: str = "1.0.0"
    log_level: str = "INFO"
    output_dir: str = "outputs/"
    artifacts_dir: str = "artifacts/"
    claude: ClaudeConfig = Field(default_factory=ClaudeConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)
    agents: AgentConfig = Field(default_factory=AgentConfig)
    scanner: ScannerConfig = Field(default_factory=ScannerConfig)
    cost_estimation: CostEstimationConfig = Field(default_factory=CostEstimationConfig)
    coding_standards: CodingStandardsConfig = Field(default_factory=CodingStandardsConfig)
    prompts: PromptConfig = Field(default_factory=PromptConfig)
    demo: DemoConfig = Field(default_factory=DemoConfig)
    database_url: str = "sqlite:///history/aisdlc.db"
