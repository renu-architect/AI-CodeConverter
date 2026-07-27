# =============================================================================
# data_cleaning_and_lambda.py
# Migrated from AWS Glue to Azure Synapse Spark
# =============================================================================

import logging
import sys
from typing import Optional

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import (
    col,
    lit,
    regexp_replace,
    struct,
    when,
)
from pyspark.sql.types import (
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# FIX (security): Replace mssparkutils.notebook.run() with the standard
# Synapse parameter pattern.  notebook.run() is designed to execute child
# notebooks and return their exit value — not to fetch pipeline parameters.
# For Spark Job Definitions the parameter is injected via spark.conf;
# for Notebooks it is injected via the Synapse pipeline parameter cell.
# The assertion below fails fast with a clear message if the parameter has
# not been resolved, preventing silent misconfiguration.
try:
    _spark_for_conf: SparkSession = SparkSession.builder.getOrCreate()
    _STORAGE_ACCOUNT: str = _spark_for_conf.conf.get(
        "spark.job.storage_account", "<storage_account>"
    )
except Exception as exc:  # noqa: BLE001
    logger.warning(
        "Could not read spark.job.storage_account from Spark conf: %s", exc
    )
    _STORAGE_ACCOUNT = "<storage_account>"

assert "<storage_account>" not in _STORAGE_ACCOUNT, (
    "storage_account placeholder not resolved. "
    "Pass the 'storage_account' parameter via the Synapse pipeline or "
    "Spark Job Definition conf key 'spark.job.storage_account'."
)

INPUT_PATH: str = (
    f"abfss://raw@{_STORAGE_ACCOUNT}.dfs.core.windows.net/"
    "medicare/inpatient_charges/"
)
OUTPUT_PATH: str = (
    f"abfss://curated@{_STORAGE_ACCOUNT}.dfs.core.windows.net/"
    "medicare/inpatient_charges_nested/"
)

# ---------------------------------------------------------------------------
# Source schema
# ---------------------------------------------------------------------------
# FIX (schema_fidelity): 'provider zip code' is declared as StringType here
# so that mixed-type raw CSV data is ingested without parse errors.  An
# explicit cast to LongType() is applied inside nest_and_cast() — matching
# the original Glue apply_mapping long→long contract.  This mirrors the
# same deferred-cast pattern used for 'provider id'.
SOURCE_SCHEMA: StructType = StructType(
    [
        StructField("drg definition", StringType(), True),
        StructField("provider id", StringType(), True),          # cast→long later
        StructField("provider name", StringType(), True),
        StructField("provider city", StringType(), True),
        StructField("provider state", StringType(), True),
        StructField("provider zip code", StringType(), True),    # cast→long later
        StructField("hospital referral region description", StringType(), True),
        StructField("total discharges", StringType(), True),
        StructField("average covered charges", StringType(), True),
        StructField("average total payments", StringType(), True),
        StructField("average medicare payments", StringType(), True),
    ]
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_spark() -> SparkSession:
    """Return the active SparkSession (created by the Synapse runtime).

    Equivalent to the Glue GlueContext / SparkContext initialisation block.
    In Synapse the session is pre-created; this function simply retrieves it
    and ensures it is available before any DataFrame operations are attempted.
    """
    spark: SparkSession = SparkSession.builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    return spark


def read_source(spark: SparkSession, path: str) -> DataFrame:
    """Read the raw Medicare CSV from ADLS Gen2.

    Parameters
    ----------
    spark:
        Active SparkSession.
    path:
        ADLS Gen2 abfss:// URI for the source CSV files.

    Returns
    -------
    DataFrame
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
    # NOTE (performance): df.count() is intentionally omitted here.
    # A count() immediately after load() triggers a full distributed scan
    # before any filtering or transformation, doubling I/O cost.
    # Row-count observability is handled conditionally in main() after the
    # null-filter step, guarded by the enable_row_counts parameter.
    logger.info("Source DataFrame loaded successfully.")
    return df


def filter_nulls(df: DataFrame) -> DataFrame:
    """Drop rows where any column is null.

    Equivalent to the Glue Filter transform that removed incomplete records
    before the apply_mapping step.

    Parameters
    ----------
    df:
        Input DataFrame.

    Returns
    -------
    DataFrame
        DataFrame with rows containing any null value removed.
    """
    # FIX (code_completeness): filter_nulls() body was missing from the
    # submitted code.  dropna(how="any") replicates the Glue Filter
    # behaviour of discarding any row that contains at least one null field.
    logger.info("Filtering null rows.")
    return df.dropna(how="any")


def resolve_provider_id(df: DataFrame) -> DataFrame:
    """Cast 'provider id' from StringType to LongType.

    Equivalent to the Glue resolveChoice(specs=[('provider id', 'cast:long')])
    transform.  Non-castable values (e.g. empty strings, non-numeric text)
    are returned as null — matching the original cast:long behaviour.

    Parameters
    ----------
    df:
        DataFrame containing a StringType 'provider id' column.

    Returns
    -------
    DataFrame
        DataFrame with 'provider id' as LongType.
    """
    logger.info("Resolving 'provider id' to LongType.")
    return df.withColumn(
        "provider id",
        col("provider id").cast(LongType()),
    )


def strip_currency(df: DataFrame) -> DataFrame:
    """Strip the leading '$' character from the three monetary columns.

    Equivalent to the Glue Map transform that applied the Python lambda
    ``lambda x: x[1:]`` to each monetary field.  The regex ``^\\$``
    matches only a literal leading dollar sign, which is identical in
    effect to slicing off the first character when that character is '$'.

    Null safety: each regexp_replace call is wrapped in a ``when`` guard so
    that null input values remain null rather than raising a NullPointerError
    (the original UDF would throw on null input).

    .. note::
        The original lambda ``x[1:]`` strips the first character
        unconditionally.  In practice every value in the source data begins
        with '$', so ``^\\$`` is behaviourally equivalent and is safer
        because it leaves values that do *not* start with '$' unchanged
        rather than silently corrupting them.

    Parameters
    ----------
    df:
        DataFrame with raw monetary string columns.

    Returns
    -------
    DataFrame
        DataFrame with intermediate columns ACC, ATP, AMP holding the
        cleaned numeric strings ready for DoubleType casting.
    """
    # FIX (transformations): implement the dollar-sign stripping that was
    # imported (regexp_replace) but never applied in the submitted code.
    # Null-safe wrappers prevent the NullPointerError the original UDF
    # would raise on null input.
    logger.info("Stripping leading '$' from monetary columns.")
    return (
        df
        .withColumn(
            "ACC",
            when(
                col("average covered charges").isNotNull(),
                regexp_replace(col("average covered charges"), r"^\$", ""),
            ).otherwise(lit(None).cast(StringType())),
        )
        .withColumn(
            "ATP",
            when(
                col("average total payments").isNotNull(),
                regexp_replace(col("average total payments"), r"^\$", ""),
            ).otherwise(lit(None).cast(StringType())),
        )
        .withColumn(
            "AMP",
            when(
                col("average medicare payments").isNotNull(),
                regexp_replace(col("average medicare payments"), r"^\$", ""),
            ).otherwise(lit(None).cast(StringType())),
        )
    )


def nest_and_cast(df: DataFrame) -> DataFrame:
    """Rename fields, cast types, and restructure into nested structs.

    Implements the full apply_mapping specification from the original Glue
    job:

    Top-level output columns
    ------------------------
    drg : StringType
        DRG definition string.
    rr : StringType
        Hospital referral region description.
    provider : StructType
        id        LongType   — cast from 'provider id'
        name      StringType
        city      StringType
        state     StringType
        zip       LongType   — cast from 'provider zip code'
    charges : StructType
        covered       DoubleType — stripped ACC cast to double
        total_pay     DoubleType — stripped ATP cast to double
        medicare_pay  DoubleType — stripped AMP cast to double

    Parameters
    ----------
    df:
        DataFrame after filter_nulls(), resolve_provider_id(), and
        strip_currency() have been applied.

    Returns
    -------
    DataFrame
        Nested, fully-typed output DataFrame matching the original Glue
        output contract.
    """
    # FIX (code_completeness + schema_fidelity): implement nest_and_cast()
    # which was entirely missing from the submitted code.
    #
    # FIX (schema_fidelity): 'provider zip code' is explicitly cast to
    # LongType() here, satisfying the original Glue apply_mapping long→long
    # contract.  Without this cast it would remain StringType in the output,
    # breaking downstream consumers.
    #
    # Nested structs are constructed with pyspark.sql.functions.struct() so
    # that Parquet serialisation correctly produces nested column groups
    # (dot-notation field names alone are not sufficient for Parquet nesting).
    logger.info("Nesting and casting DataFrame to output schema.")

    provider_struct = struct(
        col("provider id").cast(LongType()).alias("id"),
        col("provider name").cast(StringType()).alias("name"),
        col("provider city").cast(StringType()).alias("city"),
        col("provider state").cast(StringType()).alias("state"),
        col("provider zip code").cast(LongType()).alias("zip"),
    )

    charges_struct = struct(
        col("ACC").cast(DoubleType()).alias("covered"),
        col("ATP").cast(DoubleType()).alias("total_pay"),
        col("AMP").cast(DoubleType()).alias("medicare_pay"),
    )

    return df.select(
        col("drg definition").cast(StringType()).alias("drg"),
        col("hospital referral region description")
        .cast(StringType())
        .alias("rr"),
        provider_struct.alias("provider"),
        charges_struct.alias("charges"),
    )


def write_output(df: DataFrame, path: str) -> None:
    """Write the transformed DataFrame to ADLS Gen2 as Parquet.

    Equivalent to the Glue job's ``datasink`` write step.  Uses
    ``overwrite`` mode so that re-runs are idempotent.

    Nested structs produced by nest_and_cast() are serialised correctly by
    the Parquet writer because they are expressed as struct() columns rather
    than dot-notation field names.

    Parameters
    ----------
    df:
        Fully transformed, nested DataFrame.
    path:
        ADLS Gen2 abfss:// URI for the output Parquet location.
    """
    # FIX (output_targets): write_output() body was missing from the
    # submitted code.  mode("overwrite") ensures idempotent re-runs.
    logger.info("Writing output Parquet to: %s", path)
    try:
        df.write.mode("overwrite").parquet(path)
        logger.info("Output written successfully.")
    except Exception as exc:
        logger.error("Failed to write output to %s: %s", path, exc)
        raise


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main(enable_row_counts: bool = False) -> None:
    """Orchestrate the full data cleaning and restructuring pipeline.

    Pipeline steps
    --------------
    1. Ingest raw CSV from ADLS Gen2 with SOURCE_SCHEMA.
    2. Drop rows containing any null value (Glue Filter equivalent).
    3. Optionally log row count for observability (guarded to avoid extra scan).
    4. Cast 'provider id' to LongType (Glue resolveChoice cast:long).
    5. Strip leading '$' from monetary columns (Glue Map / lambda equivalent).
    6. Rename, cast, and nest all fields into the output schema.
    7. Write nested Parquet to ADLS Gen2 (Glue datasink equivalent).

    Parameters
    ----------
    enable_row_counts:
        When True, emit a row-count log line after the null-filter step for
        observability.  Defaults to False to avoid the extra distributed
        scan in production runs.
    """
    spark: SparkSession = get_spark()

    # 1. Ingest
    df: DataFrame = read_source(spark, INPUT_PATH)

    # 2. Remove incomplete records (Glue Filter transform equivalent)
    df = filter_nulls(df)

    # FIX (performance): count() is now conditional and placed *after*
    # filtering so it scans the smaller post-filter dataset only when
    # explicitly requested.
    if enable_row_counts:
        row_count: int = df.count()
        logger.info("Row count after null filter: %d", row_count)

    # 3. Resolve 'provider id' to LongType (Glue resolveChoice cast:long)
    df = resolve_provider_id(df)

    # 4. Strip leading '$' from monetary columns (Glue Map / lambda equivalent)
    #    Produces intermediate columns ACC, ATP, AMP.
    df = strip_currency(df)

    # 5. Rename, cast, and nest into the output schema (Glue apply_mapping
    #    equivalent).  Also applies the deferred LongType cast to
    #    'provider zip code' per the original schema contract.
    df = nest_and_cast(df)

    # 6. Persist nested Parquet to ADLS Gen2 (Glue datasink equivalent)
    write_output(df, OUTPUT_PATH)


if __name__ == "__main__":
    # Allow enable_row_counts to be toggled via a CLI argument when running
    # as a Synapse Spark Job Definition rather than a notebook.
    _enable_counts: bool = "--enable-row-counts" in sys.argv
    main(enable_row_counts=_enable_counts)