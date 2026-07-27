# README.md

# Migration Documentation: `data_cleaning_and_lambda`

> **AWS Glue (PySpark) → Azure Synapse Spark**
> Migration Package Version: 1.0 | Plan Date: 2025-01-01

---

## Table of Contents

1. [Overview](#1-overview)
2. [Prerequisites](#2-prerequisites)
3. [Setup Instructions](#3-setup-instructions)
4. [Architecture Description](#4-architecture-description)
5. [Migration Summary](#5-migration-summary)
6. [Known Issues and Assumptions](#6-known-issues-and-assumptions)
7. [Deployment Guide — Azure Synapse](#7-deployment-guide--azure-synapse)
8. [Testing and Validation](#8-testing-and-validation)
9. [Support and Contacts](#9-support-and-contacts)

---

## 1. Overview

### 1.1 Job Identity

| Field | Value |
|---|---|
| **Job Name** | `data_cleaning_and_lambda` |
| **Source File** | `data_cleaning_and_lambda.py` |
| **Original Framework** | AWS Glue (PySpark) |
| **Target Framework** | Azure Synapse Spark |
| **Complexity Score** | 9.8 / 10 (HIGH) |
| **Source Line Count** | 54 |
| **Copyright** | 2016–2020 Amazon.com, Inc. or its affiliates. All Rights Reserved. |
| **License** | MIT-0 |
| **Analysis Confidence** | 0.97 |
| **Developer Approval Required** | ✅ Yes |

### 1.2 Business Purpose

This job performs **data cleaning and transformation of Medicare provider payment records**. The pipeline executes the following logical stages in order:

1. **Type Resolution** — Resolves ambiguous `StringType` values in the `provider id` field by casting to `LongType`, converting non-castable strings to `null`.
2. **Null Filtering** — Removes records where `provider id` is `null` after the cast, eliminating both genuine SQL nulls and previously non-numeric strings.
3. **Currency Stripping** — Removes dollar-sign (`$`) prefixes from three monetary charge columns using a `regexp_replace` UDF equivalent.
4. **Schema Restructuring** — Reshapes flat fields into a nested `provider` / `charges` struct schema via field mapping.
5. **Parquet Write** — Writes the cleaned, reshaped dataset to ADLS Gen2 in Parquet format for downstream analytical consumption of Medicare provider charge data.

### 1.3 Validation Status

| Category | Weight | Raw Score | Weighted Score | Status |
|---|---|---|---|---|
| Business Intent | 30% | 97 | 29.1 | ✅ PASS |
| Transformation Accuracy | 25% | 95 | 23.75 | ✅ PASS |
| Schema Fidelity | 20% | 93 | 18.6 | ✅ PASS |
| Input / Output Sources | 15% | 90–95 | ~13.9 | ✅ PASS |
| Error Handling | 10% | 88 | 8.8 | ✅ PASS |

> **Overall Result: PASS** — The converted code is semantically correct and faithfully reproduces the original pipeline's behaviour with appropriate Synapse-native equivalents.

---

## 2. Prerequisites

### 2.1 Azure Platform Requirements

| Requirement | Minimum Version / Tier | Notes |
|---|---|---|
| Azure Synapse Analytics Workspace | GA | Must be provisioned before deployment |
| Apache Spark Pool | Spark 3.2+ | Spark 3.3 recommended for full `StructType` compatibility |
| ADLS Gen2 Storage Account | Standard LRS or higher | Required for both source CSV and output Parquet |
| Azure Key Vault | Standard tier | Recommended for storing storage account keys / SAS tokens |
| Azure Active Directory | N/A | Service Principal or Managed Identity required for ADLS access |

### 2.2 Python and Library Requirements

| Library | Version | Purpose |
|---|---|---|
| `pyspark` | 3.2+ (bundled with Synapse) | Core Spark engine |
| `pyspark.sql.functions` | Bundled | `col`, `lit`, `regexp_replace`, `struct`, `when` |
| `pyspark.sql.types` | Bundled | `DoubleType`, `LongType`, `StringType`, `StructField`, `StructType` |
| `logging` | stdlib | Structured runtime logging |
| `sys` | stdlib | Exit handling |
| `typing` | stdlib | Type hints (`Optional`) |

> ℹ️ No additional `pip install` steps are required. All dependencies are available in the default Synapse Spark runtime.

### 2.3 Permissions Required

| Resource | Permission | Purpose |
|---|---|---|
| ADLS Gen2 — Source Container | `Storage Blob Data Reader` | Read source Medicare CSV files |
| ADLS Gen2 — Output Container | `Storage Blob Data Contributor` | Write Parquet output |
| Azure Key Vault | `Key Vault Secrets User` | Read connection secrets at runtime |
| Synapse Workspace | `Synapse Artifact Publisher` | Deploy notebooks or Spark job definitions |

### 2.4 Source Data Requirements

| Field | Detail |
|---|---|
| **Format** | CSV with header row |
| **Encoding** | UTF-8 |
| **Expected Columns** | `provider id`, `average covered charges`, `average total payments`, `average medicare payments`, `provider zip code`, plus additional provider descriptor fields |
| **Column `total discharges`** | Excluded from `SOURCE_SCHEMA` — must not be mapped to output |
| **Dollar-prefixed values** | Monetary columns must carry `$` prefix for stripping logic to apply correctly |

---

## 3. Setup Instructions

### 3.1 Clone or Download the Converted Code

```bash
# If stored in a Git repository
git clone <your-repository-url>
cd data_cleaning_and_lambda
```

Ensure the following file is present:

```
data_cleaning_and_lambda.py   # Converted Synapse Spark job
```

### 3.2 Configure ADLS Gen2 Paths

Open `data_cleaning_and_lambda.py` and locate the **Constants** section. Update the following parameters to match your environment:

```python
# Source path — ADLS Gen2 CSV location
SOURCE_PATH = "abfss://<container>@<storage_account>.dfs.core.windows.net/<path>/medicare_data.csv"

# Output path — ADLS Gen2 Parquet destination
OUTPUT_PATH = "abfss://<container>@<storage_account>.dfs.core.windows.net/<path>/output/"
```

> ⚠️ Replace `<container>`, `<storage_account>`, and `<path>` with your actual values before deployment.

### 3.3 Configure Spark Session Authentication

In your Synapse Spark pool configuration or notebook setup cell, add the ADLS Gen2 OAuth credentials:

```python
spark.conf.set(
    "fs.azure.account.auth.type.<storage_account>.dfs.core.windows.net",
    "OAuth"
)
spark.conf.set(
    "fs.azure.account.oauth.provider.type.<storage_account>.dfs.core.windows.net",
    "org.apache.hadoop.fs.azurebfs.oauth2.ClientCredsTokenProvider"
)
spark.conf.set(
    "fs.azure.account.oauth2.client.id.<storage_account>.dfs.core.windows.net",
    "<service-principal-client-id>"
)
spark.conf.set(
    "fs.azure.account.oauth2.client.secret.<storage_account>.dfs.core.windows.net",
    dbutils.secrets.get(scope="<key-vault-scope>", key="<secret-name>")
)
spark.conf.set(
    "fs.azure.account.oauth2.client.endpoint.<storage_account>.dfs.core.windows.net",
    "https://login.microsoftonline.com/<tenant-id>/oauth2/token"
)
```

> 🔐 **Security Note:** Never hardcode credentials in source files. Use Azure Key Vault linked services or Synapse managed identity wherever possible.

### 3.4 Upload the Script to Synapse

**Option A — Synapse Notebook:**
1. Open Azure Synapse Studio → **Develop** → **+** → **Notebook**.
2. Paste the contents of `data_cleaning_and_lambda.py` into a code cell.
3. Attach the notebook to your Spark pool.
4. Save and publish.

**Option B — Spark Job Definition:**
1. Upload `data_cleaning_and_lambda.py` to an ADLS Gen2 path or Synapse-linked storage.
2. Open Azure Synapse Studio → **Develop** → **+** → **Spark job definition**.
3. Set **Language** to `PySpark`.
4. Point **Main definition file** to the uploaded `.py` file.
5. Configure Spark pool, executor size, and node count.
6. Save and publish.

---

## 4. Architecture Description

### 4.1 Original Architecture — AWS Glue

```
┌─────────────────────────────────────────────────────────────────┐
│                        AWS Ecosystem                            │
│                                                                 │
│  ┌──────────────────┐     ┌──────────────────────────────────┐  │
│  │  AWS Glue Data   │────▶│        AWS Glue Job              │  │
│  │  Catalog         │     │  (PySpark + Glue DynamicFrame)   │  │
│  │  (Medicare CSV)  │     │                                  │  │
│  └──────────────────┘     │  1. ResolveChoice (provider id)  │  │
│                           │  2. Filter nulls                 │  │
│                           │  3. Lambda UDF (strip $)         │  │
│                           │  4. ApplyMapping (nest schema)   │  │
│                           │  5. Write Parquet → S3           │  │
│                           └──────────────┬───────────────────┘  │
│                                          │                      │
│                           ┌──────────────▼───────────────────┐  │
│                           │         Amazon S3                │  │
│                           │    (Parquet output — analytics)  │  │
│                           └──────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Target Architecture — Azure Synapse Spark

```
┌─────────────────────────────────────────────────────────────────┐
│                       Azure Ecosystem                           │
│                                                                 │
│  ┌──────────────────┐     ┌──────────────────────────────────┐  │
│  │  ADLS Gen2       │────▶│     Azure Synapse Spark Pool     │  │
│  │  (Source CSV)    │     │  (PySpark — Native Spark APIs)   │  │
│  └──────────────────┘     │                                  │  │
│                           │  1. resolve_provider_id()        │  │
│                           │     cast StringType → LongType   │  │
│                           │  2. filter_nulls()               │  │
│                           │     drop null provider id rows   │  │
│                           │  3. strip_dollar_signs()         │  │
│                           │     regexp_replace ($ removal)   │  │
│                           │  4. nest_and_cast()              │  │
│                           │     struct() field mapping       │  │
│                           │  5. write_output()               │  │
│                           │     Parquet → ADLS Gen2          │  │
│                           └──────────────┬───────────────────┘  │
│                                          │                      │
│  ┌───────────────────────────────────────▼──────────────────┐   │
│  │                    ADLS Gen2                             │   │
│  │         (Parquet output — downstream analytics)         │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐                     │
│  │  Azure Key Vault │  │  Azure Monitor / │                     │
│  │  (Secrets)       │  │  Synapse Monitor │                     │
│  └──────────────────┘  └──────────────────┘                     │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 Data Flow

```
CSV on ADLS Gen2
      │
      ▼
 spark.read.csv()          ← replaces GlueContext.create_dynamic_frame_from_catalog()
      │
      ▼
 resolve_provider_id()     ← replaces ResolveChoice(cast:long)
      │
      ▼
 filter_nulls()            ← replaces Filter.apply(isNotNull)
      │
      ▼
 strip_dollar_signs()      ← replaces Lambda UDF (x[1:] slice)
      │                       now uses regexp_replace(col, "^\\$", "")
      ▼
 nest_and_cast()           ← replaces ApplyMapping + nested DynamicFrame
      │                       now uses struct() + cast()
      ▼
 write_output()            ← replaces glueContext.write_dynamic_frame_from_options()
      │                       now uses df.write.mode("overwrite").parquet()
      ▼
Parquet on ADLS Gen2
```

---

## 5. Migration Summary

### 5.1 Key Changes at a Glance

| # | Category | Original (AWS Glue) | Migrated (Azure Synapse) | Impact |
|---|---|---|---|---|
| 1 | **Runtime** | AWS Glue PySpark (Glue 2.0/3.0) | Azure Synapse Spark 3.2+ | HIGH |
| 2 | **Data Source** | Glue Data Catalog (`create_dynamic_frame_from_catalog`) | `spark.read.csv()` from ADLS Gen2 | HIGH |
| 3 | **Data Output** | `write_dynamic_frame_from_options` → S3 Parquet | `df.write.mode("overwrite").parquet()` → ADLS Gen2 | HIGH |
| 4 | **Type Resolution** | `ResolveChoice(specs=[("provider id", "cast:long")])` | `col("provider id").cast(LongType())` via `when/otherwise` | MEDIUM |
| 5 | **Null Filtering** | `Filter.apply(frame, f=lambda x: x["provider id"] != 0)` | `df.filter(col("provider id").isNotNull())` | MEDIUM |
| 6 | **Currency Strip UDF** | Python lambda `x[1:]` (string slice) | `regexp_replace(col, "^\\$", "")` — no UDF serialisation overhead | MEDIUM |
| 7 | **Schema Nesting** | `ApplyMapping.apply()` with nested tuple specs | Native `struct()` + `cast()` column expressions | MEDIUM |
| 8 | **Call Order Fix** | `filter_nulls` called before `resolve_provider_id` | `resolve_provider_id` called **first**, then `filter_nulls` | MEDIUM |
| 9 | **Glue Context** | `GlueContext`, `Job`, `getResolvedOptions` | Removed entirely — standard `SparkSession` used | HIGH |
| 10 | **Logging** | Glue-managed logging | `logging.basicConfig` + `logging.getLogger` | LOW |
| 11 | **Error Handling** | Implicit Glue job failure | Explicit `try/except` with `sys.exit(1)` | LOW |

### 5