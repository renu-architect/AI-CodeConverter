# ============================================================
# data_cleaning_and_lambda_synapse.py
# Migrated from AWS Glue → Azure Synapse Spark
# Migration Plan Version: 1.0
# ============================================================

import logging
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
INPUT_PATH: str = "abfss://raw@<storage_account>.dfs.core.windows.net/medicare/"
OUTPUT_PATH: str = "abfss://curated@<storage_account>.dfs.core.windows.net/medicare_nested/"

SOURCE_SCHEMA = StructType(
    [
        StructField("drg definition", StringType(), True),
        StructField("provider id", StringType(), True),
        StructField("provider name", StringType(), True),
        StructField("provider city", StringType(), True),
        StructField("provider state", StringType(), True),
        StructField("provider zip code", StringType(), True),
        StructField("hospital referral region description", StringType(), True),
        StructField("total discharges", StringType(), True),
        StructField("average covered charges", StringType(), True),
        StructField("average total payments", StringType(), True),
        StructField("average medicare payments", StringType(), True),
    ]
)

# Columns that must be non-null for a record to be considered valid
NULL_FILTER_COLUMNS: list[str] = [
    "drg definition",
    "provider id",
    "provider name",
    "average covered charges",
    "average total payments",
    "average medicare payments",
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------


def get_spark() -> SparkSession:
    """Return the active SparkSession (created by Synapse runtime)."""
    return SparkSession.builder.getOrCreate()


def read_source(spark: SparkSession, path: str) -> DataFrame:
    """Read raw Medicare CSV data from ADLS Gen2.

    Parameters
    ----------
    spark:
        Active SparkSession.
    path:
        ADLS Gen2 ``abfss://`` URI pointing to the source CSV files.

    Returns
    -------
    DataFrame
        Flat DataFrame conforming to ``SOURCE_SCHEMA`` with header row
        consumed and all columns typed as ``StringType`` pending downstream
        casting.
    """
    logger.info("Reading source CSV from: %s", path)
    df: DataFrame = (
        spark.read.option("header", "true")
        .option("inferSchema", "false")
        .schema(SOURCE_SCHEMA)
        .csv(path)
    )
    logger.info("Source row count (pre-filter): %d", df.count())
    return df


def resolve_provider_id(df: DataFrame) -> DataFrame:
    """Resolve ambiguous ``provider id`` values.

    Mirrors the Glue ``resolveChoice(specs=[('provider id', 'cast:long')])``
    step.  Values that cannot be cast produce ``null``, which the subsequent
    ``filter_nulls`` step will drop.

    Parameters
    ----------
    df:
        Input DataFrame with ``provider id`` as ``StringType``.

    Returns
    -------
    DataFrame
        DataFrame with ``provider id`` cast to ``LongType``.
    """
    logger.info("Resolving provider id to LongType")
    return df.withColumn(
        "provider id",
        col("provider id").cast(LongType()),
    )


def filter_nulls(df: DataFrame, columns: list[str]) -> DataFrame:
    """Drop rows where any of the specified columns contain null values.

    Mirrors the Glue ``Filter.apply`` step that removed records with null
    ``provider id`` or null charge columns.

    Parameters
    ----------
    df:
        Input DataFrame.
    columns:
        Column names to check for nulls; a row is dropped if *any* of these
        columns is null.

    Returns
    -------
    DataFrame
        DataFrame with null rows removed.
    """
    logger.info("Filtering nulls on columns: %s", columns)
    condition = None
    for column in columns:
        not_null = col(column).isNotNull()
        condition = not_null if condition is None else condition & not_null
    filtered_df: DataFrame = df.filter(condition)  # type: ignore[arg-type]
    logger.info("Row count after null filter: %d", filtered_df.count())
    return filtered_df


# FIX: Performance — replaced Python UDF (_strip_leading_char) with native
# regexp_replace to eliminate Python serialization overhead (pickle round-trip
# per row).  regexp_replace executes on the JVM, handles nulls natively, and
# requires no custom null guard.  Addresses severity=LOW finding at lines
# 97-100.
def apply_currency_strip(df: DataFrame) -> DataFrame:
    """Strip leading ``$`` characters from currency string columns.

    Replaces the original Python lambda UDF with the native Spark
    ``regexp_replace`` function.  This keeps execution on the JVM and avoids
    Python serialization overhead on large datasets.

    Affected columns
    ----------------
    * ``average covered charges``  → intermediate column ``ACC``
    * ``average total payments``   → intermediate column ``ATP``
    * ``average medicare payments``→ intermediate column ``AMP``

    Parameters
    ----------
    df:
        Input DataFrame containing raw currency string columns.

    Returns
    -------
    DataFrame
        DataFrame with ``ACC``, ``ATP``, and ``AMP`` columns appended as
        cleaned numeric strings (still ``StringType``; cast occurs in
        ``apply_mapping_equivalent``).
    """
    logger.info("Stripping leading '$' from currency columns via regexp_replace")
    return (
        df.withColumn(
            "ACC",
            regexp_replace(col("average covered charges"), r"^\$", ""),
        )
        .withColumn(
            "ATP",
            regexp_replace(col("average total payments"), r"^\$", ""),
        )
        .withColumn(
            "AMP",
            regexp_replace(col("average medicare payments"), r"^\$", ""),
        )
    )


# FIX: Business Logic — implements the Glue apply_mapping equivalent using
# PySpark struct() and col() with explicit casts.  Produces the nested schema:
#   drg        StringType
#   provider   StructType { id LongType, name StringType, city StringType,
#                           state StringType, zip LongType }
#   rr         StringType
#   charges    StructType { covered DoubleType, total_pay DoubleType,
#                           medicare_pay DoubleType }
# Addresses severity=CRITICAL Business Logic finding.
def apply_mapping_equivalent(df: DataFrame) -> DataFrame:
    """Restructure the flat DataFrame into the target nested schema.

    This function is the direct equivalent of the AWS Glue
    ``apply_mapping`` call that produced nested ``provider`` and ``charges``
    structs.  It uses PySpark ``struct()`` and ``col()`` with explicit casts
    to mirror the original field-level type mappings.

    Target schema
    -------------
    .. code-block:: text

        root
         |-- drg: string
         |-- provider: struct
         |    |-- id: long
         |    |-- name: string
         |    |-- city: string
         |    |-- state: string
         |    |-- zip: long
         |-- rr: string
         |-- charges: struct
         |    |-- covered: double
         |    |-- total_pay: double
         |    |-- medicare_pay: double

    Parameters
    ----------
    df:
        Flat DataFrame produced by ``apply_currency_strip``.  Must contain
        ``ACC``, ``ATP``, and ``AMP`` intermediate columns.

    Returns
    -------
    DataFrame
        Nested DataFrame matching the original Glue job output schema.
    """
    logger.info("Assembling nested struct schema (apply_mapping equivalent)")
    nested_df: DataFrame = df.select(
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
    logger.info("Nested schema assembled successfully")
    nested_df.printSchema()
    return nested_df


# FIX: Output Target — adds the Parquet write step that was absent from the
# truncated converted code.  The write receives the nested DataFrame produced
# by apply_mapping_equivalent (not the flat intermediate), ensuring the
# provider and charges structs are persisted correctly.  Addresses
# severity=CRITICAL Output Target finding.
def write_output(df: DataFrame, path: str) -> None:
    """Write the nested DataFrame to ADLS Gen2 in Parquet format.

    The DataFrame passed to this function **must** be the output of
    ``apply_mapping_equivalent`` so that the nested ``provider`` and
    ``charges`` struct columns are present in the written Parquet files.

    Parameters
    ----------
    df:
        Nested DataFrame to persist.
    path:
        ADLS Gen2 ``abfss://`` URI for the output Parquet location.
    """
    logger.info("Writing nested Parquet output to: %s", path)
    (
        df.write.mode("overwrite")
        .option("compression", "snappy")
        .parquet(path)
    )
    logger.info("Write complete: %s", path)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def main(
    input_path: Optional[str] = None,
    output_path: Optional[str] = None,
) -> None:
    """Execute the full Medicare data cleaning and restructuring pipeline.

    Pipeline steps
    --------------
    1. Read raw CSV from ADLS Gen2.
    2. Resolve ``provider id`` to ``LongType``.
    3. Drop rows with nulls in key columns.
    4. Strip leading ``$`` from currency columns (native ``regexp_replace``).
    5. Assemble nested ``provider`` / ``charges`` structs (apply_mapping
       equivalent).
    6. Write Parquet output to ADLS Gen2.

    Parameters
    ----------
    input_path:
        Override for ``INPUT_PATH`` constant (useful in unit tests).
    output_path:
        Override for ``OUTPUT_PATH`` constant (useful in unit tests).
    """
    src: str = input_path or INPUT_PATH
    dst: str = output_path or OUTPUT_PATH

    spark: SparkSession = get_spark()

    try:
        # Step 1 — ingest
        raw_df: DataFrame = read_source(spark, src)

        # Step 2 — resolve ambiguous provider id type
        resolved_df: DataFrame = resolve_provider_id(raw_df)

        # Step 3 — remove null records
        clean_df: DataFrame = filter_nulls(resolved_df, NULL_FILTER_COLUMNS)

        # Step 4 — strip currency symbols (native Spark, no Python UDF)
        stripped_df: DataFrame = apply_currency_strip(clean_df)

        # Step 5 — restructure into nested schema (apply_mapping equivalent)
        nested_df: DataFrame = apply_mapping_equivalent(stripped_df)

        # Step 6 — persist to ADLS Gen2 as Parquet
        write_output(nested_df, dst)

        logger.info("Pipeline completed successfully.")

    except Exception as exc:  # noqa: BLE001
        logger.exception("Pipeline failed with unhandled exception: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Entry point (Synapse Spark Job Definition mode)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()