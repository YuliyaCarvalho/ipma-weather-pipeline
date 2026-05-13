WITH staging AS (
    SELECT *
    FROM {{ ref('stg_observations') }}
),

stations AS (
    SELECT
        CAST(station_id AS INT64) AS station_id,
        station_name,
        CAST(latitude AS FLOAT64) AS latitude,
        CAST(longitude AS FLOAT64) AS longitude
    FROM `ipma-weather-496012.raw.stations`
),

final AS (
    SELECT
        s.observed_at,
        s.station_id,
        st.station_name,
        st.latitude,
        st.longitude,
        CASE
            WHEN st.longitude < -25 THEN 'Açores'
            WHEN st.latitude < 33 THEN 'Madeira'
            ELSE 'Continental'
        END AS region,
        s.temperature_c,
        s.humidity_pct,
        s.precipitation_mm,
        s.wind_speed_kmh,
        s.wind_direction,
        s.pressure_hpa,
        s.solar_radiation_kjm2
    FROM staging s
    LEFT JOIN stations st ON s.station_id = st.station_id
)

SELECT * FROM final