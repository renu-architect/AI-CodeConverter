# Glue to Synapse Mapping Reference

Comprehensive API and pattern mapping for the Implementer and Planner agents.

---

## Core Initialization

### Glue
```python
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'dt'])
job.init(args['JOB_NAME'], args)
```

### Synapse
```python
from pyspark.sql import SparkSession
from notebookutils import mssparkutils

spark = SparkSession.builder.appName("customer_etl").getOrCreate()
# Parameters from notebook cell tags or pipeline
dt = mssparkutils.notebook.getContext().parameters.get("dt")
```

---

## Reading Data

| Glue API | Synapse Equivalent | Notes |
|----------|-------------------|-------|
| `create_dynamic_frame.from_catalog(database, table)` | `spark.sql(f"SELECT * FROM {database}.{table}")` | Map Glue DB to Synapse dedicated pool table |
| `create_dynamic_frame.from_catalog(..., push_down_predicate)` | `spark.sql(f"SELECT * FROM ... WHERE {predicate}")` | Push predicate into SQL |
| `create_dynamic_frame.from_options(connection_type, connection_options)` | `spark.read.format(fmt).options(**opts).load(path)` | ADLS Gen2 instead of S3 |
| `create_dynamic_frame.from_options("s3", ...)` | `spark.read.parquet("abfss://container@account.dfs.core.windows.net/path")` | S3 → ADLS path mapping |
| `create_dynamic_frame.from_options("jdbc", ...)` | `spark.read.jdbc(url, table, properties)` | Same pattern, Azure SQL connection |
| `spark.read.parquet(path)` | `spark.read.parquet(path)` | Same if path updated to ADLS |
| `spark.read.csv(path)` | `spark.read.csv(path)` | Same |

---

## Transformations

| Glue API | Synapse Equivalent | Notes |
|----------|-------------------|-------|
| `ApplyMapping(frame, mappings)` | `df.select(*[col(src).alias(dst) for src, dst in mappings])` | Manual column mapping |
| `ResolveChoice(frame, specs)` | `df.withColumn(col, F.coalesce(col, alt))` | Case-by-case per spec |
| `DropNullFields(frame)` | `df.dropna(how='all')` or per-column `dropna(subset=[...])` | |
| `Relationalize(frame, ...)` | Manual normalization with joins | Complex — plan carefully |
| `SelectFields(frame, paths)` | `df.select(*paths)` | Direct equivalent |
| `Filter(frame, f)` | `df.filter(f)` | f is a SQL expression string |
| `Map(frame, f)` | `df.rdd.map(f)` or `df.withColumn(...)` | Prefer DataFrame API |
| `Join(frame1, frame2, paths, style)` | `df1.join(df2, paths, style)` | Verify join type preserved |
| `Union(frame1, frame2)` | `df1.union(df2)` or `df1.unionByName(df2)` | Use unionByName for schema safety |
| `Aggregate(frame, groupBy, aggs)` | `df.groupBy(groupBy).agg(*aggs)` | |
| `RenameField(frame, old, new)` | `df.withColumnRenamed(old, new)` | |
| `DropFields(frame, paths)` | `df.drop(*paths)` | |

---

## Writing Data

| Glue API | Synapse Equivalent | Notes |
|----------|-------------------|-------|
| `write_dynamic_frame.from_options(frame, "s3", ...)` | `df.write.format("parquet").mode("overwrite").save(adls_path)` | Update paths |
| `write_dynamic_frame.from_catalog(...)` | `df.write.mode("overwrite").saveAsTable(f"{db}.{table}")` | Dedicated SQL pool |
| `write_dynamic_frame.from_jdbc_conf(...)` | `df.write.jdbc(url, table, properties)` | |
| `glueContext.write_dynamic_frame.from_options(..., format="parquet")` | `df.write.parquet(path)` | |
| With partitions | `df.write.partitionBy("dt").parquet(path)` | Preserve partition columns |
| `glueContext.purge_s3_path(path)` | `mssparkutils.fs.rm(path, recurse=True)` | |

---

## Bookmarks

Glue bookmarks have no direct Synapse equivalent. Migration patterns:

### Pattern 1: Delta Lake MERGE
```python
from delta.tables import DeltaTable

if DeltaTable.isDeltaTable(spark, target_path):
    delta_table = DeltaTable.forPath(spark, target_path)
    delta_table.alias("target").merge(
        source_df.alias("source"),
        "target.id = source.id"
    ).whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()
else:
    source_df.write.format("delta").save(target_path)
```

### Pattern 2: Watermark Table
```python
# Read last processed timestamp from watermark table
last_ts = spark.sql("SELECT MAX(processed_at) FROM etl_watermarks WHERE job='customer_etl'").collect()[0][0]
new_data = spark.sql(f"SELECT * FROM source WHERE updated_at > '{last_ts}'")
# Process new_data...
# Update watermark
spark.sql(f"INSERT INTO etl_watermarks VALUES ('customer_etl', current_timestamp())")
```

### Pattern 3: Incremental Partition
```python
# Process only today's partition
dt = mssparkutils.notebook.getContext().parameters.get("dt")
df = spark.sql(f"SELECT * FROM source WHERE dt = '{dt}'")
```

---

## Job Lifecycle

| Glue | Synapse | Notes |
|------|---------|-------|
| `getResolvedOptions(sys.argv, keys)` | `mssparkutils.notebook.getContext().parameters` | Notebook parameters |
| `Job.init(name, args)` | Not needed | Synapse manages lifecycle |
| `Job.commit()` | Not needed | Synapse auto-commits |
| `Job.bookmarkOption(name, frame)` | Delta MERGE or watermark | See bookmark patterns |

---

## Utility Mapping

| Glue Utility | Synapse Equivalent |
|-------------|-------------------|
| `glueContext.extract_jdbc_conf(...)` | Build JDBC URL manually |
| `glueContext.getSource(...)` | `spark.read` with options |
| `glueContext.create_dynamic_frame.from_catalog(..., additional_options={"catalogPartitionPredicate": ...})` | SQL WHERE clause |
| `s3://bucket/path` | `abfss://container@account.dfs.core.windows.net/path` |
| `glueContext.getCatalogSource(...)` | `spark.sql(...)` against dedicated pool |
| CloudWatch logging | Synapse Spark logging / Log Analytics |
| `boto3` S3 operations | `mssparkutils.fs` operations |

---

## Library Mapping

| Remove (Glue) | Add (Synapse) |
|--------------|---------------|
| `awsglue.transforms.*` | `pyspark.sql.functions` |
| `awsglue.utils.getResolvedOptions` | `notebookutils.mssparkutils` |
| `awsglue.context.GlueContext` | `pyspark.sql.SparkSession` |
| `awsglue.dynamicframe.DynamicFrame` | `pyspark.sql.DataFrame` |
| `awsglue.job.Job` | (not needed) |
| `boto3` | `azure-storage-blob` (if needed outside Spark) |
| — | `delta-spark` (for bookmark patterns) |
| — | `com.microsoft.spark.sqlanalytics` (SQL pool writes) |

---

## Common Pitfalls

| Pitfall | Impact | Solution |
|---------|--------|----------|
| DynamicFrame → DataFrame conversion | Schema loss | Explicit schema definition |
| Bookmark removal | Duplicate/missing data | Implement Delta MERGE |
| S3 paths hardcoded | Runtime failure | Parameterize ADLS paths |
| `ApplyMapping` complex mappings | Manual effort | Generate mapping table from specs |
| Glue catalog references | Table not found | Create Synapse table mapping config |
| `ResolveChoice` ambiguity | Data quality issues | Explicit coalesce logic per field |
| UDF compatibility | Different serialization | Test UDFs in Synapse environment |
| `push_down_predicate` | Performance regression | Use SQL WHERE in Synapse |
| Worker configuration | Different sizing | Synapse pool sizing guide |
| `additional_options` in catalog reads | Feature loss | Map to spark.read options |

---

## Path Mapping Configuration

```yaml
# config/path_mapping.yaml
s3_to_adls:
  "s3://my-bucket/data/": "abfss://data@myaccount.dfs.core.windows.net/"
  "s3://my-bucket/staging/": "abfss://staging@myaccount.dfs.core.windows.net/"

catalog_mapping:
  "analytics.customers": "dbo.customers"
  "analytics.orders": "dbo.orders"
```

Used by Implementer agent via `{{path_mapping}}` variable.
