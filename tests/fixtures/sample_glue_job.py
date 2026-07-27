"""Sample AWS Glue ETL job for testing."""

import sys
from awsglue.transforms import ApplyMapping, ResolveChoice
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.dynamicframe import DynamicFrame
from pyspark.sql.functions import col

args = getResolvedOptions(sys.argv, ["JOB_NAME", "dt", "database"])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

database = args["database"]
dt = args["dt"]


def main():
    """Main ETL entry point."""
    try:
        dyf_customers = glueContext.create_dynamic_frame.from_catalog(
            database=database,
            table_name="customers",
            transformation_ctx="dyf_customers",
        )
    except Exception as e:
        print(f"Error reading customers: {e}")
        raise

    mapped = ApplyMapping.apply(
        frame=dyf_customers,
        mappings=[
            ("id", "int", "customer_id", "int"),
            ("name", "string", "customer_name", "string"),
            ("amount", "double", "total_amount", "decimal"),
        ],
    )

    resolved = ResolveChoice.apply(frame=mapped, choice="make_cols")

    dyf_orders = glueContext.create_dynamic_frame.from_catalog(
        database=database,
        table_name="orders",
    )

    orders_df = dyf_orders.toDF()
    customers_df = resolved.toDF()

    enriched = customers_df.join(orders_df, "customer_id", "left")
    filtered = enriched.filter(col("dt") == dt)

    output_dyf = DynamicFrame.fromDF(filtered, glueContext, "output")
    glueContext.write_dynamic_frame.from_options(
        frame=output_dyf,
        connection_type="s3",
        connection_options={"path": f"s3://bucket/enriched/customers/dt={dt}/"},
        format="parquet",
    )

    job.commit()


if __name__ == "__main__":
    main()
