import requests
import os
import json
from datetime import datetime, timezone
from google.cloud import bigquery

# credentials
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "secrets/gcp_key.json"

# config
PROJECT_ID = "ipma-weather-496012"
DATASET = "raw"

def create_observations_table_if_not_exists(client):
    schema = [
        bigquery.SchemaField("timestamp", "STRING"),
        bigquery.SchemaField("station_id", "STRING"),
        bigquery.SchemaField("ingested_at", "STRING"),
        bigquery.SchemaField("intensidadeVentoKM", "FLOAT"),
        bigquery.SchemaField("intensidadeVento", "FLOAT"),
        bigquery.SchemaField("idDireccVento", "FLOAT"),
        bigquery.SchemaField("temperatura", "FLOAT"),
        bigquery.SchemaField("precAcumulada", "FLOAT"),
        bigquery.SchemaField("humidade", "FLOAT"),
        bigquery.SchemaField("pressao", "FLOAT"),
        bigquery.SchemaField("radiacao", "FLOAT"),
    ]
    table_ref = f"{PROJECT_ID}.{DATASET}.observations"
    client.create_table(bigquery.Table(table_ref, schema=schema), exists_ok=True)
    print(f"Table {table_ref} ready")

def create_stations_table_if_not_exists(client):
    schema = [
        bigquery.SchemaField("station_id", "STRING"),
        bigquery.SchemaField("station_name", "STRING"),
        bigquery.SchemaField("latitude", "STRING"),
        bigquery.SchemaField("longitude", "STRING"),
        bigquery.SchemaField("updated_at", "STRING"),
    ]
    table_ref = f"{PROJECT_ID}.{DATASET}.stations"
    client.create_table(bigquery.Table(table_ref, schema=schema), exists_ok=True)
    print(f"Table {table_ref} ready")

def fetch_observations():
    url = "https://api.ipma.pt/open-data/observation/meteorology/stations/observations.json"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()

    rows = []
    ingested_at = datetime.now(timezone.utc).isoformat()

    for timestamp, stations in data.items():
        for station_id, fields in stations.items():
            if fields is None:
                continue
            row = {
                "timestamp": timestamp,
                "station_id": station_id,
                "ingested_at": ingested_at,
            }
            row.update(fields)
            rows.append(row)

    return rows

def fetch_and_load_stations(client):
    url = "https://api.ipma.pt/open-data/observation/meteorology/stations/stations.json"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()

    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    rows = []
    for station in data:
        rows.append({
            "station_id": str(station["properties"]["idEstacao"]),
            "station_name": station["properties"]["localEstacao"],
            "latitude": str(station["geometry"]["coordinates"][1]),
            "longitude": str(station["geometry"]["coordinates"][0]),
            "updated_at": updated_at,
        })

    table_ref = f"{PROJECT_ID}.{DATASET}.stations"
    tmp_file = "tmp_stations.json"

    with open(tmp_file, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        ignore_unknown_values=True,
    )

    with open(tmp_file, "rb") as f:
        job = client.load_table_from_file(f, table_ref, job_config=job_config)

    job.result()
    print(f"Loaded {len(rows)} stations into {table_ref}")

def load_observations_to_bigquery(client, rows):
    table_ref = f"{PROJECT_ID}.{DATASET}.observations"
    tmp_file = "tmp_observations.json"

    with open(tmp_file, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        ignore_unknown_values=True,
    )

    with open(tmp_file, "rb") as f:
        job = client.load_table_from_file(f, table_ref, job_config=job_config)

    job.result()
    print(f"Loaded {len(rows)} rows into {table_ref}")

if __name__ == "__main__":
    client = bigquery.Client(project=PROJECT_ID)

    create_observations_table_if_not_exists(client)
    create_stations_table_if_not_exists(client)

    print("Fetching stations...")
    fetch_and_load_stations(client)

    print("Fetching observations...")
    rows = fetch_observations()
    print(f"Fetched {len(rows)} rows")

    load_observations_to_bigquery(client, rows)