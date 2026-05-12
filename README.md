# IPMA Weather Pipeline

Automated data engineering pipeline that ingests hourly weather observations from 222 meteorological stations across Portugal, transforms and validates the data through a layered dbt architecture, and loads it into BigQuery for downstream analytics.

**Stack:** Python · BigQuery · SQL · dbt Core · GitHub Actions · Looker Studio

---

## Architecture

```
IPMA Public API
      ↓
Python ingestion script
      ↓  daily batch · GitHub Actions cron 09:00 UTC
BigQuery — raw layer
  ├── raw.observations   (append-only, ~4150 rows/day)
  └── raw.stations       (truncate-reload, 222 stations)
      ↓
dbt staging layer
  └── staging.stg_observations
        cast types · null -99.0 · decode wind direction · deduplicate
      ↓
dbt mart layer
  └── mart.mart_observations
        join station metadata · final column selection
      ↓
Looker Studio dashboard (in progress)
```

---

## Project Structure

```
ipma-weather-pipeline/
├── .github/
│   └── workflows/
│       └── pipeline.yml        
├── ingestion/
│   └── ingest.py               
├── dbt_project/
│   ├── models/
│   │   ├── staging/
│   │   │   ├── stg_observations.sql
│   │   │   └── schema.yml      
│   │   └── mart/
│   │       └── mart_observations.sql
│   ├── macros/
│   │   └── generate_schema_name.sql
│   ├── packages.yml
│   └── dbt_project.yml
├── requirements.txt
└── README.md
```

---

## Data Source

[IPMA](https://www.ipma.pt/en/) (Instituto Português do Mar e da Atmosfera) is Portugal's national meteorological service. The pipeline consumes two public endpoints - no authentication required:

- **Observations:** hourly station measurements, last 24 hours, updated hourly
- **Stations:** list of all active meteorological stations with coordinates

---

### Observation fields

| Field | Description | Unit | Raw field name |
|---|---|---|---|
| `observed_at` | Observation timestamp | TIMESTAMP | `timestamp` |
| `station_id` | Station identifier | INT64 | `station_id` |
| `temperature_c` | Air temperature at 1.5m height | °C | `temperatura` |
| `humidity_pct` | Relative humidity | % | `humidade` |
| `precipitation_mm` | Accumulated precipitation | mm | `precAcumulada` |
| `wind_speed_kmh` | Wind speed at 10m height | km/h | `intensidadeVentoKM` |
| `wind_direction` | Wind direction (decoded label) | STRING | `idDireccVento` |
| `pressure_hpa` | Atmospheric pressure at sea level | hPa | `pressao` |
| `solar_radiation_kjm2` | Solar radiation | kJ/m2 | `radiacao` |

---

## Pipeline Design Decisions

**Raw layer is append-only and never modified.**
Every API response is landed as-is, with an `ingested_at` timestamp. If the pipeline runs twice, duplicates accumulate in raw - intentionally. This preserves a complete audit trail. Deduplication happens in dbt staging, not ingestion.

**Stations use truncate-reload, not append.**
Station metadata is stable but can change (new stations, renamed locations). Truncating and reloading on every run ensures the reference table always reflects the current state without accumulating redundant history.

**Sentinel values (-99.0) are nulled in staging, not ingestion.**
IPMA uses -99.0 to indicate missing measurements. Converting these to NULL in the transformation layer keeps raw faithful to the source and makes the nullification logic explicit, testable, and auditable.

**dbt schema naming uses a custom macro.**
A `generate_schema_name` macro overrides dbt's default behaviour of concatenating the target dataset with the model schema, ensuring models build into `staging` and `mart` exactly as named.

---

## Data Quality Tests

8 automated dbt tests run on every pipeline execution:

| Test | Column | Rule |
|---|---|---|
| `not_null` | `observed_at` | No missing timestamps |
| `not_null` | `station_id` | No missing station references |
| `expression_is_true` | `observed_at` | Timestamp not in the future |
| `accepted_range` | `temperature_c` | Between -20°C and 50°C |
| `accepted_range` | `humidity_pct` | Between 0% and 100% |
| `accepted_range` | `wind_speed_kmh` | Between 0 and 220 km/h |
| `accepted_range` | `pressure_hpa` | Between 940 and 1060 hPa |
| `accepted_values` | `wind_direction` | Valid compass labels only |

If any test fails, GitHub Actions marks the run as failed and sends an email notification.

---

## Setup

### Prerequisites

- Python 3.13+
- Google Cloud project with BigQuery enabled
- Service account with `BigQuery Data Editor` and `BigQuery Job User` roles
- dbt Core with BigQuery adapter (`pip install dbt-bigquery`)

### Local setup

```bash
git clone https://github.com/YuliyaCarvalho/ipma-weather-pipeline.git
cd ipma-weather-pipeline


# create and activate virtual environment
python -m venv venv
source venv/Scripts/activate  (# Windows Git Bash)
source venv/bin/activate     (# Mac/Linux)

# install dependencies
pip install -r requirements.txt

# add your GCP service account key
mkdir secrets (# place your key at secrets/gcp_key.json)

# configure dbt profile at ~/.dbt/profiles.yml
# see dbt_project/profiles_template.yml for the expected structure
```

---

### BigQuery datasets required

Create the following datasets in your GCP project, region `europe-west1`:

- `raw`
- `staging`
- `mart`

### Run manually

```bash
# ingestion
python ingestion/ingest.py

# dbt transformation + tests
cd dbt_project
dbt deps
dbt run
dbt test
```

---


### Automated schedule

The pipeline runs daily at **09:00 UTC** via GitHub Actions. Two repository secrets are required:

- `GCP_KEY` — contents of your service account JSON key
- `DBT_PROFILES` — contents of your `~/.dbt/profiles.yml`

---

## Author

[Yulia Carvalho](https://yuliyacarvalho.github.io/Portfolio-Website/) · [LinkedIn](https://www.linkedin.com/in/yuliyacarvalho) · [Portfolio Website](https://yuliyacarvalho.github.io/Portfolio-Website/)