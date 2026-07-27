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
# FIX (security): Replace literal placeholder with runtime parameter
# resolution.  The notebook/pipeline must pass 'storage_account' as a
# parameter; the assertion below fails fast with a clear message if it has
# not been substituted.
try:
    from notebookutils import mssparkutils  # Synapse runtime import

    _STORAGE_ACCOUNT: str = mssparkutils.notebook.run(
        "get_param", timeout_seconds=30, arguments={"param": "storage_account"}
    )
except Exception:
    # Fallback: read from Spark conf (set via Synapse pipeline parameter)
    _STORAGE_ACCOUNT = (
        SparkSession.builder.getOrCreate()
        .conf.get("spark.job.storage_account", "<storage_account>")
    )

assert "<storage_account>" not in _STORAGE_ACCOUNT, (
    "storage_account placeholder not resolved. "
    "Pass the 'storage_account' parameter via the Synapse pipeline or notebook."
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
# 'provider id' is kept as StringType here to tolerate mixed-type raw data;
# the LongType cast is applied explicitly in resolve_provider_id() —
# matching the original Glue resolveChoice cast:long behaviour.
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
    spark = SparkSession.builder.getOrCreate()
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
    # FIX (performance): df.count() removed from here.
    # A count() immediately after load() triggers a full distributed scan
    # before any filtering or transformation, doubling I/O cost.
    # Row-count observability is handled conditionally in main() after the
    # null-filter step, guarded by the enable_row_counts job parameter.
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
        DataFrame with fully-null rows removed.
    """
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
    # FIX (transformations): cast to LongType, not StringType.
    # The original Glue job uses cast:long; casting to StringType broke the
    # downstream provider.id: long output contract in nest_and_cast().
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
    logger.info("Stripping leading '$' from monetary columns.")
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
    # FIX (code_completeness + schema_mapping): implement nest_and_cast()
    # which was entirely missing from the submitted code.
    #
    # Steps:
    #   1. Strip '$' from monetary columns (via strip_currency, already done
    #      upstream, but we reference ACC/ATP/AMP here).
    #   2. Rename and cast all 10 fields per the apply_mapping spec.
    #   3. Construct provider struct with id(long), name, city, state,
    #      zip(long).
    #   4. Construct charges struct with covered(double), total_pay(double),
    #      medicare_pay(double).
    #   5. Output drg(string) and rr(string) at top level.
    #
    # FIX (schema_mapping): provider.zip is explicitly cast to LongType here,
    # satisfying the original schema contract.  Without this cast it would
    # remain StringType in the output.

    logger.info("Nesting and casting DataFrame to output schema.")

    provider_struct = struct(
        col("provider id").cast(LongType()).alias("id"),
        col("provider name").alias("name"),
        col("provider city").alias("city"),
        col("provider state").alias("state"),
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

    Parameters
    ----------
    df:
        Fully transformed, nested DataFrame.
    path:
        ADLS Gen2 abfss:// URI for the output Parquet location.
    """
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

    Parameters
    ----------
    enable_row_counts:
        When True, emit row-count log lines after the null-filter step for
        observability.  Defaults to False to avoid the extra distributed
        scan in production runs.
    """
    spark: SparkSession = get_spark()

    # 1. Ingest
    df: DataFrame = read_source(spark, INPUT_PATH)

    # 2. Remove incomplete records
    df = filter_nulls(df)

    # FIX (performance): count() is now conditional and placed *after*
    # filtering so it scans the smaller post-filter dataset only when
    # explicitly requested.
    if enable_row_counts:
        row_count: int = df.count()
        logger.info("Row count after null filter: %d", row_count)

    # 3. Resolve provider id to LongType (Glue resolveChoice cast:long)
    df = resolve_provider_id(df)

    # 4. Strip leading '$' from monetary columns
    df = strip_currency(df)

    # 5. Rename, cast, and nest into output schema
    df = nest_and_cast(df)

    # 6. Persist
    write_output(df, OUTPUT_PATH)


if __name__ == "__main__":
    # Allow enable_row_counts to be toggled via a CLI argument when running
    # as a Synapse Spark Job Definition rather than a notebook.
    _enable_counts: bool = "--enable-row-counts" in sys.argv
    main(enable_row_counts=_enable_counts)