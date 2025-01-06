from google.cloud import bigquery

# Initialize the BigQuery Client
client = bigquery.Client()

# SQL query to truncate the table
query = """
    TRUNCATE TABLE `case-study-446714.gcp.students`
"""

# Execute the query
client.query(query).result()  # Wait for the query to finish

print("Table contents cleared successfully!")
