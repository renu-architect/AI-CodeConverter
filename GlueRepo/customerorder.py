import sys
import logging

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from awsglue.dynamicframe import DynamicFrame

from pyspark.context import SparkContext

from pyspark.sql.functions import (
    col,
    when,
    sum,
    avg,
    row_number,
    current_timestamp,
    year,
    month,
    lit
)

from pyspark.sql.window import Window


# -----------------------------------------------------
# Job Initialization
# -----------------------------------------------------

args = getResolvedOptions(sys.argv, ["JOB_NAME"])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session

job = Job(glueContext)
job.init(args["JOB_NAME"], args)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

logger.info("Starting Customer Sales ETL")


# -----------------------------------------------------
# Read Customers CSV
# -----------------------------------------------------

customers = spark.read \
    .option("header", True) \
    .option("inferSchema", True) \
    .csv("s3://company-data/raw/customers/")


# -----------------------------------------------------
# Read Orders
# -----------------------------------------------------

orders = spark.read.parquet(
    "s3://company-data/raw/orders/"
)


# -----------------------------------------------------
# Read Exchange Rates JSON
# -----------------------------------------------------

exchange = spark.read.json(
    "s3://company-data/raw/exchange_rates/"
)


# -----------------------------------------------------
# Read Product Master from Glue Catalog
# -----------------------------------------------------

product_dynamic = glueContext.create_dynamic_frame.from_catalog(
    database="retail",
    table_name="products",
    transformation_ctx="products"
)

products = product_dynamic.toDF()


# -----------------------------------------------------
# Data Cleansing
# -----------------------------------------------------

customers = customers.dropDuplicates(["customer_id"])

customers = customers.fillna({
    "country":"Unknown",
    "status":"Inactive"
})

orders = orders.filter(col("amount") > 0)

orders = orders.fillna({
    "currency":"USD"
})


# -----------------------------------------------------
# Filter Active Customers
# -----------------------------------------------------

customers = customers.filter(
    col("status") == "Active"
)


# -----------------------------------------------------
# Join Customer + Orders
# -----------------------------------------------------

sales = orders.join(
    customers,
    "customer_id",
    "inner"
)


# -----------------------------------------------------
# Join Product
# -----------------------------------------------------

sales = sales.join(
    products,
    "product_id",
    "left"
)


# -----------------------------------------------------
# Currency Conversion
# -----------------------------------------------------

sales = sales.join(
    exchange,
    "currency",
    "left"
)

sales = sales.withColumn(
    "amount_usd",
    col("amount") * col("rate")
)


# -----------------------------------------------------
# Calculate Discount
# -----------------------------------------------------

sales = sales.withColumn(
    "discount",
    when(col("amount_usd") > 1000, 0.10)
    .when(col("amount_usd") > 500, 0.05)
    .otherwise(0)
)

sales = sales.withColumn(
    "net_amount",
    col("amount_usd") * (1 - col("discount"))
)


# -----------------------------------------------------
# Window Function
# -----------------------------------------------------

windowSpec = Window.partitionBy(
    "customer_id"
).orderBy(
    col("order_date").desc()
)

sales = sales.withColumn(
    "latest_order",
    row_number().over(windowSpec)
)

latest_orders = sales.filter(
    col("latest_order") == 1
)


# -----------------------------------------------------
# Aggregate Sales
# -----------------------------------------------------

summary = sales.groupBy(
    "country",
    "category"
).agg(
    sum("net_amount").alias("total_sales"),
    avg("net_amount").alias("avg_sales")
)


# -----------------------------------------------------
# Audit Columns
# -----------------------------------------------------

summary = summary.withColumn(
    "processed_timestamp",
    current_timestamp()
)

summary = summary.withColumn(
    "job_name",
    lit(args["JOB_NAME"])
)


# -----------------------------------------------------
# Partition Columns
# -----------------------------------------------------

summary = summary.withColumn(
    "year",
    year(current_timestamp())
)

summary = summary.withColumn(
    "month",
    month(current_timestamp())
)


# -----------------------------------------------------
# Convert to DynamicFrame
# -----------------------------------------------------

summary_dynamic = DynamicFrame.fromDF(
    summary,
    glueContext,
    "summary_dynamic"
)


# -----------------------------------------------------
# Write Output
# -----------------------------------------------------

glueContext.write_dynamic_frame.from_options(
    frame=summary_dynamic,
    connection_type="s3",
    connection_options={
        "path":"s3://company-data/curated/customer_sales/",
        "partitionKeys":["year","month"]
    },
    format="parquet"
)


# -----------------------------------------------------
# Metrics
# -----------------------------------------------------

logger.info(f"Customers : {customers.count()}")
logger.info(f"Orders    : {orders.count()}")
logger.info(f"Output    : {summary.count()}")


# -----------------------------------------------------
# Commit
# -----------------------------------------------------

job.commit()

logger.info("Customer Sales ETL Completed")