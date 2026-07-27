from common.athena import run_query

rows = run_query("SELECT count(*) AS n FROM raw_matches")
print("Athena via boto3 returned:", rows)