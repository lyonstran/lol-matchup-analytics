import os
import time

import boto3
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

_client = None


def client():
    global _client
    if _client is None:
        _client = boto3.client("athena", region_name=os.environ["AWS_REGION"])
    return _client


def run_query(sql: str, poll_seconds: float = 1.0) -> list[dict]:
    """Run an Athena query to completion; return rows as a list of dicts."""
    athena = client()
    resp = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": os.environ.get("ATHENA_DATABASE", "lol")},
        ResultConfiguration={"OutputLocation": os.environ["ATHENA_OUTPUT"]},
    )
    qid = resp["QueryExecutionId"]

    while True:
        info = athena.get_query_execution(QueryExecutionId=qid)
        state = info["QueryExecution"]["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(poll_seconds)

    if state != "SUCCEEDED":
        reason = info["QueryExecution"]["Status"].get("StateChangeReason", "")
        raise RuntimeError(f"Athena query {state}: {reason}")

    rows, columns = [], None
    paginator = athena.get_paginator("get_query_results")
    for page in paginator.paginate(QueryExecutionId=qid):
        for r in page["ResultSet"]["Rows"]:
            values = [c.get("VarCharValue") for c in r["Data"]]
            if columns is None:
                columns = values          # first row overall = header
                continue
            rows.append(dict(zip(columns, values)))
    return rows