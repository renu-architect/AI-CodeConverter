"""Enumerations used across the AI-SDLC framework."""

from enum import Enum


class WorkflowStage(str, Enum):
    IDLE = "IDLE"
    SCANNING = "SCANNING"
    ANALYZING = "ANALYZING"
    PLANNING = "PLANNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    IMPLEMENTING = "IMPLEMENTING"
    REVIEWING = "REVIEWING"
    VALIDATING = "VALIDATING"
    TESTING = "TESTING"
    DOCUMENTING = "DOCUMENTING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ArtifactType(str, Enum):
    PROJECT_JSON = "project.json"
    UNDERSTANDING = "Understanding.md"
    MIGRATION_PLAN = "MigrationPlan.md"
    CONVERTED_CODE = "converted_code"
    CONVERSION_NOTES = "ConversionNotes.md"
    MIGRATION_SUMMARY = "MigrationSummary.md"
    REVIEW = "Review.md"
    VALIDATION = "Validation.md"
    TEST_CASES = "TestCases.md"
    README = "README.md"
    METRICS = "Metrics.json"
    APPROVAL = "approval_record.json"


class ReviewStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"


class ComplexityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PromptMode(str, Enum):
    OFF = "off"
    ON = "on"
    MEDIUM = "medium"
    PRO = "pro"
    ULTRA = "ultra"
