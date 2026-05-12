WITH source AS (
    SELECT *
    FROM `ipma-weather-496012.raw.observations`
),

deduplicated AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY timestamp, station_id ORDER BY ingested_at DESC) AS row_num
    FROM source
),

cleaned AS (
    SELECT
        CAST(CONCAT(timestamp, ':00') AS TIMESTAMP) AS observed_at,
        CAST(station_id AS INT64) AS station_id,
        CAST(ingested_at AS TIMESTAMP) AS ingested_at,
        NULLIF(temperatura, -99.0) AS temperature_c,
        NULLIF(humidade, -99.0) AS humidity_pct,
        NULLIF(precAcumulada, -99.0) AS precipitation_mm,
        NULLIF(intensidadeVentoKM, -99.0) AS wind_speed_kmh,
        NULLIF(pressao, -99.0) AS pressure_hpa,
        NULLIF(radiacao, -99.0) AS solar_radiation_kjm2,

        CASE CAST(idDireccVento AS INT64)
            WHEN 0 THEN 'No direction'
            WHEN 1 THEN 'N'
            WHEN 2 THEN 'NE'
            WHEN 3 THEN 'E'
            WHEN 4 THEN 'SE'
            WHEN 5 THEN 'S'
            WHEN 6 THEN 'SW'
            WHEN 7 THEN 'W'
            WHEN 8 THEN 'NW'
            WHEN 9 THEN 'N'
            ELSE NULL
        END AS wind_direction
    FROM deduplicated
    WHERE row_num = 1
)

SELECT * FROM cleaned
