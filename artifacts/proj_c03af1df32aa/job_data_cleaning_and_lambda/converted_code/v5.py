"""
Azure Synapse Spark — data_cleaning_and_lambda
Migrated from AWS Glue ETL job: data_cleaning_and_lambda.py

Performs data cleaning and transformation of Medicare payment records:
  - Reads source CSV data from ADLS Gen2
  - Resolves ambiguous provider ID types (cast to long, null-filter non-numeric)
  - Resolves provider zip code types (cast to long, warn/filter non-numeric)
  - Strips currency formatting ($) from monetary charge columns via a null-safe UDF
  - Restructures flat fields into a nested provider/charges schema
  - Writes cleaned, reshaped dataset to ADLS Gen2 in Parquet format

Original Copyright: 2016-2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.
Original License: MIT-0
"""

import logging
from typing import Optional

# ---------------------------------------------------------------------------
# mssparkutils — conditional import to support both Synapse Notebook context
# (notebookutils alias) and Synapse Spark Job Definition context (mssparkutils
# package), as well as local / unit-test environments where neither is present.
# The utility is not invoked in the current pipeline logic; the import is
# retained for future secret-retrieval or filesystem operations.
# ---------------------------------------------------------------------------
try:
    from notebookutils import mssparkutils  # Synapse Notebook pre-installed alias
except ImportError:
    try:
        import mssparkutils  # type: ignore[no-redef]  # Synapse Spark Job Definition
    except ImportError:
        mssparkutils = None  # type: ignore[assignment]  # local / unit-test context

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
# `provider id` as StringType here lets us perform a controlled cast to
# LongType ourselves, mirroring Glue's resolveChoice(cast:long) semantics.
#
# NOTE — provider zip code: intentionally declared as StringType (not LongType)
# even though the original Glue source schema typed it as long.  Reading it as
# StringType allows a controlled, observable cast to LongType in
# resolve_provider_zip_code(), where any non-numeric values are detected,
# logged at WARNING level, and handled according to the business rule
# (drop-row, analogous to the filter_null_provider_ids pattern).  If the
# column were read as LongType directly, Spark's CSV reader would silently
# coerce non-numeric values to null with no opportunity to log or count them.
SOURCE_SCHEMA: StructType = StructType(
    [
        StructField("drg definition", StringType(), nullable=True),
        StructField("provider id", StringType(), nullable=True),
        StructField("provider name", StringType(), nullable=True),
        StructField("provider city", StringType(), nullable=True),
        StructField("provider state", StringType(), nullable=True),
        # Intentionally StringType — see module-level NOTE above.
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

    The null guard mirrors the original ``lambda x: x[1:]`` behaviour exactly:
    only ``None`` is guarded against (to prevent ``TypeError``); empty strings
    are passed through unchanged so that downstream ``cast(DoubleType())``
    produces a ``null`` via Spark's normal cast-failure path rather than being
    silently converted to ``None`` here.

    .. note::
        The original lambda would raise ``TypeError`` on ``None`` input.
        Guarding only on ``None`` (not on empty string) preserves the
        original semantics for all well-formed and malformed non-None inputs.
        If empty-string data-quality detection is required in future, add an
        explicit ``logger.warning`` branch rather than silently returning
        ``None``.

    Args:
        value: Raw monetary string, expected to begin with ``$``
                (e.g. ``"$1234.56"``).

    Returns:
        The string with the leading ``$`` removed, or ``None`` if the input
        is ``None``.
    """
    if value is None:
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

    The partition count is logged only at DEBUG level to avoid unnecessary
    DAG overhead on the hot path; repartitioning is handled by the
    orchestrator (``run()``) after filtering to avoid shuffling rows that
    will be immediately discarded.

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
    # Partition count is debug-only to avoid unnecessary computation on the
    # hot path; repartitioning is applied in run() after filtering.
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "Source read complete. Inferred partition count: %d",
            df.rdd.getNumPartitions(),
        )
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

    No row-count materialisation is performed here because calling
    ``df.count()`` before and after filtering triggers two full dataset scans
    and adds significant latency on large inputs with no business logic
    benefit.  If row-count auditing is a hard requirement, cache the
    DataFrame before counting and unpersist afterwards to avoid redundant
    scans:

        df.cache()
        before: int = df.count()
        filtered_df = df.where(col("provider id").isNotNull())
        after: int = filtered_df.count()
        df.unpersist()
        logger.info("Removed %d row(s), %d remaining.", before - after, after)

    Args:
        df: ``DataFrame`` after ``resolve_provider_id``.

    Returns:
        Filtered ``DataFrame`` with no ``null`` values in ``provider id``.
    """
    logger.info(
        "NULL provider ID filter applied: rows with null provider id removed."
    )
    filtered_df: DataFrame = df.where(col("provider id").isNotNull())
    return filtered_df


def resolve_provider_zip_code(df: DataFrame) -> DataFrame:
    """Cast ``provider zip code`` from ``StringType`` to ``LongType``.

    ``provider zip code`` is intentionally read as ``StringType`` in
    ``SOURCE_SCHEMA`` (see module-level NOTE) so that this controlled cast
    can detect and surface non-numeric ZIP values before they silently become
    ``null`` in the output struct field ``provider.zip``.

    Behaviour mirrors the ``resolve_provider_id`` / ``filter_null_provider_ids``
    pattern:

    1. Cast the column to ``LongType``; non-numeric values become ``null``.
    2. Count the newly introduced nulls and emit a ``WARNING`` log so that
       data-quality issues are observable in Synapse Monitor / Log Analytics.
    3. Drop rows whose ZIP cast produced ``null`` (business rule: invalid ZIPs
       are treated as unprocessable records, consistent with the provider-ID
       filter applied earlier in the pipeline).

    If the business rule changes to *retain* rows with invalid ZIPs (e.g. to
    route them to a dead-letter path), replace the ``filter`` call with a
    conditional branch and remove the ``WARNING`` assertion below.

    Args:
        df: ``DataFrame`` after ``filter_null_provider_ids``, with
            ``provider zip code`` still typed as ``StringType``.

    Returns:
        ``DataFrame`` with ``provider zip code`` recast to ``LongType`` and
        all rows with un-castable ZIP values removed.
    """
    logger.info(
        "Resolving 'provider zip code' column: casting StringType → LongType."
    )

    # Identify rows where the cast would produce null (non-numeric ZIP strings).
    # We evaluate this BEFORE applying the cast so we can count bad rows cheaply
    # using a single filter predicate without caching the full DataFrame.
    invalid_zip_count: int = df.where(
        col("provider zip code").cast(LongType()).isNull()
        & col("provider zip code").isNotNull()  # exclude pre-existing nulls
    ).count()

    if invalid_zip_count > 0:
        logger.warning(
            "DATA QUALITY WARNING: %d row(s) contain a non-numeric 'provider zip code' "
            "value that cannot be cast to LongType. These rows will be dropped. "
            "Review upstream data for malformed ZIP codes.",
            invalid_zip_count,
        )
    else:
        logger.info(
            "All 'provider zip code' values are numeric — no rows dropped by ZIP cast."
        )

    # Apply the cast and drop rows where the result is null (covers both
    # pre-existing nulls and newly introduced cast-failure nulls).
    resolved_df: DataFrame = df.withColumn(
        "provider zip code", col("provider zip code").cast(LongType())
    )
    filtered_df: DataFrame = resolved_df.where(
        col("provider zip code").isNotNull()
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

    ``provider id`` is already ``LongType`` (cast in ``resolve_provider_id``).
    ``provider zip code`` is already ``LongType`` (cast and null-filtered in
    ``resolve_provider_zip_code``), so no further cast is required here and
    there is no risk of silent null introduction at this stage.

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

        # Nested provider struct.
        # Both `provider id` (LongType) and `provider zip code` (LongType)
        # have already been cast and null-filtered by their respective
        # resolve_* functions upstream, so no additional cast is needed here.
        struct(
            col("provider id").alias("id"),
            col("provider name").alias("name"),
            col("provider city").alias("city"),
            col("provider state").alias("state"),
            col("provider zip code").alias("zip"),
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
      4. Repartition to align with Synapse pool parallelism — performed
         **after** filtering so the shuffle operates only on rows that will
         actually be processed, avoiding wasted I/O on discarded records.
      5. Resolve ``provider zip code`` type (String → Long); log a WARNING
         if any non-numeric ZIP values are found, then drop those rows.
      6. Strip ``$`` prefix from monetary charge columns.
      7. Rename, recast, and nest fields into the target schema.
      8. Write output to ADLS Gen2 as Parquet.

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

        # Repartition is applied AFTER null-provider-id filtering so that the
        # shuffle operates only on the reduced, already-cleaned dataset.
        # Repartitioning before filtering would shuffle rows that are
        # immediately discarded, wasting I/O on large inputs with a significant
        # proportion of non-numeric provider IDs.
        target_partitions: int = spark.sparkContext.defaultParallelism
        logger.info(
            "Repartitioning filtered DataFrame to %d partition(s) "
            "(spark.sparkContext.defaultParallelism).",
            target_partitions,
        )
        filtered_df = filtered_df.repartition(target_partitions)

        # Resolve provider zip code: cast String → Long, warn on bad values,
        # and drop rows with un-castable ZIPs (mirrors provider-id pattern).
        zip_resolved_df: DataFrame = resolve_provider_zip_code(filtered_df)

        cleaned_df: DataFrame = strip_currency_symbols(zip_resolved_df)
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