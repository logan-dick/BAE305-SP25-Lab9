import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

st.set_page_config(page_title="Water Quality Explorer", layout="wide")

st.title("Water Quality Explorer")
st.write(
    "Upload station.csv and narrowresult.csv, choose a characteristic, "
    "filter by date and value range, then view the stations on a map and the trend over time."
)

# -------------------------------------------------
# Helper functions
# -------------------------------------------------
@st.cache_data
def load_station_data(file):
    df = pd.read_csv(file)
    needed = [
        "MonitoringLocationIdentifier",
        "MonitoringLocationName",
        "LatitudeMeasure",
        "LongitudeMeasure",
    ]
    df = df[needed].copy()
    df = df.dropna(subset=["MonitoringLocationIdentifier", "LatitudeMeasure", "LongitudeMeasure"])
    df = df.drop_duplicates(subset=["MonitoringLocationIdentifier"])
    return df

@st.cache_data
def load_result_data(file):
    df = pd.read_csv(file)
    needed = [
        "MonitoringLocationIdentifier",
        "CharacteristicName",
        "ActivityStartDate",
        "ResultMeasureValue",
        "ResultMeasure/MeasureUnitCode",
    ]
    df = df[needed].copy()

    df["ActivityStartDate"] = pd.to_datetime(df["ActivityStartDate"], errors="coerce")
    df["ResultMeasureValue"] = pd.to_numeric(df["ResultMeasureValue"], errors="coerce")

    df = df.dropna(
        subset=[
            "MonitoringLocationIdentifier",
            "CharacteristicName",
            "ActivityStartDate",
            "ResultMeasureValue",
        ]
    )
    return df

def try_load_default_csv(filename):
    path = Path(filename)
    if path.exists():
        return path
    return None

# -------------------------------------------------
# File input
# -------------------------------------------------
st.sidebar.header("Data Input")

station_file = st.sidebar.file_uploader("Upload station.csv", type=["csv"])
result_file = st.sidebar.file_uploader("Upload narrowresult.csv", type=["csv"])

# Fallback to local repo files if user doesn't upload them
if station_file is None:
    station_file = try_load_default_csv("station.csv")

if result_file is None:
    result_file = try_load_default_csv("narrowresult.csv")

if station_file is None or result_file is None:
    st.info("Upload both CSV files, or place station.csv and narrowresult.csv in the same GitHub repository as this app.")
    st.stop()

# -------------------------------------------------
# Load data
# -------------------------------------------------
try:
    station_df = load_station_data(station_file)
    result_df = load_result_data(result_file)
except Exception as e:
    st.error(f"Error loading files: {e}")
    st.stop()

# Merge data
merged_df = pd.merge(
    result_df,
    station_df,
    on="MonitoringLocationIdentifier",
    how="inner"
)

if merged_df.empty:
    st.warning("No matching station/result records were found after merging the files.")
    st.stop()

# -------------------------------------------------
# Characteristic selection
# -------------------------------------------------
characteristics = sorted(merged_df["CharacteristicName"].dropna().unique())

selected_characteristic = st.selectbox(
    "Select a water quality characteristic",
    characteristics
)

char_df = merged_df[merged_df["CharacteristicName"] == selected_characteristic].copy()

if char_df.empty:
    st.warning("No data found for the selected characteristic.")
    st.stop()

# -------------------------------------------------
# Date range filter
# -------------------------------------------------
min_date = char_df["ActivityStartDate"].min().date()
max_date = char_df["ActivityStartDate"].max().date()

date_range = st.slider(
    "Select date range",
    min_value=min_date,
    max_value=max_date,
    value=(min_date, max_date)
)

filtered_df = char_df[
    (char_df["ActivityStartDate"].dt.date >= date_range[0]) &
    (char_df["ActivityStartDate"].dt.date <= date_range[1])
].copy()

if filtered_df.empty:
    st.warning("No data found in that date range.")
    st.stop()

# -------------------------------------------------
# Value range filter
# -------------------------------------------------
min_val = float(filtered_df["ResultMeasureValue"].min())
max_val = float(filtered_df["ResultMeasureValue"].max())

# Protect against identical min/max
if min_val == max_val:
    value_range = (min_val, max_val)
    st.write(f"Only one value is available for this filter: {min_val}")
else:
    value_range = st.slider(
        "Select result value range",
        min_value=min_val,
        max_value=max_val,
        value=(min_val, max_val)
    )

filtered_df = filtered_df[
    (filtered_df["ResultMeasureValue"] >= value_range[0]) &
    (filtered_df["ResultMeasureValue"] <= value_range[1])
].copy()

if filtered_df.empty:
    st.warning("No data found in that value range.")
    st.stop()

# -------------------------------------------------
# Summary
# -------------------------------------------------
unit_values = filtered_df["ResultMeasure/MeasureUnitCode"].dropna().unique()
unit_label = unit_values[0] if len(unit_values) > 0 else "units"

site_count = filtered_df["MonitoringLocationIdentifier"].nunique()
sample_count = len(filtered_df)

col1, col2, col3 = st.columns(3)
col1.metric("Characteristic", selected_characteristic)
col2.metric("Stations shown", site_count)
col3.metric("Measurements shown", sample_count)

# -------------------------------------------------
# Map data
# -------------------------------------------------
map_df = (
    filtered_df.groupby(
        [
            "MonitoringLocationIdentifier",
            "MonitoringLocationName",
            "LatitudeMeasure",
            "LongitudeMeasure",
        ],
        as_index=False
    )
    .agg(
        MeanValue=("ResultMeasureValue", "mean"),
        MinValue=("ResultMeasureValue", "min"),
        MaxValue=("ResultMeasureValue", "max"),
        Measurements=("ResultMeasureValue", "count"),
    )
)

st.subheader("Station Map")

fig_map = px.scatter_mapbox(
    map_df,
    lat="LatitudeMeasure",
    lon="LongitudeMeasure",
    hover_name="MonitoringLocationName",
    hover_data={
        "MonitoringLocationIdentifier": True,
        "MeanValue": ":.2f",
        "MinValue": ":.2f",
        "MaxValue": ":.2f",
        "Measurements": True,
        "LatitudeMeasure": False,
        "LongitudeMeasure": False,
    },
    color="MeanValue",
    size="Measurements",
    zoom=5,
    height=600,
    title=f"Stations with {selected_characteristic} in selected date/value range"
)

fig_map.update_layout(mapbox_style="open-street-map", margin={"r":0, "t":50, "l":0, "b":0})
st.plotly_chart(fig_map, use_container_width=True)

# -------------------------------------------------
# Trend over time
# -------------------------------------------------
st.subheader("Trend Over Time")

trend_df = filtered_df.sort_values(["MonitoringLocationIdentifier", "ActivityStartDate"])

fig_trend = px.line(
    trend_df,
    x="ActivityStartDate",
    y="ResultMeasureValue",
    color="MonitoringLocationIdentifier",
    hover_name="MonitoringLocationName",
    markers=True,
    title=f"{selected_characteristic} over time by station",
    labels={
        "ActivityStartDate": "Date",
        "ResultMeasureValue": f"Value ({unit_label})",
        "MonitoringLocationIdentifier": "Station ID",
    },
)

fig_trend.update_layout(legend_title_text="Station ID")
st.plotly_chart(fig_trend, use_container_width=True)

# -------------------------------------------------
# Show filtered data table
# -------------------------------------------------
with st.expander("Show filtered data table"):
    st.dataframe(
        filtered_df[
            [
                "MonitoringLocationIdentifier",
                "MonitoringLocationName",
                "CharacteristicName",
                "ActivityStartDate",
                "ResultMeasureValue",
                "ResultMeasure/MeasureUnitCode",
                "LatitudeMeasure",
                "LongitudeMeasure",
            ]
        ].sort_values(["MonitoringLocationIdentifier", "ActivityStartDate"]),
        use_container_width=True
    )
