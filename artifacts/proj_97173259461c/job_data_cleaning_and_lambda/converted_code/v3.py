# data_cleaning_and_lambda_synapse.py
# Migrated from AWS Glue: data_cleaning_and_lambda.py
# Migration Plan Version: 1.0 | Date: 2025-01-01
# Developer Approval Required: YES
#
# SECURITY NOTE: Replace '<storage_account>' references by passing
# --storage_account as a Synapse pipeline parameter or retrieving via
# mssparkutils.credentials. The Synapse workspace managed identity must
# hold 'Storage Blob Data Contributor' on both source and target containers.

import logging
import sys
from typing import Optional

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import col, regexp_replace, struct
from pyspark.sql.types import (
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# FIX (security): '<storage_account>' is a placeholder. Supply the real value
# via a Synapse pipeline parameter or mssparkutils secret retrieval.
# Example Synapse pipeline parameter pattern:
#   storage_account = getArgument("storage_account")
# and then build the paths dynamically. The literals below will cause a
# runtime failure if left unchanged.
INPUT_PATH: str = (
    "abfss://source@<storage_account>.dfs.core.windows.net/medicare/inpatient/"
)
OUTPUT_PATH: str = (
    "abfss://output@<storage_account>.dfs.core.windows.net/medicare/cleaned/"
)

# FIX (schema_mapping / code_completeness): 'total discharges' is retained in
# SOURCE_SCHEMA for ingestion completeness but is intentionally excluded from
# the nest_and_cast() output, matching the original apply_mapping behaviour.
# 'provider zip code' is ingested as StringType() here; it is explicitly cast
# to LongType() inside nest_and_cast(), matching the original job's output.
# StructType / StructField are used below to declare SOURCE_SCHEMA.
SOURCE_SCHEMA: StructType = StructType(
    [
        StructField("drg definition", StringType(), True),
        StructField("provider id", StringType(), True),
        StructField("provider name", StringType(), True),
        StructField("provider city", StringType(), True),
        StructField("provider state", StringType(), True),
        StructField("provider zip code", StringType(), True),   # cast → LongType in nest_and_cast
        StructField("hospital referral region description", StringType(), True),
        StructField("total discharges", StringType(), True),    # retained for ingestion; not in output
        StructField("average covered charges", StringType(), True),
        StructField("average total payments", StringType(), True),
        StructField("average medicare payments", StringType(), True),
    ]
)

# FIX (transformations / filter_nulls): Reverted to match the original Glue
# job which filters ONLY on 'provider id' being NOT NULL. The previous
# conversion expanded this to six columns, which could silently drop valid
# records. If additional null checks are required in future, document them
# explicitly and obtain business-owner sign-off before adding them here.
NULL_FILTER_COLUMN: str = "provider id"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)
logger: logging.Logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def get_spark() -> SparkSession:
    """Return the active SparkSession (created by Synapse runtime)."""
    return SparkSession.builder.getOrCreate()


def read_source(spark: SparkSession, path: str) -> DataFrame:
    """Read raw Medicare CSV data from ADLS Gen2.

    Args:
        spark: Active SparkSession.
        path:  ADLS Gen2 abfss:// URI for the source CSV files.

    Returns:
        Raw DataFrame with SOURCE_SCHEMA applied.
    """
    logger.info("Reading source data from: %s", path)
    df: DataFrame = (
        spark.read.format("csv")
        .option("header", "true")
        .option("inferSchema", "false")
        .schema(SOURCE_SCHEMA)
        .load(path)
    )
    logger.info("Source row count: %d", df.count())
    return df


def resolve_provider_id(df: DataFrame) -> DataFrame:
    """Resolve ambiguous 'provider id' column type to string.

    Equivalent to the Glue resolveChoice(specs=[('provider id', 'cast:string')])
    call. In native PySpark the column is already StringType() from SOURCE_SCHEMA,
    so this step re-casts explicitly to guarantee contract and mirrors the
    original pipeline stage.

    Args:
        df: Input DataFrame.

    Returns:
        DataFrame with 'provider id' guaranteed as StringType.
    """
    logger.info("Resolving 'provider id' to StringType")
    return df.withColumn("provider id", col("provider id").cast(StringType()))


def filter_nulls(df: DataFrame) -> DataFrame:
    """Remove records where 'provider id' is NULL.

    FIX (transformations): Matches the original Glue job which filters ONLY
    on 'provider id'. The previous conversion incorrectly filtered on six
    columns (NULL_FILTER_COLUMNS list), risking silent record loss.

    Args:
        df: Input DataFrame.

    Returns:
        DataFrame containing only rows where 'provider id' IS NOT NULL.
    """
    logger.info("Filtering NULL values on column: '%s'", NULL_FILTER_COLUMN)
    before: int = df.count()
    filtered: DataFrame = df.where(col(f"`{NULL_FILTER_COLUMN}`").isNotNull())
    after: int = filtered.count()
    logger.info("filter_nulls dropped %d record(s) (%d → %d)", before - after, before, after)
    return filtered


def strip_currency(df: DataFrame) -> DataFrame:
    """Strip leading '$' characters from currency string columns.

    FIX (transformations): The original Glue job applied a Python lambda UDF
    (chop_f) to remove the leading '$' from 'average covered charges',
    'average total payments', and 'average medicare payments', storing the
    results in new columns ACC, ATP, and AMP respectively.

    The previous conversion referenced regexp_replace in a comment but never
    applied it, so ACC, ATP, and AMP were never created. This function
    replaces the Python UDF with the native PySpark regexp_replace function,
    eliminating Python serialisation (pickle) overhead while preserving
    identical output semantics.

    Args:
        df: Input DataFrame containing the three raw currency columns.

    Returns:
        DataFrame with additional columns ACC, ATP, and AMP (strings,
        '$' prefix removed), ready for casting in nest_and_cast().
    """
    logger.info(
        "Stripping leading '$' from currency columns → ACC, ATP, AMP "
        "(native regexp_replace; replaces original chop_f Python UDF)"
    )
    # FIX: Performance — replaced Python UDF (_strip_leading_char) with native
    # regexp_replace to eliminate Python serialization overhead (pickle round-
    # trip per row). Semantics are identical: remove a single leading '$'.
    df = (
        df
        .withColumn("ACC", regexp_replace(col("average covered charges"), r"^\$", ""))
        .withColumn("ATP", regexp_replace(col("average total payments"), r"^\$", ""))
        .withColumn("AMP", regexp_replace(col("average medicare payments"), r"^\$", ""))
    )
    return df


def nest_and_cast(df: DataFrame) -> DataFrame:
    """Restructure flat columns into nested provider and charges structs.

    FIX (transformations): The apply_mapping equivalent was entirely absent
    from the converted code. This function replicates the original Glue
    apply_mapping call which:
      - Renames and casts flat columns into a 'provider' struct:
            provider.id        ← provider id        (cast LongType)
            provider.name      ← provider name       (StringType)
            provider.city      ← provider city       (StringType)
            provider.state     ← provider state      (StringType)
            provider.zip       ← provider zip code   (cast LongType)
      - Renames and casts flat columns into a 'charges' struct:
            charges.covered    ← ACC  (cast DoubleType)
            charges.total_pay  ← ATP  (cast DoubleType)
            charges.medicare_pay ← AMP (cast DoubleType)
      - Retains top-level scalar columns:
            drg  ← drg definition
            rr   ← hospital referral region description
      - 'total discharges' is intentionally excluded, matching the original
        apply_mapping output (see SOURCE_SCHEMA note above).

    Args:
        df: DataFrame produced by strip_currency(), containing ACC, ATP, AMP.

    Returns:
        DataFrame with nested 'provider' and 'charges' struct columns.
    """
    logger.info("Applying nest_and_cast: restructuring flat columns into nested structs")
    nested: DataFrame = df.select(
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
            col("ACC").cast(DoubleType()).alias("covered"),
            col("ATP").cast(DoubleType()).alias("total_pay"),
            col("AMP").cast(DoubleType()).alias("medicare_pay"),
        ).alias("charges"),
    )
    logger.info("nest_and_cast complete. Output columns: %s", nested.columns)
    return nested


def write_output(df: DataFrame, path: str) -> None:
    """Write the final DataFrame to ADLS Gen2 in Parquet format.

    FIX (output_targets): No write step existed in the converted code.
    OUTPUT_PATH was defined as a constant but never used. This function
    replicates the original Glue job's
    glueContext.write_dynamic_frame.from_options(..., format='glueparquet')
    call using native PySpark Parquet writer.

    Prerequisite: The Synapse workspace managed identity (or the configured
    linked service principal) must hold the 'Storage Blob Data Contributor'
    role on the target ADLS Gen2 container.

    Args:
        df:   Final transformed DataFrame.
        path: ADLS Gen2 abfss:// URI for the Parquet output location.
    """
    logger.info("Writing output to: %s (format=parquet, mode=overwrite)", path)
    df.write.mode("overwrite").parquet(path)
    logger.info("Write complete.")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def main() -> None:
    """Execute the full Medicare data-cleaning pipeline.

    Pipeline stages (mirrors original Glue job sequence):
        1. read_source        — load raw CSV from ADLS Gen2
        2. resolve_provider_id — cast 'provider id' to StringType
        3. filter_nulls       — drop rows where 'provider id' IS NULL
        4. strip_currency     — remove '$' prefix → ACC, ATP, AMP columns
        5. nest_and_cast      — restructure into provider/charges structs
        6. write_output       — persist Parquet to ADLS Gen2

    FIX (code_completeness): The original converted file was truncated and
    lacked any orchestration entry point. This function and the
    __main__ guard below complete the pipeline.
    """
    logger.info("=== data_cleaning_and_lambda pipeline START ===")

    spark: SparkSession = get_spark()

    df: DataFrame = read_source(spark, INPUT_PATH)
    df = resolve_provider_id(df)
    df = filter_nulls(df)
    df = strip_currency(df)
    df = nest_and_cast(df)
    write_output(df, OUTPUT_PATH)

    logger.info("=== data_cleaning_and_lambda pipeline END ===")


if __name__ == "__main__":
    main()