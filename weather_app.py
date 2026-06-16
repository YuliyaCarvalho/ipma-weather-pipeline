"""
IPMA Weather Dashboard — Portugal
Streamlit + BigQuery + Plotly  ·  Neon / glow redesign
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from urllib.parse import quote

import pandas as pd
import plotly.graph_objects as go
import pytz
import requests
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account


# CONFIG

PROJECT_ID = "ipma-weather-496012"
DATASET = "mart"
VIEW_CURRENT = "current_conditions"
VIEW_OBS = "mart_observations"

NUTS2_GEOJSON_URL = (
    "https://raw.githubusercontent.com/eurostat/Nuts2json/master/pub/v2/2021/4326/10M/2.json"
)

NUTS2_TO_REGION = {
    "PT11": "Norte",
    "PT16": "Centro",
    "PT17": "Lisboa e Vale do Tejo",
    "PT18": "Alentejo",
    "PT15": "Algarve",
    "PT20": "Açores",
    "PT30": "Madeira",
}

REGION_ORDER = [
    "Norte",
    "Centro",
    "Lisboa e Vale do Tejo",
    "Alentejo",
    "Algarve",
    "Açores",
    "Madeira",
]

REGION_FALLBACK_VIEWPORT: dict[str, tuple[float, float, float]] = {
    "Madeira": (32.85, -16.80, 8.5),
    "Açores": (38.50, -28.50, 6.5),
}

# IPMA daily forecast cities: id → (name, lat, lon)
IPMA_CITIES: dict[int, tuple[str, float, float]] = {
    1010500: ("Aveiro",           40.6443,  -8.6455),
    1020500: ("Beja",             38.0154,  -7.8724),
    1030300: ("Braga",            41.5518,  -8.4229),
    1040200: ("Bragança",         41.8061,  -6.7590),
    1050200: ("Castelo Branco",   39.8221,  -7.4936),
    1060300: ("Coimbra",          40.2111,  -8.4291),
    1070500: ("Évora",            38.5667,  -7.9000),
    1080500: ("Faro",             37.0161,  -7.9350),
    1090700: ("Guarda",           40.5364,  -7.2678),
    1100900: ("Leiria",           39.7444,  -8.8072),
    1110600: ("Lisboa",           38.7167,  -9.1333),
    1121400: ("Portalegre",       39.2967,  -7.4286),
    1131200: ("Porto",            41.1496,  -8.6109),
    1141600: ("Santarém",         39.2333,  -8.6833),
    1151200: ("Setúbal",          38.5244,  -8.8882),
    1160900: ("Viana do Castelo", 41.6932,  -8.8350),
    1171400: ("Vila Real",        41.3005,  -7.7439),
    1182300: ("Viseu",            40.6566,  -7.9122),
    2310300: ("Ponta Delgada",    37.7333, -25.6667),
    3420300: ("Funchal",          32.6669, -16.9241),
}
DEFAULT_FORECAST_LOC = 1110600  # Lisboa

REGION_FORECAST_LOC: dict[str, int] = {
    "Norte":                 1131200,
    "Centro":                1060300,
    "Lisboa e Vale do Tejo": 1110600,
    "Alentejo":              1070500,
    "Algarve":               1080500,
    "Açores":                2310300,
    "Madeira":               3420300,
}

WEATHER_ICON: dict[int, str] = {
    1: "☀️", 2: "⛅", 3: "🌤️", 4: "☁️", 5: "🌥️",
    6: "🌫️", 7: "🌦️", 8: "🌧️", 9: "🌧️", 10: "🌦️",
    11: "🌦️", 12: "🌨️", 13: "❄️", 14: "⛈️", 15: "⛈️",
    16: "🌫️", 17: "🌨️", 18: "🌨️", 19: "🌫️", 20: "🌦️",
    21: "🌧️", 22: "🌧️", 23: "🌧️", 24: "❄️", 25: "❄️",
    26: "❄️", 27: "❄️", 28: "⛈️", 29: "⛈️",
}

WEATHER_DESC: dict[str, dict[int, str]] = {
    "EN": {
        1: "Clear sky", 2: "Partly cloudy", 3: "Sunny intervals",
        4: "Cloudy", 5: "Cloudy", 6: "Fog", 7: "Light rain",
        8: "Rain", 9: "Heavy rain", 10: "Light showers", 11: "Showers",
        12: "Snow showers", 13: "Snow", 14: "Thunderstorms", 15: "Thunderstorms",
        16: "Mist", 17: "Hail", 18: "Frost", 19: "Fog", 20: "Light showers",
        21: "Intermittent rain", 22: "Frequent rain", 23: "Heavy rain",
        24: "Light snow", 25: "Moderate snow", 26: "Heavy snow",
        27: "Snow", 28: "Thunderstorm+hail", 29: "Thunderstorm",
    },
    "PT": {
        1: "Céu limpo", 2: "Pouco nublado", 3: "Sol e nuvens",
        4: "Nublado", 5: "Muito nublado", 6: "Nevoeiro", 7: "Chuva fraca",
        8: "Chuva", 9: "Chuva forte", 10: "Aguaceiros fracos", 11: "Aguaceiros",
        12: "Aguaceiros neve", 13: "Neve", 14: "Trovoada", 15: "Trovoada",
        16: "Neblina", 17: "Granizo", 18: "Geada", 19: "Nevoeiro",
        20: "Aguaceiros fracos", 21: "Chuva por vezes", 22: "Chuva frequente",
        23: "Chuva forte", 24: "Neve fraca", 25: "Neve moderada",
        26: "Neve forte", 27: "Neve", 28: "Trovoada+granizo", 29: "Trovoada",
    },
}

WIND_CLASS_LABEL: dict[str, dict[int, str]] = {
    "EN": {1: "Weak", 2: "Moderate", 3: "Fresh", 4: "Strong", 5: "Very strong"},
    "PT": {1: "Fraco", 2: "Moderado", 3: "Fresco", 4: "Forte", 5: "Muito forte"},
}

LISBON_TZ = pytz.timezone("Europe/Lisbon")

TEMP_COLORSCALE = [
    [0.0, "#00b4d8"],
    [0.5, "#f5d90a"],
    [1.0, "#ff6b35"],
]


# I18N

STRINGS = {
    "EN": {
        "app_title": "IPMA Weather · Portugal",
        "greet_morning": "Good morning",
        "greet_afternoon": "Good afternoon",
        "greet_evening": "Good evening",
        "greet_suffix": "Portugal",
        "nat_avg": "National average",
        "nat_max": "Highest",
        "nat_min": "Lowest",
        "select_region_placeholder": "— Select region —",
        "select_station_placeholder": "— Select station —",
        "region_label": "Region",
        "station_label": "Station",
        "no_region_hint": "Select a region to see stations and detailed readings.",
        "no_station_hint": "Select a station to see live readings and the 24-hour trend.",
        "metric_temp": "Temperature",
        "metric_humidity": "Humidity",
        "metric_precip": "Precipitation",
        "metric_wind": "Wind",
        "metric_pressure": "Pressure",
        "metric_solar": "Solar index",
        "wind_unit": "km/h",
        "chart_title": "Last 24 hours — temperature",
        "chart_min": "min",
        "chart_max": "max",
        "chart_now": "now",
        "footer_live": "BIGQUERY · LIVE",
        "footer_observed": "observed",
        "footer_ago": "min ago",
        "loading": "Loading live data…",
        "active_stations": "Active stations",
        "inactive_stations": "Inactive",
        "stations_in_region": "stations in region",
        "lang_label": "Language",
        "rain_reporting": "stations reporting rain",
        "last_reading": "Last reading",
        "trend_tooltip": "compared to previous reading",
        "forecast_title": "5-day forecast",
        "rain_prob": "rain",
        "forecast_for": "Forecast for",
    },
    "PT": {
        "app_title": "IPMA Meteorologia · Portugal",
        "greet_morning": "Bom dia",
        "greet_afternoon": "Boa tarde",
        "greet_evening": "Boa noite",
        "greet_suffix": "Portugal",
        "nat_avg": "Média nacional",
        "nat_max": "Máxima",
        "nat_min": "Mínima",
        "select_region_placeholder": "— Seleccionar região —",
        "select_station_placeholder": "— Seleccionar estação —",
        "region_label": "Região",
        "station_label": "Estação",
        "no_region_hint": "Selecciona uma região para ver as estações e leituras detalhadas.",
        "no_station_hint": "Selecciona uma estação para ver leituras e a tendência de 24 horas.",
        "metric_temp": "Temperatura",
        "metric_humidity": "Humidade",
        "metric_precip": "Precipitação",
        "metric_wind": "Vento",
        "metric_pressure": "Pressão",
        "metric_solar": "Índice solar",
        "wind_unit": "km/h",
        "chart_title": "Últimas 24 horas — temperatura",
        "chart_min": "mín",
        "chart_max": "máx",
        "chart_now": "agora",
        "footer_live": "BIGQUERY · AO VIVO",
        "footer_observed": "observado",
        "footer_ago": "min atrás",
        "loading": "A carregar dados…",
        "active_stations": "Estações activas",
        "inactive_stations": "Inactivas",
        "stations_in_region": "estações na região",
        "lang_label": "Idioma",
        "rain_reporting": "estações com chuva",
        "last_reading": "Última leitura",
        "trend_tooltip": "comparado com a leitura anterior",
        "forecast_title": "Previsão 5 dias",
        "rain_prob": "chuva",
        "forecast_for": "Previsão para",
    },
}


# PAGE

st.set_page_config(
    page_title="IPMA Weather · Portugal",
    page_icon="🌤️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700;800;900&display=swap');

      #MainMenu, header, footer { visibility: hidden; }
      html, body, [class*="css"] { font-family: 'JetBrains Mono', monospace; }
      .stApp { background-color: #0d1117; color: #e6edf3; }
      section[data-testid="stSidebar"] { background-color: #0d1117; }
      .block-container { padding-top: 1rem; padding-bottom: 1rem; max-width: 1600px; }
      h1, h2, h3, h4, h5, h6 { color: #e6edf3 !important; font-family: 'JetBrains Mono', monospace; }

      /* ---------- TOP BAR ---------- */
      .topbar {
          display: flex; align-items: center; justify-content: space-between;
          padding: 4px 0 14px; border-bottom: 1px solid #1f2733; margin-bottom: 12px;
      }
      .topbar h1 {
          font-family: 'Oswald', sans-serif; font-size: 32px; font-weight: 700;
          margin: 0; letter-spacing: 2px; color: #e6edf3 !important;
          text-transform: uppercase; text-shadow: 0 0 12px rgba(0,245,255,0.25);
      }
      .clock {
          font-family: 'JetBrains Mono', monospace;
          font-size: 15px; color: #8b949e; text-align: right; line-height: 1.5;
      }
      .clock strong { color: #00f5ff; font-weight: 600; text-shadow: 0 0 8px rgba(0,245,255,0.5); }
      .topbar-right { display: flex; flex-direction: column; align-items: flex-end; gap: 8px; }

      /* ---------- LANGUAGE TOGGLE ---------- */
      .lang-toggle { display: flex; gap: 8px; justify-content: flex-end; align-items: center; }
      .lang-btn {
          font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 600;
          padding: 6px 16px; border-radius: 7px; text-decoration: none !important;
          color: #8b949e; border: 1px solid transparent; transition: all .15s; letter-spacing: 1px;
      }
      .lang-btn:hover { color: #e6edf3; }
      .lang-btn.sel {
          color: #ffffff; border-color: #bf5af2;
          box-shadow: 0 0 8px #bf5af2; background: rgba(191,90,242,0.10);
      }

      /* ---------- RAIN PILL ---------- */
      .rain-pill {
          display: inline-flex; align-items: center; gap: 8px;
          font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 500;
          color: #00b4d8; padding: 6px 16px; border: 1px solid #00b4d8;
          border-radius: 999px; box-shadow: 0 0 8px rgba(0,180,216,0.45);
          background: rgba(0,180,216,0.06); white-space: nowrap;
      }
      .rain-pill b { color: #e6edf3; font-weight: 700; }

      /* ---------- STAT PILLS (inline grid, stays within map column) ---------- */
      .stat-grid {
          display: grid; grid-template-columns: repeat(3, 1fr);
          gap: 8px; margin-bottom: 10px; width: 100%;
      }
      .stat {
          background: #0d1117; border: 1px solid #161b22; border-left: 3px solid #00f5ff;
          border-radius: 8px; padding: 10px 12px; box-shadow: 0 0 8px rgba(0,245,255,0.18);
          min-width: 0;
      }
      .stat .lbl {
          font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: 1.2px;
          color: #8b949e; text-transform: uppercase;
      }
      .stat .val {
          font-size: 24px; font-weight: 700; color: #e6edf3;
          letter-spacing: -0.5px; margin-top: 4px; white-space: nowrap;
      }
      .stat .unit { font-size: 12px; color: #8b949e; margin-left: 3px; font-weight: 400; }
      .stat .sub {
          font-size: 10px; color: #8b949e; margin-top: 3px;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      }
      .stat .val.hot  { color: #ff6b35; text-shadow: 0 0 10px rgba(255,107,53,0.4); }
      .stat .val.cold { color: #00b4d8; text-shadow: 0 0 10px rgba(0,180,216,0.4); }

      /* ---------- REGION LIST ---------- */
      .col-label {
          font-family: 'JetBrains Mono', monospace; font-size: 13px; letter-spacing: 1.6px;
          color: #e6edf3; text-transform: uppercase; margin: 4px 0 10px; font-weight: 600;
      }
      .region-list { display: flex; flex-direction: column; gap: 5px; width: 100%; }
      .region-row {
          display: flex !important; justify-content: space-between; align-items: center;
          width: 100% !important; box-sizing: border-box !important;
          padding: 8px 12px; border: 1px solid #3d444d; border-left: 3px solid #3d444d;
          border-radius: 8px; text-decoration: none !important; cursor: pointer;
          font-family: 'JetBrains Mono', monospace; text-transform: uppercase;
          letter-spacing: 1px; font-size: 12px; color: #8b949e; font-weight: 400;
          transition: all .15s;
      }
      .region-row:visited { color: #8b949e !important; text-decoration: none !important; }
      .region-row:hover {
          border-color: #00f5ff; color: #e6edf3;
          box-shadow: 0 0 8px rgba(0,245,255,0.22); text-decoration: none !important;
      }
      .region-row .temp { color: #8b949e; font-size: 12px; flex-shrink: 0; margin-left: 6px; }
      .region-row:hover .temp { color: #e6edf3; }
      .region-row.sel {
          border-color: #bf5af2; border-left-color: #bf5af2; color: #ffffff;
          box-shadow: 0 0 8px #bf5af2; background: rgba(191,90,242,0.09);
          text-decoration: none !important; font-weight: 700;
      }
      a.region-row.sel { color: #ffffff !important; }
      .region-row.sel .temp { color: #ffffff; font-weight: 700; }
      a.region-row { text-decoration: none !important; color: #8b949e; }
      a { text-decoration: none !important; }

      /* ---------- SELECTBOX ---------- */
      div[data-baseweb="select"] > div {
          background-color: #0d1117 !important; border-color: #3d444d !important;
          font-family: 'JetBrains Mono', monospace !important;
      }
      div[data-baseweb="select"] > div:hover { border-color: #00f5ff !important; }
      div[data-testid="stSelectbox"] > label,
      div[data-testid="stSelectbox"] > label p {
          font-family: 'JetBrains Mono', monospace !important;
          font-size: 13px !important; font-weight: 600 !important;
          letter-spacing: 1.6px !important; color: #e6edf3 !important;
          text-transform: uppercase !important; margin: 8px 0 6px !important; padding: 0 !important;
      }
      div[data-baseweb="select"] > div > div { color: #e6edf3 !important; }
      div[data-baseweb="select"] [data-testid="stMarkdownContainer"] p,
      div[data-baseweb="select"] div[class*="placeholder"],
      div[data-baseweb="select"] div[aria-selected="false"],
      div[data-baseweb="select"] span,
      div[data-baseweb="select"] div > div > div {
          font-family: 'JetBrains Mono', monospace !important;
          font-size: 12px !important; font-weight: 400 !important;
          letter-spacing: 1px !important; color: #8b949e !important;
      }

      /* ---------- FORECAST PILLS (horizontal strip) ---------- */
      .fc-header {
          font-family: 'JetBrains Mono', monospace; font-size: 13px; letter-spacing: 1.6px;
          color: #e6edf3; text-transform: uppercase; margin: 4px 0 6px; font-weight: 600;
      }
      .fc-city {
          font-family: 'JetBrains Mono', monospace; font-size: 13px;
          color: #00f5ff; font-weight: 600; margin-left: 8px; text-transform: none;
          letter-spacing: 0;
      }
      .fc-strip { display: flex; flex-direction: row; gap: 6px; width: 100%; }
      .fc-card {
          flex: 1; min-width: 0;
          display: flex; flex-direction: column; align-items: center;
          background: #0d1117; border: 1px solid #1f2733; border-top: 3px solid #1f2733;
          border-radius: 8px; padding: 7px 4px; text-align: center;
          font-family: 'JetBrains Mono', monospace;
      }
      .fc-card.today { border-top-color: #bf5af2; box-shadow: 0 0 8px rgba(191,90,242,0.35); }
      .fc-head {
          font-size: 12px; font-weight: 700; color: #e6edf3;
          text-transform: uppercase; letter-spacing: 1px; white-space: nowrap;
          margin-bottom: 4px;
      }
      .fc-head .fc-date { font-size: 11px; color: #8b949e; font-weight: 400; letter-spacing: 0; text-transform: none; }
      .fc-icon { font-size: 20px; margin: 2px 0 3px; }
      .fc-desc { font-size: 10px; color: #8b949e; line-height: 1.3; margin-bottom: 3px; }
      .fc-tmax { color: #ff6b35; font-weight: 700; font-size: 14px; }
      .fc-tmin { color: #8b949e; font-size: 11px; margin-left: 2px; }
      .fc-meta { font-size: 10px; color: #8b949e; margin-top: 3px; line-height: 1.4; }

      /* ---------- METRIC CARDS ---------- */
      .ncard {
          background: #0d1117; border: 1px solid #161b22; border-left: 3px solid #00f5ff;
          border-radius: 8px; padding: 10px 14px; margin-bottom: 8px;
          box-shadow: 0 0 8px rgba(0,245,255,0.22); min-height: 58px;
      }
      .ncard-top { display: flex; justify-content: space-between; align-items: center; }
      .ncard-lbl {
          font-family: 'JetBrains Mono', monospace; font-size: 12px; letter-spacing: 1.4px;
          color: #8b949e; text-transform: uppercase;
      }
      .ncard-val { font-size: 24px; font-weight: 700; color: #e6edf3; letter-spacing: -0.5px; margin-top: 3px; line-height: 1.05; }
      .ncard-val.big { font-size: 36px; color: #00f5ff; text-shadow: 0 0 14px rgba(0,245,255,0.5); }
      .ncard-unit { font-size: 12px; color: #8b949e; margin-left: 4px; font-weight: 400; }
      .trend { font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 600; cursor: help; }

      /* ---------- HINT / INFO BOX ---------- */
      div[data-testid="stAlert"] {
          background: #0d1117; border: 1px solid #1f2733; border-left: 3px solid #bf5af2;
          box-shadow: 0 0 8px rgba(191,90,242,0.2); color: #8b949e;
      }

      /* ---------- FOOTER ---------- */
      .footer {
          display: flex; align-items: center; justify-content: space-between;
          margin-top: 14px; padding: 10px 4px; border-top: 1px solid #1f2733;
          font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #8b949e; letter-spacing: 0.8px;
      }
      .footer .dot { color: #39ff14; margin-right: 6px; text-shadow: 0 0 6px rgba(57,255,20,0.7); }
    </style>
    """,
    unsafe_allow_html=True,
)


# SESSION STATE

if "lang" not in st.session_state:
    st.session_state["lang"] = "EN"
if "region" not in st.session_state:
    st.session_state["region"] = None
if "station" not in st.session_state:
    st.session_state["station"] = None


# QUERY-PARAM SYNC

_qp = st.query_params

if _qp.get("lang") in ("EN", "PT"):
    st.session_state["lang"] = _qp.get("lang")

if "region" in _qp:
    _rv = _qp.get("region")
    _new_region = None if _rv == "__none__" else _rv
    if _new_region is not None and _new_region not in REGION_ORDER:
        _new_region = st.session_state["region"]
    if _new_region != st.session_state["region"]:
        st.session_state["region"] = _new_region
        st.session_state["station"] = None


# AUTH + BIGQUERY

@st.cache_resource(show_spinner=False)
def get_bq_client() -> bigquery.Client:
    info = dict(st.secrets["gcp_service_account"])
    credentials = service_account.Credentials.from_service_account_info(info)
    return bigquery.Client(credentials=credentials, project=PROJECT_ID)


@st.cache_data(ttl=60, show_spinner=False)
def fetch_current_conditions() -> pd.DataFrame:
    client = get_bq_client()
    query = f"""
        SELECT
            observed_at, station_id, station_name,
            latitude, longitude, region,
            temperature_c, humidity_pct, precipitation_mm,
            wind_speed_kmh, wind_direction, pressure_hpa,
            solar_radiation_kjm2, solar_index
        FROM `{PROJECT_ID}.{DATASET}.{VIEW_CURRENT}`
    """
    df = client.query(query).to_dataframe()
    if not df.empty:
        df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)
    return df


@st.cache_data(ttl=300, show_spinner=False)
def fetch_station_24h(station_id: str) -> pd.DataFrame:
    client = get_bq_client()
    query = f"""
        SELECT observed_at, temperature_c
        FROM `{PROJECT_ID}.{DATASET}.{VIEW_OBS}`
        WHERE station_id = @station_id
          AND observed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
        ORDER BY observed_at
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("station_id", "INT64", int(station_id))]
    )
    df = client.query(query, job_config=job_config).to_dataframe()
    if not df.empty:
        df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)
    return df


@st.cache_data(ttl=60, show_spinner=False)
def fetch_station_recent(station_id: str) -> pd.DataFrame:
    client = get_bq_client()
    query = f"""
        SELECT observed_at, temperature_c, humidity_pct, precipitation_mm,
               wind_speed_kmh, pressure_hpa
        FROM `{PROJECT_ID}.{DATASET}.{VIEW_OBS}`
        WHERE station_id = @station_id
        ORDER BY observed_at DESC
        LIMIT 2
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("station_id", "INT64", int(station_id))]
    )
    df = client.query(query, job_config=job_config).to_dataframe()
    if not df.empty:
        df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)
    return df


@st.cache_data(ttl=86_400, show_spinner=False)
def fetch_nuts2_geojson() -> dict:
    r = requests.get(NUTS2_GEOJSON_URL, timeout=20)
    r.raise_for_status()
    gj = r.json()
    feats = []
    for f in gj.get("features", []):
        nuts_id = f.get("properties", {}).get("id", "")
        if not nuts_id.startswith("PT"):
            continue
        region_name = NUTS2_TO_REGION.get(nuts_id)
        if not region_name:
            continue
        f["properties"]["region"] = region_name
        f["id"] = region_name
        feats.append(f)
    gj["features"] = feats
    return gj


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_forecast(location_id: int) -> list:
    url = f"https://api.ipma.pt/open-data/forecast/meteorology/cities/daily/{location_id}.json"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json().get("data", [])[:5]
    except Exception:
        return []



# HELPERS

def greeting_word(hour: int, lang: str) -> str:
    s = STRINGS[lang]
    if hour < 12:
        return s["greet_morning"]
    if hour < 19:
        return s["greet_afternoon"]
    return s["greet_evening"]


def nearest_forecast_loc(lat: float, lon: float) -> int:
    """Return the IPMA city location ID nearest to the given coordinates."""
    best_id, best_dist = DEFAULT_FORECAST_LOC, float("inf")
    for loc_id, (_, clat, clon) in IPMA_CITIES.items():
        d = (lat - clat) ** 2 + (lon - clon) ** 2
        if d < best_dist:
            best_dist, best_id = d, loc_id
    return best_id


def bbox_from_features(features: list, region: str) -> Optional[tuple]:
    for f in features:
        if f["properties"].get("region") != region:
            continue
        coords = []

        def walk(node):
            if isinstance(node, (list, tuple)):
                if (len(node) >= 2 and isinstance(node[0], (int, float))
                        and isinstance(node[1], (int, float))):
                    coords.append((node[0], node[1]))
                else:
                    for child in node:
                        walk(child)

        walk(f["geometry"]["coordinates"])
        if not coords:
            return None
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        return (min(lons), min(lats), max(lons), max(lats))
    return None


def zoom_for_bbox(bbox: tuple) -> tuple:
    min_lon, min_lat, max_lon, max_lat = bbox
    center = ((min_lat + max_lat) / 2, (min_lon + max_lon) / 2)
    span = max(max_lon - min_lon, max_lat - min_lat)
    if span < 0.5:
        zoom = 11
    elif span < 1.0:
        zoom = 9.5
    elif span < 2.0:
        zoom = 8.5
    elif span < 4.0:
        zoom = 7.5
    elif span < 8.0:
        zoom = 6.5
    else:
        zoom = 5.4
    return center, zoom


def get_region_outlines(features: list, region: str) -> tuple:
    lats, lons = [], []
    for f in features:
        if f["properties"].get("region") != region:
            continue
        geom = f["geometry"]
        if geom["type"] == "Polygon":
            poly_groups = [geom["coordinates"]]
        elif geom["type"] == "MultiPolygon":
            poly_groups = geom["coordinates"]
        else:
            continue
        for poly_rings in poly_groups:
            for ring in poly_rings:
                for coord in ring:
                    lons.append(coord[0])
                    lats.append(coord[1])
                lons.append(None)
                lats.append(None)
    return lats, lons


def trend_span(curr, prev, lang: str, prev_time: str | None = None) -> str:
    base_tip = STRINGS[lang]["trend_tooltip"]
    tip = f"{base_tip} · {prev_time}" if prev_time else base_tip
    if prev is None or pd.isna(prev) or pd.isna(curr):
        return ""
    d = float(curr) - float(prev)
    if abs(d) < 0.05:
        return f'<span class="trend" title="{tip}" style="color:#8b949e">▬ 0.0</span>'
    if d > 0:
        return f'<span class="trend" title="{tip}" style="color:#ff6b35">▲ {d:+.1f}</span>'
    return f'<span class="trend" title="{tip}" style="color:#00b4d8">▼ {d:+.1f}</span>'


def render_forecast_pills(data: list, lang: str, s: dict, city_name: str) -> str:
    if not data:
        return ""
    today_str = datetime.now(LISBON_TZ).strftime("%Y-%m-%d")
    days_en = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    days_pt = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    months_en = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    months_pt = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
    days_map = days_en if lang == "EN" else days_pt
    months_map = months_en if lang == "EN" else months_pt

    html = (
        f'<div class="fc-header">{s["forecast_title"]}'
        f'<span class="fc-city">· {city_name}</span>'
        f'</div>'
        f'<div class="fc-strip">'
    )
    for d in data:
        date_str = d.get("forecastDate", "")
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            day_name = days_map[dt.weekday()]
            date_disp = f"{dt.day} {months_map[dt.month - 1]}"
        except Exception:
            day_name = date_str[:3]
            date_disp = date_str

        today_cls = "today" if date_str == today_str else ""
        wtype = int(d.get("idWeatherType", 1))
        icon = WEATHER_ICON.get(wtype, "🌡️")
        desc = WEATHER_DESC.get(lang, WEATHER_DESC["EN"]).get(wtype, "—")
        tmax = d.get("tMax", "—")
        tmin = d.get("tMin", "—")
        rain = d.get("precipitaProb", "0")
        wind_dir = d.get("predWindDir", "—")
        wind_cls = int(d.get("classWindSpeed", 0))
        wind_label = WIND_CLASS_LABEL.get(lang, {}).get(wind_cls, "")

        try:
            tmax_f = f"{float(tmax):.0f}"
            tmin_f = f"{float(tmin):.0f}"
        except (ValueError, TypeError):
            tmax_f, tmin_f = str(tmax), str(tmin)
        try:
            rain_f = f"{float(rain):.0f}%"
        except (ValueError, TypeError):
            rain_f = str(rain)

        html += (
            f'<div class="fc-card {today_cls}">'
            f'<div class="fc-head">{day_name} <span class="fc-date">/ {date_disp}</span></div>'
            f'<div class="fc-icon">{icon}</div>'
            f'<div class="fc-desc">{desc}</div>'
            f'<div><span class="fc-tmax">{tmax_f}°</span>'
            f'<span class="fc-tmin">{tmin_f}°</span></div>'
            f'<div class="fc-meta">💧 {rain_f} · {wind_dir} · {wind_label}</div>'
            f'</div>'
        )
    html += "</div>"
    return html


# TOP BAR  (rendered after data so rain count is available)

now_lisbon = datetime.now(LISBON_TZ)
lang = st.session_state["lang"]
S = STRINGS[lang]
_cur_region_param = quote(st.session_state["region"]) if st.session_state["region"] else "__none__"
greet = greeting_word(now_lisbon.hour, lang)
en_sel = "sel" if lang == "EN" else ""
pt_sel = "sel" if lang == "PT" else ""



# DATA

with st.spinner(S["loading"]):
    df = fetch_current_conditions()
    geojson = fetch_nuts2_geojson()

if df.empty:
    st.error("No data returned from BigQuery.")
    st.stop()

max_observed = df["observed_at"].max()
df["is_active"] = df["observed_at"] >= (max_observed - pd.Timedelta(hours=1))

region_avg = (
    df.groupby("region", as_index=False)["temperature_c"]
    .mean()
    .rename(columns={"temperature_c": "avg_temp_c"})
)
avg_map = dict(zip(region_avg["region"], region_avg["avg_temp_c"]))

nat_avg = df["temperature_c"].mean()
temp_df = df.dropna(subset=["temperature_c"])
if temp_df.empty:
    st.error("No temperature data available.")
    st.stop()
hot_row = temp_df.loc[temp_df["temperature_c"].idxmax()]
cold_row = temp_df.loc[temp_df["temperature_c"].idxmin()]

rain_df = df[df["precipitation_mm"] > 0].sort_values(["region", "station_name"])
rain_count = len(rain_df)
rain_hover = "&#10;".join(
    f"{row.region} · {row.station_name}" for row in rain_df.itertuples()
) if not rain_df.empty else ""

# Top bar (rendered here so rain_count is known)
st.markdown(
    f"""
    <div class="topbar">
      <h1>{greet}, {S['greet_suffix']}!</h1>
      <div class="clock">
        <div>{now_lisbon.strftime('%A · %d %b %Y')}</div>
        <strong>{now_lisbon.strftime('%H:%M:%S')}</strong>
        <span style="color:#8b949e">{now_lisbon.tzname()}</span>
      </div>
      <div class="topbar-right">
        <div class="rain-pill" title="{rain_hover}" style="cursor:help">
          🌧 <b>{rain_count}</b> {S['rain_reporting']}
        </div>
        <div class="lang-toggle">
          <a class="lang-btn {en_sel}" target="_self" href="?lang=EN&region={_cur_region_param}">EN</a>
          <a class="lang-btn {pt_sel}" target="_self" href="?lang=PT&region={_cur_region_param}">PT</a>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)



# SELECTED STATION + FORECAST LOCATION

selected_region = st.session_state["region"]
selected_station_id = st.session_state["station"]
station_row = None
if selected_station_id is not None:
    _match = df[df["station_id"] == selected_station_id]
    if not _match.empty:
        station_row = _match.iloc[0]

# Determine forecast location and city name
if station_row is not None:
    forecast_loc = nearest_forecast_loc(
        float(station_row["latitude"]), float(station_row["longitude"])
    )
elif selected_region:
    forecast_loc = REGION_FORECAST_LOC.get(selected_region, DEFAULT_FORECAST_LOC)
else:
    forecast_loc = DEFAULT_FORECAST_LOC

forecast_city = IPMA_CITIES[forecast_loc][0] if forecast_loc in IPMA_CITIES else "Lisboa"
forecast_data = fetch_forecast(forecast_loc)



# MAIN LAYOUT — columns 2 / 5 / 3

col_left, col_center, col_right = st.columns([2, 5, 3], gap="large")


# ---- LEFT: region list + station dropdown (vertically fills map height) ----
with col_left:
    st.markdown(f"<div class='col-label'>{S['region_label']}</div>", unsafe_allow_html=True)

    rows_html = ""
    for region in REGION_ORDER:
        avg_t = avg_map.get(region)
        temp_txt = f"{avg_t:.1f}°" if avg_t is not None and pd.notna(avg_t) else "—"
        sel_cls = "sel" if region == selected_region else ""
        href = f"?lang={lang}&region={quote(region)}"
        rows_html += (
            f'<a class="region-row {sel_cls}" target="_self" href="{href}">'
            f'<span>{region}</span><span class="temp">{temp_txt}</span></a>'
        )
    st.markdown(f'<div class="region-list">{rows_html}</div>', unsafe_allow_html=True)

    if selected_region:
        region_df = df[df["region"] == selected_region].copy()
        region_df = region_df.sort_values(["is_active", "station_name"], ascending=[False, True])

        station_options_data = [(None, S["select_station_placeholder"])]
        for _, row in region_df.iterrows():
            badge = "●" if row["is_active"] else "○"
            station_options_data.append((row["station_id"], f"{badge} {row['station_name']}"))

        labels = [lbl for _, lbl in station_options_data]
        ids = [sid for sid, _ in station_options_data]

        try:
            idx = ids.index(st.session_state["station"])
        except ValueError:
            idx = 0

        chosen_label = st.selectbox(
            S["station_label"], options=labels, index=idx, key="station_select",
        )
        chosen_id = ids[labels.index(chosen_label)]
        if chosen_id != st.session_state["station"]:
            st.session_state["station"] = chosen_id
            st.rerun()
    else:
        st.selectbox(
            S["station_label"],
            options=[S["select_station_placeholder"]],
            index=0,
            disabled=True,
            key="station_select_disabled",
        )


# ---- CENTER: stat pills (inline HTML grid) + map ----
with col_center:
    # Stat pills rendered as a single HTML grid — guaranteed to stay within column width
    st.markdown(
        f"""
        <div class="stat-grid">
          <div class="stat">
            <div class="lbl">{S['nat_avg']}</div>
            <div class="val">{nat_avg:.1f}<span class="unit"> °C</span></div>
            <div class="sub">{len(df)} {S['stations_in_region'].lower()}</div>
          </div>
          <div class="stat">
            <div class="lbl">{S['nat_max']}</div>
            <div class="val hot">{hot_row['temperature_c']:.1f}<span class="unit"> °C</span></div>
            <div class="sub">{hot_row['station_name']} · {hot_row['region']}</div>
          </div>
          <div class="stat">
            <div class="lbl">{S['nat_min']}</div>
            <div class="val cold">{cold_row['temperature_c']:.1f}<span class="unit"> °C</span></div>
            <div class="sub">{cold_row['station_name']} · {cold_row['region']}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Viewport
    if selected_region:
        bbox = bbox_from_features(geojson["features"], selected_region)
        if bbox is not None:
            (clat, clon), region_zoom = zoom_for_bbox(bbox)
        elif selected_region in REGION_FALLBACK_VIEWPORT:
            clat, clon, region_zoom = REGION_FALLBACK_VIEWPORT[selected_region]
        else:
            clat, clon, region_zoom = 39.5, -8.0, 5.6
    else:
        clat, clon, region_zoom = 39.5, -8.0, 5.6

    if station_row is not None:
        map_center = {"lat": float(station_row["latitude"]), "lon": float(station_row["longitude"])}
        map_zoom = min(region_zoom + 2.0, 12.0)
    else:
        map_center = {"lat": clat, "lon": clon}
        map_zoom = region_zoom

    fig = go.Figure(go.Choroplethmap(
        geojson=geojson,
        locations=region_avg["region"],
        z=region_avg["avg_temp_c"],
        featureidkey="properties.region",
        colorscale=TEMP_COLORSCALE,
        zmin=region_avg["avg_temp_c"].min(),
        zmax=region_avg["avg_temp_c"].max(),
        marker_opacity=0.5,
        marker_line_width=2,
        marker_line_color="#00f5ff",
        showscale=True,
        colorbar=dict(
            title=dict(text="°C", font=dict(color="#8b949e", size=11)),
            tickfont=dict(color="#8b949e", size=10),
            thickness=10, len=0.6, x=0.99,
            bgcolor="rgba(13,17,23,0.6)", outlinewidth=0,
        ),
    ))
    fig.update_layout(
        map=dict(
            style="carto-darkmatter",
            center={"lat": map_center["lat"], "lon": map_center["lon"]},
            zoom=map_zoom,
        ),
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        height=600,
        paper_bgcolor="#0d1117",
        plot_bgcolor="#0d1117",
        font=dict(color="#e6edf3", family="JetBrains Mono, monospace"),
    )

    # Region outlines + labels
    all_lats, all_lons = [], []
    label_lats, label_lons, label_texts = [], [], []
    for r in REGION_ORDER:
        r_lats, r_lons = get_region_outlines(geojson["features"], r)
        all_lats.extend(r_lats)
        all_lons.extend(r_lons)
        bbox = bbox_from_features(geojson["features"], r)
        if bbox is not None:
            clat_r = (bbox[1] + bbox[3]) / 2
            clon_r = (bbox[0] + bbox[2]) / 2
        elif r in REGION_FALLBACK_VIEWPORT:
            clat_r, clon_r, _ = REGION_FALLBACK_VIEWPORT[r]
        else:
            continue
        avg_t = avg_map.get(r)
        temp_lbl = f"{avg_t:.1f}°" if avg_t is not None and pd.notna(avg_t) else ""
        label_lats.append(clat_r)
        label_lons.append(clon_r)
        label_texts.append(f"{r}<br>{temp_lbl}")

    if all_lats:
        fig.add_trace(go.Scattermap(
            lat=all_lats, lon=all_lons, mode="lines",
            line=dict(width=3, color="#00f5ff"), opacity=1.0,
            hoverinfo="skip", showlegend=False,
        ))
    if label_lats:
        fig.add_trace(go.Scattermap(
            lat=label_lats, lon=label_lons, mode="text", text=label_texts,
            textfont=dict(size=14, color="#ffffff", family="JetBrains Mono, monospace"),
            hoverinfo="skip", showlegend=False,
        ))

    if selected_region:
        region_df = df[df["region"] == selected_region].copy()
        active_df = region_df[region_df["is_active"]]
        inactive_df = region_df[~region_df["is_active"]]

        if not inactive_df.empty:
            fig.add_trace(go.Scattermap(
                lat=inactive_df["latitude"], lon=inactive_df["longitude"], mode="markers",
                marker=dict(size=6, color="#3d444d", opacity=0.4),
                hovertext=inactive_df["station_name"], hoverinfo="text",
                name=S["inactive_stations"], showlegend=False,
            ))
        if not active_df.empty:
            fig.add_trace(go.Scattermap(
                lat=active_df["latitude"], lon=active_df["longitude"], mode="markers",
                marker=dict(
                    size=10, color=active_df["temperature_c"],
                    colorscale=TEMP_COLORSCALE,
                    cmin=region_avg["avg_temp_c"].min(),
                    cmax=region_avg["avg_temp_c"].max(),
                    showscale=False,
                ),
                hovertext=[f"{r.station_name}<br>{r.temperature_c:.1f} °C" for r in active_df.itertuples()],
                hoverinfo="text", name=S["active_stations"], showlegend=False,
            ))

        if station_row is not None:
            for sz, op in [(36, 0.28), (14, 0.55)]:
                fig.add_trace(go.Scattermap(
                    lat=[station_row["latitude"]], lon=[station_row["longitude"]], mode="markers",
                    marker=dict(size=sz, color="#bf5af2", opacity=op),
                    hoverinfo="skip", showlegend=False,
                ))
            fig.add_trace(go.Scattermap(
                lat=[station_row["latitude"]], lon=[station_row["longitude"]], mode="markers",
                marker=dict(size=7, color="#ffffff"),
                hovertext=[f"★ {station_row['station_name']}"],
                hoverinfo="text", showlegend=False,
            ))

    _map_key = f"map|{selected_region or ''}|{selected_station_id or ''}"
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key=_map_key)


# ---- RIGHT: metric cards + 24h chart ----
with col_right:
    if station_row is None:
        if not selected_region:
            st.info(S["no_region_hint"])
        else:
            st.info(S["no_station_hint"])
    else:
        recent = fetch_station_recent(str(selected_station_id))
        prev_row = recent.iloc[1] if len(recent) >= 2 else None

        _UNAVAILABLE = "currently unavailable"

        def fmt(val, spec) -> str:
            if val is None or (not isinstance(val, str) and pd.isna(val)):
                return _UNAVAILABLE
            if not spec:
                return str(val)
            return format(float(val), spec)

        def prev_val(field):
            if prev_row is None:
                return None
            return prev_row.get(field)

        prev_time = (
            prev_row["observed_at"].tz_convert(LISBON_TZ).strftime("%Y-%m-%d %H:%M:%S")
            if prev_row is not None else None
        )

        wind_dir = station_row.get("wind_direction") or "—"
        solar_raw = station_row.get("solar_radiation_kjm2")
        solar_index = station_row.get("solar_index")
        solar_label = fmt(solar_index, "") if solar_index is not None else _UNAVAILABLE
        solar_unit = f"{solar_raw:.0f} kJ/m²" if solar_raw is not None and pd.notna(solar_raw) else ""

        def card(label, value, unit, trend_str, big=False):
            cls = "ncard-val big" if big else "ncard-val"
            if value == _UNAVAILABLE:
                return (
                    f'<div class="ncard">'
                    f'<div class="ncard-top"><span class="ncard-lbl">{label}</span></div>'
                    f'<div style="font-size:12px;color:#ff3b3b;text-shadow:0 0 8px rgba(255,59,59,0.6);'
                    f'margin-top:6px;font-family:\'JetBrains Mono\',monospace">{_UNAVAILABLE}</div>'
                    f'</div>'
                )
            return (
                f'<div class="ncard">'
                f'<div class="ncard-top"><span class="ncard-lbl">{label}</span>{trend_str}</div>'
                f'<div class="{cls}">{value}<span class="ncard-unit">{unit}</span></div>'
                f'</div>'
            )

        cards_html = ""
        cards_html += card(
            S["metric_temp"], fmt(station_row["temperature_c"], ".1f"), "°C",
            trend_span(station_row["temperature_c"], prev_val("temperature_c"), lang, prev_time), big=True,
        )
        cards_html += card(
            S["metric_humidity"], fmt(station_row["humidity_pct"], ".0f"), "%",
            trend_span(station_row["humidity_pct"], prev_val("humidity_pct"), lang, prev_time),
        )
        cards_html += card(
            S["metric_precip"], fmt(station_row["precipitation_mm"], ".1f"), "mm",
            trend_span(station_row["precipitation_mm"], prev_val("precipitation_mm"), lang, prev_time),
        )
        cards_html += card(
            S["metric_wind"], fmt(station_row["wind_speed_kmh"], ".0f"), f"{S['wind_unit']} · {wind_dir}",
            trend_span(station_row["wind_speed_kmh"], prev_val("wind_speed_kmh"), lang, prev_time),
        )
        cards_html += card(
            S["metric_pressure"], fmt(station_row["pressure_hpa"], ".0f"), "hPa",
            trend_span(station_row["pressure_hpa"], prev_val("pressure_hpa"), lang, prev_time),
        )
        cards_html += card(S["metric_solar"], solar_label, solar_unit, "")
        st.markdown(cards_html, unsafe_allow_html=True)

        st.markdown(
            f"<div class='col-label' style='margin-top:6px'>{S['chart_title']}</div>",
            unsafe_allow_html=True,
        )
        hist = fetch_station_24h(str(selected_station_id))
        if hist.empty:
            st.info("—")
        else:
            hist_local = hist.copy()
            hist_local["t_local"] = hist_local["observed_at"].dt.tz_convert(LISBON_TZ)
            min_idx = hist_local["temperature_c"].idxmin()
            max_idx = hist_local["temperature_c"].idxmax()
            now_idx = hist_local["t_local"].idxmax()

            chart = go.Figure()
            chart.add_trace(go.Scatter(
                x=hist_local["t_local"], y=hist_local["temperature_c"],
                mode="lines", line=dict(color="#00f5ff", width=2),
                fill="tozeroy", fillcolor="rgba(0, 245, 255, 0.14)",
                hovertemplate="%{x|%H:%M} · %{y:.1f}°C<extra></extra>",
            ))
            for idx, label, color, position in [
                (min_idx, f"{S['chart_min']} {hist_local.loc[min_idx, 'temperature_c']:.1f}°", "#00b4d8", "bottom center"),
                (max_idx, f"{S['chart_max']} {hist_local.loc[max_idx, 'temperature_c']:.1f}°", "#ff6b35", "top center"),
                (now_idx, f"{S['chart_now']} {hist_local.loc[now_idx, 'temperature_c']:.1f}°", "#bf5af2", "top center"),
            ]:
                chart.add_trace(go.Scatter(
                    x=[hist_local.loc[idx, "t_local"]], y=[hist_local.loc[idx, "temperature_c"]],
                    mode="markers+text",
                    marker=dict(size=8, color=color, line=dict(color="#0d1117", width=1.5)),
                    text=[label], textposition=position,
                    textfont=dict(color=color, size=11, family="JetBrains Mono, monospace"),
                    showlegend=False, hoverinfo="skip",
                ))
            chart.update_layout(
                height=200, margin=dict(l=0, r=0, t=18, b=10),
                paper_bgcolor="#0d1117", plot_bgcolor="#0d1117", showlegend=False,
                xaxis=dict(showgrid=False, color="#8b949e", tickfont=dict(size=10), tickformat="%H:%M", nticks=5, showline=False),
                yaxis=dict(showgrid=False, color="#8b949e", tickfont=dict(size=10), showline=False, zeroline=False),
            )
            st.plotly_chart(chart, use_container_width=True, config={"displayModeBar": False})



# FORECAST STRIP — horizontal, below left+center columns, right edge = map edge

st.markdown("<div style='margin-top:-14px'>", unsafe_allow_html=True)
fc_col, _ = st.columns([7, 3], gap="large")
with fc_col:
    fc_html = render_forecast_pills(forecast_data, lang, S, forecast_city)
    if fc_html:
        st.markdown(fc_html, unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)



# FOOTER

ago_min = max(0, int((datetime.now(pytz.UTC) - max_observed.to_pydatetime()).total_seconds() // 60))
observed_str = max_observed.tz_convert(LISBON_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")

st.markdown(
    f"""
    <div class="footer">
      <div><span class="dot">●</span>{S['footer_live']} &nbsp;·&nbsp;
        {S['footer_observed']} {observed_str} &nbsp;·&nbsp;
        {ago_min} {S['footer_ago']}</div>
      <div>{PROJECT_ID}.{DATASET}.{VIEW_CURRENT}</div>
    </div>
    """,
    unsafe_allow_html=True,
)
