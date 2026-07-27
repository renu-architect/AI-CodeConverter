"""
Azure Synapse Spark — data_cleaning_and_lambda
Migrated from AWS Glue ETL job: data_cleaning_and_lambda.py

Performs data cleaning and transformation of Medicare payment records:
  - Reads source CSV data from ADLS Gen2
  - Resolves ambiguous provider ID types (cast to long, null-filter non-numeric)
  - Strips currency formatting ($) from monetary charge columns via a null-safe UDF
  - Restructures flat fields into a nested provider/charges schema
  - Writes cleaned, reshaped dataset to ADLS Gen2 in Parquet format

Original Copyright: 2016-2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.
Original License: MIT-0
"""

import logging
from typing import Optional

from notebookutils import mssparkutils  # noqa: F401  # pre-installed in Synapse Spark pools
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import col, struct, udf, when
from pyspark.sql.types import DoubleType, LongType, StringType, StructField, StructType

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger: logging.Logger = logging.getLogger("data_cleaning_and_lambda")

# ---------------------------------------------------------------------------
# Configuration — replace placeholder values with your storage account name
# and container names, or inject via Synapse pipeline parameters / notebook
# widgets.  No credentials are stored here; access is granted through the
# Synapse workspace Managed Identity (Storage Blob Data Contributor role).
# ---------------------------------------------------------------------------
SOURCE_PATH: str = (
    "abfss://source@<storage_account>.dfs.core.windows.net/medicare/"
)
OUTPUT_PATH: str = (
    "abfss://target@<storage_account>.dfs.core.windows.net/output-dir/medicare_parquet"
)

# Explicit source schema avoids the type-inference ambiguity that caused the
# `provider id` choice-type problem in the original Glue job.  Declaring
# `provider_id` as StringType here lets us perform a controlled cast to
# LongType ourselves, mirroring Glue's resolveChoice(cast:long) semantics.
SOURCE_SCHEMA: StructType = StructType(
    [
        StructField("drg definition", StringType(), nullable=True),
        StructField("provider id", StringType(), nullable=True),
        StructField("provider name", StringType(), nullable=True),
        StructField("provider city", StringType(), nullable=True),
        StructField("provider state", StringType(), nullable=True),
        StructField("provider zip code", StringType(), nullable=True),
        StructField("hospital referral region description", StringType(), nullable=True),
        StructField("average covered charges", StringType(), nullable=True),
        StructField("average total payments", StringType(), nullable=True),
        StructField("average medicare payments", StringType(), nullable=True),
    ]
)


# ---------------------------------------------------------------------------
# UDF
# ---------------------------------------------------------------------------
def _strip_leading_char(value: Optional[str]) -> Optional[str]:
    """Return *value* with its first character removed.

    Returns ``None`` when *value* is ``None`` or an empty string so that
    downstream ``cast(DoubleType())`` produces a clean ``null`` rather than
    raising a runtime exception.

    This replaces the original ``lambda x: x[1:]`` which had no null guard
    and would raise ``TypeError`` on ``None`` or produce an empty string on
    single-character input.

    Args:
        value: Raw monetary string, expected to begin with ``$``
                (e.g. ``"$1234.56"``).

    Returns:
        The string with the leading ``$`` removed, or ``None`` if the input
        is ``None`` / empty.
    """
    if value is None or len(value) == 0:
        return None
    return value[1:]


# Register as a Spark UDF with an explicit return type.
strip_leading_char_udf = udf(_strip_leading_char, StringType())


# ---------------------------------------------------------------------------
# Pipeline steps — each step is a pure function that accepts and returns a
# DataFrame, making the logic independently testable.
# ---------------------------------------------------------------------------
def read_source(spark: SparkSession, path: str) -> DataFrame:
    """Read the Medicare CSV source from ADLS Gen2.

    Uses the explicit ``SOURCE_SCHEMA`` to avoid type-inference ambiguity.
    ``header=True`` is required because the source files include a header row.

    Args:
        spark: Active ``SparkSession``.
        path:  ``abfss://`` URI pointing to the source CSV directory or file.

    Returns:
        Raw ``DataFrame`` with all columns as ``StringType``.

    Raises:
        Exception: Propagates any Spark read-time I/O or schema errors.
    """
    logger.info("Reading source data from: %s", path)
    df: DataFrame = (
        spark.read.format("csv")
        .option("header", "true")
        .option("multiLine", "false")
        .schema(SOURCE_SCHEMA)
        .load(path)
    )
    logger.info("Source read complete. Inferred partition count: %d", df.rdd.getNumPartitions())
    return df


def resolve_provider_id(df: DataFrame) -> DataFrame:
    """Cast ``provider id`` from ``StringType`` to ``LongType``.

    Mirrors Glue ``resolveChoice(specs=[('provider id', 'cast:long')])``:
    values that cannot be cast to ``long`` (non-numeric strings) become
    ``null``.  The subsequent ``filter_null_provider_ids`` step removes those
    rows, replicating the original two-step clean-up.

    Args:
        df: Input ``DataFrame`` with ``provider id`` as ``StringType``.

    Returns:
        ``DataFrame`` with ``provider id`` recast to ``LongType``.
    """
    logger.info("Resolving 'provider id' column: casting StringType → LongType.")
    return df.withColumn("provider id", col("provider id").cast(LongType()))


def filter_null_provider_ids(df: DataFrame) -> DataFrame:
    """Remove rows where ``provider id`` is ``null``.

    These nulls originate from the ``cast:long`` resolution step — they
    represent records whose ``provider id`` was a non-numeric string and
    therefore could not be cast.

    Args:
        df: ``DataFrame`` after ``resolve_provider_id``.

    Returns:
        Filtered ``DataFrame`` with no ``null`` values in ``provider id``.
    """
    before: int = df.count()
    filtered_df: DataFrame = df.where(col("provider id").isNotNull())
    after: int = filtered_df.count()
    logger.info(
        "NULL provider ID filter: removed %d row(s), %d row(s) remaining.",
        before - after,
        after,
    )
    return filtered_df


def strip_currency_symbols(df: DataFrame) -> DataFrame:
    """Strip the leading ``$`` from the three monetary charge columns.

    Applies the null-safe ``strip_leading_char_udf`` to:
      - ``average covered charges``  → intermediate column ``ACC``
      - ``average total payments``   → intermediate column ``ATP``
      - ``average medicare payments`` → intermediate column ``AMP``

    The intermediate column names (``ACC``, ``ATP``, ``AMP``) are retained
    to match the original job's naming convention and are consumed by the
    subsequent ``build_nested_schema`` step.

    Args:
        df: Filtered ``DataFrame`` with raw ``$``-prefixed monetary strings.

    Returns:
        ``DataFrame`` with three additional ``StringType`` columns:
        ``ACC``, ``ATP``, ``AMP``.
    """
    logger.info("Stripping currency symbols from monetary charge columns.")
    return (
        df.withColumn("ACC", strip_leading_char_udf(col("average covered charges")))
        .withColumn("ATP", strip_leading_char_udf(col("average total payments")))
        .withColumn("AMP", strip_leading_char_udf(col("average medicare payments")))
    )


def build_nested_schema(df: DataFrame) -> DataFrame:
    """Rename, recast, and nest fields to produce the target output schema.

    Replaces Glue ``DynamicFrame.apply_mapping`` with native PySpark
    ``select`` + ``struct``.  The mapping is:

    +-----------------------------------------+---------------------+-----------+
    | Source column                           | Target path         | Cast      |
    +=========================================+=====================+===========+
    | drg definition                          | drg                 | string    |
    | provider id                             | provider.id         | long      |
    | provider name                           | provider.name       | string    |
    | provider city                           | provider.city       | string    |
    | provider state                          | provider.state      | string    |
    | provider zip code                       | provider.zip        | long      |
    | hospital referral region description    | rr                  | string    |
    | ACC                                     | charges.covered     | double    |
    | ATP                                     | charges.total_pay   | double    |
    | AMP                                     | charges.medicare_pay| double    |
    +-----------------------------------------+---------------------+-----------+

    Args:
        df: ``DataFrame`` produced by ``strip_currency_symbols``.

    Returns:
        ``DataFrame`` with top-level columns ``drg``, ``provider``
        (struct), ``rr``, and ``charges`` (struct).
    """
    logger.info("Building nested output schema via struct() expressions.")
    return df.select(
        # Flat renamed column
        col("drg definition").alias("drg"),

        # Nested provider struct — provider zip code cast to LongType to
        # match the original apply_mapping target type declaration.
        struct(
            col("provider id").cast(LongType()).alias("id"),
            col("provider name").alias("name"),
            col("provider city").alias("city"),
            col("provider state").alias("state"),
            col("provider zip code").cast(LongType()).alias("zip"),
        ).alias("provider"),

        # Flat renamed column
        col("hospital referral region description").alias("rr"),

        # Nested charges struct — cast stripped strings to DoubleType.
        # A null-safe cast is used: non-numeric strings become null rather
        # than raising a runtime exception.
        struct(
            col("ACC").cast(DoubleType()).alias("covered"),
            col("ATP").cast(DoubleType()).alias("total_pay"),
            col("AMP").cast(DoubleType()).alias("medicare_pay"),
        ).alias("charges"),
    )


def write_parquet(df: DataFrame, path: str) -> None:
    """Write the final ``DataFrame`` to ADLS Gen2 in Parquet format.

    Uses ``overwrite`` mode to match the original job's unconditional write
    behaviour (no bookmarks / incremental logic was present in the source).

    Args:
        df:   Final nested ``DataFrame`` ready for output.
        path: ``abfss://`` URI for the Parquet output directory.

    Raises:
        Exception: Propagates any Spark write-time I/O errors.
    """
    logger.info("Writing Parquet output to: %s", path)
    df.write.mode("overwrite").parquet(path)
    logger.info("Parquet write complete.")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run(spark: SparkSession) -> None:
    """Execute the full Medicare data cleaning and transformation pipeline.

    Orchestrates all pipeline steps in sequence:
      1. Read source CSV from ADLS Gen2.
      2. Resolve ``provider id`` type (String → Long, non-numeric → null).
      3. Filter rows with null ``provider id``.
      4. Strip ``$`` prefix from monetary charge columns.
      5. Rename, recast, and nest fields into the target schema.
      6. Write output to ADLS Gen2 as Parquet.

    Args:
        spark: Active ``SparkSession`` (pre-initialised in Synapse notebooks).

    Raises:
        ValueError: If the source path or output path configuration is empty.
        Exception:  Propagates unexpected Spark runtime errors after logging.
    """
    if not SOURCE_PATH or "<storage_account>" in SOURCE_PATH:
        raise ValueError(
            "SOURCE_PATH contains a placeholder value. "
            "Replace '<storage_account>' with your ADLS Gen2 storage account name."
        )
    if not OUTPUT_PATH or "<storage_account>" in OUTPUT_PATH:
        raise ValueError(
            "OUTPUT_PATH contains a placeholder value. "
            "Replace '<storage_account>' with your ADLS Gen2 storage account name."
        )

    logger.info("Pipeline start: data_cleaning_and_lambda")

    try:
        raw_df: DataFrame = read_source(spark, SOURCE_PATH)
        resolved_df: DataFrame = resolve_provider_id(raw_df)
        filtered_df: DataFrame = filter_null_provider_ids(resolved_df)
        cleaned_df: DataFrame = strip_currency_symbols(filtered_df)
        nested_df: DataFrame = build_nested_schema(cleaned_df)
        write_parquet(nested_df, OUTPUT_PATH)
    except ValueError as exc:
        logger.error("Configuration error: %s", exc)
        raise
    except Exception as exc:
        logger.error("Unexpected pipeline failure: %s", exc, exc_info=True)
        raise

    logger.info("Pipeline complete: data_cleaning_and_lambda")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
# In a Synapse Notebook, `spark` is pre-initialised — call run(spark) directly
# in the final notebook cell.
#
# In a Synapse Spark Job Definition (.py), the block below is the entry point.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    _spark: SparkSession = SparkSession.builder.getOrCreate()
    run(_spark)