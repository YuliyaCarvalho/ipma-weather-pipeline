import requests

url = "https://api.ipma.pt/open-data/observation/meteorology/stations/observations.json"

response = requests.get(url)
data = response.json()

rows = []

for timestamp, stations in data.items():
    for station_id, fields in stations.items():
        if fields is None:
            continue
        row = {
            "timestamp": timestamp,
            "station_id": station_id,
        }
        row.update(fields)
        rows.append(row)

print("Total rows:", len(rows))
print("First row:", rows[0])

import json
none_count = sum(1 for stations in data.values() for fields in stations.values() if fields is None)
print("None fields count:", none_count)

# check if -99.0 appears anywhere
minus99_count = sum(
    1 for row in rows
    for val in row.values()
    if val == -99.0
)
print("-99.0 values count:", minus99_count)