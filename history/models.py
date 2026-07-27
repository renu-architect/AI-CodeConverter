"""SQLAlchemy models for migration history database."""

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    TIMESTAMP,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


class Project(Base):
    __tablename__ = "projects"
    project_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    repo_path = Column(String, nullable=False)
    repo_hash = Column(String, nullable=False)
    developer = Column(String)
    status = Column(String, default="active")
    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)
    workflows = relationship("Workflow", back_populates="project")


class Workflow(Base):
    __tablename__ = "workflows"
    workflow_id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.project_id"))
    stage = Column(String, default="IDLE")
    progress_pct = Column(Float, default=0.0)
    current_agent = Column(String)
    current_file = Column(String)
    iteration = Column(Integer, default=1)
    started_at = Column(TIMESTAMP)
    completed_at = Column(TIMESTAMP)
    elapsed_seconds = Column(Integer, default=0)
    tokens_used = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    status = Column(String, default="running")
    error = Column(Text)
    checkpoint = Column(Text)
    project = relationship("Project", back_populates="workflows")
    migrations = relationship("Migration", back_populates="workflow")


class Migration(Base):
    __tablename__ = "migrations"
    migration_id = Column(String, primary_key=True)
    workflow_id = Column(String, ForeignKey("workflows.workflow_id"))
    project_id = Column(String, nullable=False)
    job_id = Column(String, nullable=False)
    job_name = Column(String, nullable=False)
    source_file = Column(String, nullable=False)
    complexity_score = Column(Float)
    review_score = Column(Float)
    validation_score = Column(Float)
    iterations_impl = Column(Integer, default=0)
    iterations_review = Column(Integer, default=0)
    status = Column(String, default="pending")
    started_at = Column(TIMESTAMP)
    completed_at = Column(TIMESTAMP)
    workflow = relationship("Workflow", back_populates="migrations")


class ArtifactRecord(Base):
    __tablename__ = "artifacts"
    artifact_id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False)
    job_id = Column(String, nullable=False)
    migration_id = Column(String, ForeignKey("migrations.migration_id"))
    artifact_type = Column(String, nullable=False)
    version = Column(Integer, nullable=False)
    file_path = Column(String, nullable=False)
    content_hash = Column(String, nullable=False)
    size_bytes = Column(Integer)
    created_at = Column(TIMESTAMP)
    created_by = Column(String)


class LLMCall(Base):
    __tablename__ = "llm_calls"
    call_id = Column(String, primary_key=True)
    workflow_id = Column(String, nullable=False)
    migration_id = Column(String)
    agent_name = Column(String, nullable=False)
    prompt_template = Column(String, nullable=False)
    prompt_version = Column(String, nullable=False)
    model = Column(String, nullable=False)
    tokens_input = Column(Integer, nullable=False)
    tokens_output = Column(Integer, nullable=False)
    cost_usd = Column(Float, nullable=False)
    latency_ms = Column(Integer, nullable=False)
    cached = Column(Boolean, default=False)
    success = Column(Boolean, default=True)
    error = Column(Text)
    created_at = Column(TIMESTAMP)


class Approval(Base):
    __tablename__ = "approvals"
    approval_id = Column(String, primary_key=True)
    workflow_id = Column(String, ForeignKey("workflows.workflow_id"))
    migration_id = Column(String)
    developer = Column(String, nullable=False)
    approved = Column(Boolean, nullable=False)
    comments = Column(Text)
    plan_version = Column(Integer)
    estimated_cost = Column(Float)
    estimated_tokens = Column(Integer)
    created_at = Column(TIMESTAMP)


class KnowledgeEntry(Base):
    __tablename__ = "knowledge_entries"
    entry_id = Column(String, primary_key=True)
    project_id = Column(String)
    job_id = Column(String)
    collection = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    embedding_id = Column(String)
    confidence = Column(Float)
    source = Column(String)
    created_at = Column(TIMESTAMP)


class MetricsDaily(Base):
    __tablename__ = "metrics_daily"
    date = Column(String, primary_key=True)
    total_jobs = Column(Integer, default=0)
    completed_jobs = Column(Integer, default=0)
    failed_jobs = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    total_cost_usd = Column(Float, default=0.0)
    avg_review_score = Column(Float)
    avg_validation_score = Column(Float)
    avg_iterations = Column(Float)
    avg_duration_seconds = Column(Float)
    cache_hits = Column(Integer, default=0)
    knowledge_hits = Column(Integer, default=0)


def init_db(database_url: str):
    """Create all tables if they do not exist."""
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)
