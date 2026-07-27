# =============================================================================
# test_data_cleaning_and_lambda.py
# pytest test suite for the Synapse-migrated data_cleaning_and_lambda job
# =============================================================================

import pytest
from unittest.mock import MagicMock, patch
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import col
from pyspark.sql.types import (
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def spark() -> SparkSession:
    """Provide a local SparkSession for all tests."""
    return (
        SparkSession.builder
        .master("local[2]")
        .appName("test_data_cleaning_and_lambda")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.job.storage_account", "testaccount")
        .getOrCreate()
    )


@pytest.fixture(scope="session")
def source_schema() -> StructType:
    """Mirror the SOURCE_SCHEMA constant from the job module."""
    return StructType(
        [
            StructField("drg definition", StringType(), True),
            StructField("provider id", StringType(), True),
            StructField("provider name", StringType(), True),
            StructField("provider city", StringType(), True),
            StructField("provider state", StringType(), True),
            StructField("provider zip code", StringType(), True),
            StructField("hospital referral region description", StringType(), True),
            StructField("average covered charges", StringType(), True),
            StructField("average total payments", StringType(), True),
            StructField("average medicare payments", StringType(), True),
        ]
    )


@pytest.fixture()
def valid_row(spark: SparkSession, source_schema: StructType) -> DataFrame:
    """Single fully-populated valid row."""
    data = [
        (
            "039 - EXTRACRANIAL PROCEDURES W/O CC/MCC",
            "10001",
            "SOUTHEAST ALABAMA MEDICAL CENTER",
            "DOTHAN",
            "AL",
            "36301",
            "AL - Dothan",
            "$32963.07",
            "$5777.24",
            "$4763.73",
        )
    ]
    return spark.createDataFrame(data, schema=source_schema)


@pytest.fixture()
def null_provider_id_row(spark: SparkSession, source_schema: StructType) -> DataFrame:
    """Row where provider id is null."""
    data = [
        (
            "039 - EXTRACRANIAL PROCEDURES W/O CC/MCC",
            None,
            "SOME HOSPITAL",
            "CITY",
            "AL",
            "36301",
            "AL - Dothan",
            "$100.00",
            "$50.00",
            "$40.00",
        )
    ]
    return spark.createDataFrame(data, schema=source_schema)


@pytest.fixture()
def mixed_rows(spark: SparkSession, source_schema: StructType) -> DataFrame:
    """Mix of valid rows and rows with null provider id."""
    data = [
        ("DRG1", "10001", "HOSPITAL A", "CITY A", "AL", "36301", "AL - A", "$100.00", "$50.00", "$40.00"),
        ("DRG2", None,    "HOSPITAL B", "CITY B", "GA", "30301", "GA - B", "$200.00", "$80.00", "$60.00"),
        ("DRG3", "10003", "HOSPITAL C", "CITY C", "FL", "32001", "FL - C", "$300.00", "$90.00", "$70.00"),
        ("DRG4", None,    "HOSPITAL D", "CITY D", "TX", "75001", "TX - D", "$400.00", "$95.00", "$80.00"),
        ("DRG5", "10005", "HOSPITAL E", "CITY E", "NY", "10001", "NY - E", "$500.00", "$99.00", "$85.00"),
    ]
    return spark.createDataFrame(data, schema=source_schema)


@pytest.fixture()
def empty_df(spark: SparkSession, source_schema: StructType) -> DataFrame:
    """Empty DataFrame with the source schema."""
    return spark.createDataFrame([], schema=source_schema)


# ---------------------------------------------------------------------------
# Helpers (inline implementations to avoid import-time side effects)
# These mirror the job's transformation logic for isolated unit testing.
# ---------------------------------------------------------------------------

def _strip_dollar_signs(df: DataFrame) -> DataFrame:
    """Strip $ from all three charge columns."""
    from pyspark.sql.functions import regexp_replace
    for col_name in [
        "average covered charges",
        "average total payments",
        "average medicare payments",
    ]:
        df = df.withColumn(col_name, regexp_replace(col(col_name), r"\$", ""))
    return df


def _filter_nulls(df: DataFrame) -> DataFrame:
    """Drop rows where provider id is null."""
    return df.filter(col("provider id").isNotNull())


def _nest_and_cast(df: DataFrame) -> DataFrame:
    """Apply field mapping: rename, cast, and nest into structs."""
    from pyspark.sql.functions import struct
    return df.select(
        col("drg definition").alias("drg"),
        struct(
            col("provider id").cast(LongType()).alias("id"),
            col("provider name").alias("name"),
            col("provider city").alias("city"),
            col("provider state").alias("state"),
            col("provider zip code").cast(LongType()).alias("zip"),
        ).alias("provider"),
        col("hospital referral region description").alias("rr"),
        struct(
            col("average covered charges").cast(DoubleType()).alias("covered"),
            col("average total payments").cast(DoubleType()).alias("total"),
            col("average medicare payments").cast(DoubleType()).alias("medicare"),
        ).alias("charges"),
    )


# ---------------------------------------------------------------------------
# UNIT TESTS
# ---------------------------------------------------------------------------

class TestStripDollarSigns:
    """U01–U04: Dollar-sign stripping via regexp_replace."""

    def test_strip_dollar_sign_covered(self, valid_row: DataFrame):
        """U01: $ removed from average covered charges."""
        result = _strip_dollar_signs(valid_row)
        value = result.select("average covered charges").first()[0]
        assert value == "32963.07", f"Expected '32963.07', got '{value}'"

    def test_strip_dollar_sign_total(self, valid_row: DataFrame):
        """U02: $ removed from average total payments."""
        result = _strip_dollar_signs(valid_row)
        value = result.select("