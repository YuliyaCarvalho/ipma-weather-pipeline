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
            WHEN st.latitude < 33.5 AND st.longitude < -15 THEN 'Madeira'
            WHEN st.latitude < 37.5 THEN 'Algarve'
            WHEN st.latitude < 38.5 THEN 'Alentejo'
            WHEN st.latitude BETWEEN 38.5 AND 39.5 AND st.longitude > -8.5 THEN 'Alentejo'
            WHEN st.latitude BETWEEN 38.5 AND 39.5 AND st.longitude <= -8.5 THEN 'Lisboa e Vale do Tejo'
            WHEN st.latitude BETWEEN 39.5 AND 40.5 THEN 'Centro'
            WHEN st.latitude > 40.5 THEN 'Norte'
            ELSE 'Centro'
        END AS region,
        s.temperature_c,
        s.humidity_pct,
        s.precipitation_mm,
        s.wind_speed_kmh,
        s.wind_direction,
        s.pressure_hpa,
        s.solar_radiation_kjm2,
        CASE
            WHEN s.solar_radiation_kjm2 IS NULL THEN NULL
            WHEN s.solar_radiation_kjm2 / 3.6 < 200 THEN 'Low'
            WHEN s.solar_radiation_kjm2 / 3.6 < 400 THEN 'Moderate'
            WHEN s.solar_radiation_kjm2 / 3.6 < 600 THEN 'High'
            WHEN s.solar_radiation_kjm2 / 3.6 < 800 THEN 'Very High'
            ELSE 'Extreme'
        END AS solar_index
    FROM staging s
    LEFT JOIN stations st ON s.station_id = st.station_id
)

SELECT * FROM final