"""
Name:      Nicola Kareh
CS230:     Section 8
Data:      Farmers Markets Directory
URL:       Not Deployed
Description:
This app explores the Farmers Markets Directory dataset. The user can filter markets
by state, city, SNAP/EBT availability, indoor vs outdoor, accepted payment types, and
market name. The app shows summary metrics, a few charts, a filtered data table, and
a PyDeck map with hover tooltips. The point is to look at where farmers markets show
up across the country and how accessible they are based on payment options and food
assistance programs.
"""

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import pydeck as pdk

# ============================================================
# PAGE SETUP
# ============================================================

st.set_page_config(
    page_title="Farmers Markets Explorer",
    page_icon="🌽",
    layout="wide",
    initial_sidebar_state="expanded"
)

# [ST4] Custom page styling — fonts, colors, layout boxes, tabs, sidebar
st.markdown(
    """
    <style>
    .main-title {
        font-size: 42px;
        font-weight: 800;
        color: #4caf50;
        margin-bottom: 0px;
    }

    .subtitle {
        font-size: 20px;
        color: #888888;
        margin-top: 0px;
        margin-bottom: 20px;
    }

    .story-box {
        background-color: #ffffff;
        border-left: 6px solid #4caf50;
        padding: 16px 20px;
        border-radius: 10px;
        margin-bottom: 18px;
        font-size: 16px;
        line-height: 1.6;
        color: #1f1f1f;
    }

    .section-note {
        background-color: #ffffff;
        border-left: 5px solid #4caf50;
        padding: 12px 16px;
        border-radius: 8px;
        margin-bottom: 16px;
        font-size: 15px;
        line-height: 1.5;
        color: #1f1f1f;
    }

    .small-note {
        color: #888888;
        font-size: 14px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# ============================================================
# DICTIONARIES AND CONSTANTS
# ============================================================

# [PY5] Dictionary used to convert state abbreviations into full state names
STATE_ABBR_TO_NAME = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
    "PR": "Puerto Rico"
}

# Pre-built sets used when checking whether a state value is valid
VALID_STATE_NAMES = set(STATE_ABBR_TO_NAME.values())
VALID_STATE_ABBRS = set(STATE_ABBR_TO_NAME.keys())

# [PY5] Second dictionary — maps user-facing payment label to the keyword in the raw CSV
PAYMENT_KEYWORDS = {
    "Credit/Debit": "Debit card/Credit card",
    "Cash": "Cash",
    "Check": "Check",
    "SNAP": "SNAP",
    "WIC": "WIC",
    "Senior FMNP": "Senior Farmers Market Nutrition Program"
}

# ============================================================
# DATA FUNCTIONS
# ============================================================

def load_data(file_name):
    """
    Read the farmers market CSV. Some of the rows have characters that don't decode
    as UTF-8, so latin1 is used as a fallback.
    """
    # [PY3] Error checking with try/except
    try:
        return pd.read_csv(file_name, encoding="utf-8")
    except UnicodeDecodeError:
        return pd.read_csv(file_name, encoding="latin1")
    except FileNotFoundError:
        st.error(f"Could not find {file_name}. Make sure it's in the same folder as app.py.")
        st.stop()
    except Exception as error:
        st.error(f"The file could not be loaded. Error: {error}")
        st.stop()


def normalize_state(value):
    """
    Take a state value from the raw data and return the full state name.
    Handles both abbreviations ('MA') and full names ('Massachusetts'), and returns
    NaN if the value doesn't match anything.
    """
    if pd.isna(value):
        return np.nan

    state = str(value).strip()
    state_upper = state.upper()
    state_title = state.title()

    # Dictionary key access — convert abbreviation to full name
    if state_upper in VALID_STATE_ABBRS:
        return STATE_ABBR_TO_NAME[state_upper]

    if state_title in VALID_STATE_NAMES:
        return state_title

    return np.nan


def yes_no_from_text(value, keyword):
    """
    Check whether a keyword appears inside a messy text column. Used for
    parsing the payment and food-assistance fields, which are stored as
    free-form strings in the CSV.
    """
    if pd.isna(value):
        return False

    return keyword.lower() in str(value).lower()


# [PY1] Function with two parameters, one with a default value
# [PY2] Function that returns more than one value (returns 7 values as a tuple)
def summarize_markets(dataframe, location_label="Current selection"):
    """
    Build the summary numbers shown at the top of the page (total markets,
    state/city counts, SNAP rate, etc.) and a one-sentence overview string.
    """
    total_markets = len(dataframe)
    unique_states = dataframe["state_clean"].nunique()
    unique_cities = dataframe["city_clean"].nunique()
    coordinate_count = int(dataframe["has_coordinates"].sum())

    if total_markets > 0:
        snap_rate = round(dataframe["accepts_snap"].mean() * 100, 1)
        indoor_rate = round(dataframe["is_indoor_anytime"].mean() * 100, 1)
    else:
        snap_rate = 0.0
        indoor_rate = 0.0

    sentence = (
        f"{location_label} contains {total_markets:,} farmers markets across "
        f"{unique_cities:,} cities and {unique_states:,} states. "
        f"{snap_rate}% of these markets mention SNAP/EBT access."
    )

    return total_markets, unique_states, unique_cities, coordinate_count, snap_rate, indoor_rate, sentence


def clean_data(df):
    """
    Run all the cleaning steps on the raw dataframe: fill missing columns,
    standardize state names, parse coordinates, and build the boolean
    payment/access columns the rest of the app relies on.
    """
    # [DA1] Clean and manipulate raw data
    cleaned = df.copy()

    needed_columns = [
        "listing_name", "location_address", "location_site", "location_indoor",
        "acceptedpayment", "FNAP", "SNAP_option", "specialproductionmethods",
        "Parsed_City", "Parsed_State", "Parsed_Zip", "location_x", "location_y"
    ]

    for col in needed_columns:
        if col not in cleaned.columns:
            cleaned[col] = np.nan

    text_columns = [
        "listing_name", "location_address", "location_site", "location_indoor",
        "acceptedpayment", "FNAP", "SNAP_option", "specialproductionmethods",
        "Parsed_City", "Parsed_State", "Parsed_Zip"
    ]

    for col in text_columns:
        cleaned[col] = cleaned[col].fillna("").astype(str).str.strip()

    # [DA7] Add/create new cleaned columns for city, state, zip
    cleaned["city_clean"] = cleaned["Parsed_City"].replace("", np.nan).str.title()
    cleaned["state_clean"] = cleaned["Parsed_State"].apply(normalize_state)
    cleaned["zip_clean"] = cleaned["Parsed_Zip"].replace("", np.nan)

    cleaned["longitude"] = pd.to_numeric(cleaned["location_x"], errors="coerce")
    cleaned["latitude"] = pd.to_numeric(cleaned["location_y"], errors="coerce")

    cleaned.loc[~cleaned["latitude"].between(15, 75), "latitude"] = np.nan
    cleaned.loc[~cleaned["longitude"].between(-180, -50), "longitude"] = np.nan

    # [DA9] Calculated column based on values in other columns
    cleaned["has_coordinates"] = cleaned["latitude"].notna() & cleaned["longitude"].notna()

    cleaned["accepts_snap"] = (
        cleaned["FNAP"].apply(lambda x: yes_no_from_text(x, "SNAP"))
        | cleaned["SNAP_option"].apply(lambda x: len(x.strip()) > 0)
    )

    cleaned["accepts_wic"] = cleaned["FNAP"].apply(lambda x: yes_no_from_text(x, "WIC"))

    cleaned["accepts_senior_fmnp"] = cleaned["FNAP"].apply(
        lambda x: yes_no_from_text(x, "Senior Farmers Market Nutrition Program")
    )

    cleaned["accepts_credit_debit"] = cleaned["acceptedpayment"].apply(
        lambda x: yes_no_from_text(x, "Debit card/Credit card")
    )

    cleaned["accepts_cash"] = cleaned["acceptedpayment"].apply(
        lambda x: yes_no_from_text(x, "Cash")
    )

    cleaned["accepts_check"] = cleaned["acceptedpayment"].apply(
        lambda x: yes_no_from_text(x, "Check")
    )

    cleaned["is_indoor_anytime"] = (
        cleaned["location_indoor"].str.lower().str.contains("indoor")
        & ~cleaned["location_indoor"].str.lower().str.startswith("no")
    )

    # [PY4] List comprehension — find any columns that look like specialproductionmethods
    special_columns = [
        col for col in cleaned.columns
        if col.lower().startswith("specialproductionmethods")
    ]

    if len(special_columns) > 0:
        cleaned["special_method_count"] = cleaned[special_columns].replace("", np.nan).notna().sum(axis=1)
    else:
        cleaned["special_method_count"] = 0

    # [DA8] Iterate through rows of a DataFrame with iterrows()
    market_labels = []
    for index, row in cleaned.iterrows():
        city = row["city_clean"] if pd.notna(row["city_clean"]) else "Unknown City"
        state = row["state_clean"] if pd.notna(row["state_clean"]) else "Unknown State"
        label = f"{row['listing_name']} — {city}, {state}"
        market_labels.append(label)

    cleaned["market_label"] = market_labels

    cleaned = cleaned.dropna(subset=["state_clean"])

    return cleaned


def top_counts(dataframe, group_col, count_name="markets", top_n=10):
    """
    Group the dataframe by a column, count rows, and return the top N as a
    tidy little dataframe ready to plot.
    """
    # [DA2] Sort data in descending order
    # [DA3] Find top N largest values of a column
    grouped = (
        dataframe.groupby(group_col)
        .size()
        .reset_index(name=count_name)
        .sort_values(count_name, ascending=False)
        .head(top_n)
    )

    return grouped


def build_payment_summary(dataframe):
    """
    Count how many markets accept each payment / assistance option.
    Some options (SNAP, WIC, Senior FMNP) come from the boolean columns we
    already built; the rest are pulled directly from the acceptedpayment text.
    """
    rows = []

    # Dictionary items access — iterate over PAYMENT_KEYWORDS
    for readable_name, raw_keyword in PAYMENT_KEYWORDS.items():
        if readable_name == "SNAP":
            count = int(dataframe["accepts_snap"].sum())
        elif readable_name == "WIC":
            count = int(dataframe["accepts_wic"].sum())
        elif readable_name == "Senior FMNP":
            count = int(dataframe["accepts_senior_fmnp"].sum())
        else:
            count = int(
                dataframe["acceptedpayment"].apply(
                    lambda x: yes_no_from_text(x, raw_keyword)
                ).sum()
            )

        rows.append({"option": readable_name, "markets": count})

    payment_summary = pd.DataFrame(rows).sort_values("markets", ascending=False)

    return payment_summary

# ============================================================
# CHART FUNCTIONS
# ============================================================

def make_bar_chart(dataframe, x_col, y_col, title, x_label, y_label, color="#2e7d32"):
    """Vertical bar chart with title, axis labels, and a legend entry."""
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(dataframe[x_col], dataframe[y_col], color=color, label=y_label)
    ax.set_title(title, fontsize=15, fontweight="bold")
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    plt.xticks(rotation=45, ha="right")
    fig.tight_layout()
    return fig


def make_horizontal_bar_chart(dataframe, x_col, y_col, title, x_label, y_label, color="#1565c0"):
    """Horizontal bar chart — used when category labels are long."""
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.barh(dataframe[y_col], dataframe[x_col], color=color, label=x_label)
    ax.set_title(title, fontsize=15, fontweight="bold")
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.grid(axis="x", alpha=0.25)
    ax.legend()
    ax.invert_yaxis()
    fig.tight_layout()
    return fig


def make_snap_pie_chart(dataframe):
    """Two-slice pie showing how many markets list SNAP/EBT vs how many don't."""
    snap_yes = int(dataframe["accepts_snap"].sum())
    snap_no = int(len(dataframe) - snap_yes)

    fig, ax = plt.subplots(figsize=(4, 4))
    ax.pie(
        [snap_yes, snap_no],
        labels=["Mentions SNAP/EBT", "No SNAP/EBT listed"],
        autopct="%1.1f%%",
        startangle=90,
        colors=["#2e7d32", "#bdbdbd"],
        wedgeprops={"edgecolor": "white", "linewidth": 1},
        textprops={"fontsize": 10}
    )
    ax.set_title("SNAP/EBT Availability", fontsize=13, fontweight="bold")
    fig.tight_layout()
    return fig


def make_market_map(dataframe):
    """
    Build the PyDeck scatter map. Uses a Carto basemap URL instead of a
    mapbox:// style so it works without a Mapbox token.
    """
    map_data = dataframe.dropna(subset=["latitude", "longitude"]).copy()

    if map_data.empty:
        return None

    if len(map_data) > 2500:
        map_data = map_data.sample(2500, random_state=230)

    map_data["snap_color"] = map_data["accepts_snap"].apply(
        lambda x: [46, 125, 50, 180] if x else [120, 120, 120, 140]
    )

    center_lat = map_data["latitude"].mean()
    center_lon = map_data["longitude"].mean()

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_data,
        get_position="[longitude, latitude]",
        get_radius=3500,
        get_fill_color="snap_color",
        pickable=True,
        auto_highlight=True
    )

    tooltip = {
        "html": """
        <b>{listing_name}</b><br/>
        <b>Address:</b> {location_address}<br/>
        <b>City:</b> {city_clean}<br/>
        <b>State:</b> {state_clean}<br/>
        <b>SNAP/EBT:</b> {accepts_snap}<br/>
        <b>Credit/Debit:</b> {accepts_credit_debit}
        """,
        "style": {
            "backgroundColor": "#245c3c",
            "color": "white",
            "fontSize": "12px"
        }
    }

    if map_data["state_clean"].nunique() == 1:
        zoom_level = 6
    else:
        zoom_level = 3

    view_state = pdk.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=zoom_level,
        pitch=0
    )

    deck = pdk.Deck(
        initial_view_state=view_state,
        layers=[layer],
        tooltip=tooltip,
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
    )

    return deck


def make_density_heatmap(dataframe):
    """
    PyDeck HeatmapLayer showing where markets are concentrated geographically.
    Different from the scatter map — instead of one dot per market, this aggregates
    nearby points into a continuous density gradient. Best for spotting clusters.
    """
    map_data = dataframe.dropna(subset=["latitude", "longitude"]).copy()

    if map_data.empty:
        return None

    center_lat = map_data["latitude"].mean()
    center_lon = map_data["longitude"].mean()

    layer = pdk.Layer(
        "HeatmapLayer",
        data=map_data,
        get_position="[longitude, latitude]",
        aggregation="MEAN",
        opacity=0.8,
        threshold=0.05,
        intensity=1.2,
        radius_pixels=40
    )

    if map_data["state_clean"].nunique() == 1:
        zoom_level = 6
    else:
        zoom_level = 3

    view_state = pdk.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=zoom_level,
        pitch=0
    )

    deck = pdk.Deck(
        initial_view_state=view_state,
        layers=[layer],
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
    )

    return deck

# ============================================================
# LOAD DATA
# ============================================================

raw_df = load_data("farmersmarket_2026.csv")
df = clean_data(raw_df)

# Calling summarize_markets twice — once with default location_label, once without
overall_summary = summarize_markets(df)
massachusetts_summary = summarize_markets(
    df[df["state_clean"] == "Massachusetts"],
    location_label="Massachusetts"
)


# ============================================================
# MAIN HEADER
# ============================================================

st.markdown('<div class="main-title">Farmers Markets Explorer</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="subtitle">A look at where farmers markets are located across the US and how accessible they are.</div>',
    unsafe_allow_html=True
)

st.markdown(
    """
    <div class="story-box">
    This app looks at farmers markets across the country — where they're concentrated,
    which areas have more options, and how accessible they are through SNAP/EBT, WIC,
    senior nutrition programs, and the payment types they accept. Each tab below has
    its own filters, so you can explore one question at a time.
    </div>
    """,
    unsafe_allow_html=True
)


# ============================================================
# TOP-LEVEL SUMMARY METRICS (whole dataset)
# ============================================================

total_markets, unique_states, unique_cities, coordinate_count, snap_rate, indoor_rate, summary_sentence = summarize_markets(
    df,
    location_label="The full dataset"
)

metric_col1, metric_col2, metric_col3, metric_col4, metric_col5 = st.columns(5)
metric_col1.metric("Markets", f"{total_markets:,}")
metric_col2.metric("States", f"{unique_states:,}")
metric_col3.metric("Cities", f"{unique_cities:,}")
metric_col4.metric("SNAP/EBT", f"{snap_rate}%")
metric_col5.metric("Mapped points", f"{coordinate_count:,}")

st.write(summary_sentence)


# ============================================================
# TABS
# ============================================================

tab_overview, tab_access, tab_map, tab_data, tab_about = st.tabs(
    [
        "1. Overview",
        "2. Access & Payments",
        "3. Map",
        "4. Data Table",
        "5. About the Project"
    ]
)


# ============================================================
# TAB 1: OVERVIEW — multi-state selector + top-N slider
# ============================================================

with tab_overview:
    st.header("1. Where are farmers markets most common?")

    st.markdown(
        """
        <div class="section-note">
        Pick one or more states to see the cities with the most markets. Leave it
        empty to see how the entire country breaks down by state.
        </div>
        """,
        unsafe_allow_html=True
    )

    overview_filter_col1, overview_filter_col2 = st.columns([1.5, 1])

    with overview_filter_col1:
        all_states = sorted(df["state_clean"].dropna().unique())
        # [ST1] Streamlit multiselect widget
        overview_states = st.multiselect(
            "States",
            all_states,
            default=[],
            key="overview_states"
        )

    with overview_filter_col2:
        overview_top_n = st.slider(
            "How many to show",
            min_value=5, max_value=25, value=10, step=1,
            key="overview_top_n"
        )

    if len(overview_states) == 0:
        overview_df = df.copy()
        showing_states_view = True
    else:
        # [DA4] Filter data by one condition (state is in the selected list)
        overview_df = df[df["state_clean"].isin(overview_states)].copy()
        showing_states_view = False

    if overview_df.empty:
        st.warning("No markets in this selection.")
    else:
        overview_col1, overview_col2 = st.columns([1.25, 1])

        with overview_col1:
            if showing_states_view:
                top_geo = top_counts(overview_df, "state_clean", top_n=overview_top_n)
                top_geo = top_geo.rename(columns={
                    "state_clean": "State",
                    "markets": "Markets"
                })

                fig1 = make_bar_chart(
                    top_geo,
                    x_col="State",
                    y_col="Markets",
                    title=f"Top {overview_top_n} States by Number of Farmers Markets",
                    x_label="State",
                    y_label="Number of Markets",
                    color="#2e7d32"
                )
            else:
                # Build "City, ST" labels using the dictionary in reverse to keep
                # cities with the same name across states distinguishable
                overview_df["city_state_label"] = (
                    overview_df["city_clean"].fillna("Unknown") + ", " +
                    overview_df["state_clean"].map(
                        {v: k for k, v in STATE_ABBR_TO_NAME.items()}
                    ).fillna("--")
                )

                top_geo = top_counts(
                    overview_df, "city_state_label", top_n=overview_top_n
                )
                top_geo = top_geo.rename(columns={
                    "city_state_label": "City",
                    "markets": "Markets"
                })

                if len(overview_states) == 1:
                    title_suffix = overview_states[0]
                elif len(overview_states) == 2:
                    title_suffix = " & ".join(overview_states)
                else:
                    title_suffix = f"{len(overview_states)} Selected States"

                fig1 = make_bar_chart(
                    top_geo,
                    x_col="City",
                    y_col="Markets",
                    title=f"Top {overview_top_n} Cities in {title_suffix}",
                    x_label="City",
                    y_label="Number of Markets",
                    color="#2e7d32"
                )

            # [VIZ1] First chart with title, color, axis labels, and legend
            st.pyplot(fig1)

        with overview_col2:
            st.subheader("Top Locations")
            st.dataframe(top_geo, use_container_width=True, hide_index=True)


# ============================================================
# TAB 2: ACCESS & PAYMENTS — state selector + payment multiselect
# ============================================================

with tab_access:
    st.header("2. How Accessible Are These Markets?")

    st.markdown(
        """
        <div class="section-note">
        Markets are easier to use when they accept SNAP/EBT, WIC, senior nutrition
        benefits, or flexible payment options. Filter to a specific state or to
        markets that accept particular payment types.
        </div>
        """,
        unsafe_allow_html=True
    )

    access_filter_col1, access_filter_col2 = st.columns([1, 2])

    with access_filter_col1:
        access_state = st.selectbox(
            "State",
            ["All States"] + sorted(df["state_clean"].dropna().unique()),
            key="access_state"
        )

    with access_filter_col2:
        access_payments = st.multiselect(
            "Only show markets that accept...",
            ["Credit/Debit", "Cash", "Check", "WIC", "Senior FMNP"],
            default=[],
            key="access_payments"
        )

    if access_state == "All States":
        access_df = df.copy()
    else:
        access_df = df[df["state_clean"] == access_state].copy()

    # [DA5] Filter data by two or more conditions combined with OR
    if len(access_payments) > 0:
        payment_mask = pd.Series(False, index=access_df.index)
        if "Credit/Debit" in access_payments:
            payment_mask = payment_mask | access_df["accepts_credit_debit"]
        if "Cash" in access_payments:
            payment_mask = payment_mask | access_df["accepts_cash"]
        if "Check" in access_payments:
            payment_mask = payment_mask | access_df["accepts_check"]
        if "WIC" in access_payments:
            payment_mask = payment_mask | access_df["accepts_wic"]
        if "Senior FMNP" in access_payments:
            payment_mask = payment_mask | access_df["accepts_senior_fmnp"]
        access_df = access_df[payment_mask]

    if access_df.empty:
        st.warning("No markets match these filters.")
    else:
        pie_col, image_col = st.columns([1, 1])

        with pie_col:
            fig2 = make_snap_pie_chart(access_df)
            # [VIZ2] Pie chart with title, custom colors, and labels
            st.pyplot(fig2, use_container_width=True)

        with image_col:
            st.image("snap.png", use_container_width=True)

        st.subheader("State-by-State Breakdown")

        # [DA6] Pivot table — counts of SNAP, credit/debit, and indoor markets per state
        state_pivot = pd.pivot_table(
            access_df,
            index="state_clean",
            values=["accepts_snap", "accepts_credit_debit", "is_indoor_anytime"],
            aggfunc="sum"
        )

        market_counts = access_df.groupby("state_clean").size().rename("total_markets")
        state_pivot = state_pivot.join(market_counts)

        state_pivot["snap_percent"] = np.where(
            state_pivot["total_markets"] > 0,
            (state_pivot["accepts_snap"] / state_pivot["total_markets"] * 100).round(1),
            0
        )

        state_pivot = state_pivot.reset_index().sort_values(
            "snap_percent", ascending=False
        )

        display_pivot = state_pivot.rename(columns={
            "state_clean": "State",
            "accepts_snap": "SNAP Markets",
            "accepts_credit_debit": "Credit/Debit Markets",
            "is_indoor_anytime": "Indoor Markets",
            "total_markets": "Total Markets",
            "snap_percent": "SNAP %"
        })

        st.dataframe(
            display_pivot.head(10),
            use_container_width=True,
            hide_index=True
        )

        pivot_plot = state_pivot.head(10).rename(columns={
            "state_clean": "State",
            "snap_percent": "SNAP %"
        })

        fig3 = make_bar_chart(
            pivot_plot,
            x_col="State",
            y_col="SNAP %",
            title="SNAP/EBT Percentage for Top 10 States",
            x_label="State",
            y_label="Percent of Markets",
            color="#ef6c00"
        )
        # [VIZ3] Third chart with title, color, axis labels, and legend
        st.pyplot(fig3)

# ============================================================
# TAB 3: MAP — state selector + SNAP-only checkbox + heatmap
# ============================================================

with tab_map:
    st.header("3. Where Are These Markets Located?")

    st.markdown(
        """
        <div class="section-note">
        Two views of the same data. The first shows individual markets — green dots
        accept SNAP/EBT, gray dots don't. The second is a heatmap of overall
        density, where brighter areas mean more markets in close proximity.
        </div>
        """,
        unsafe_allow_html=True
    )

    map_filter_col1, map_filter_col2 = st.columns([1, 1])

    with map_filter_col1:
        map_state = st.selectbox(
            "State",
            ["All States"] + sorted(df["state_clean"].dropna().unique()),
            key="map_state"
        )

    with map_filter_col2:
        # [ST3] Streamlit checkbox widget
        map_snap_only = st.checkbox(
            "Show only markets with SNAP/EBT",
            key="map_snap_only"
        )

    if map_state == "All States":
        map_df = df.copy()
    else:
        map_df = df[df["state_clean"] == map_state].copy()

    if map_snap_only:
        map_df = map_df[map_df["accepts_snap"]]

    map_df = map_df[map_df["has_coordinates"]].copy()

    if map_df.empty:
        st.warning("No mappable markets match these filters.")
    else:
        st.write(f"Mapping {len(map_df):,} markets with valid coordinates.")

        st.subheader("Individual Markets")
        market_map = make_market_map(map_df)

        if market_map is None:
            st.warning("The map couldn't be created from this selection.")
        else:
            # [MAP] PyDeck scatter map with custom dots, colors, and hover tooltips
            st.pydeck_chart(market_map, use_container_width=True)

        st.caption("Green = SNAP/EBT listed. Gray = SNAP/EBT not listed.")

        st.subheader("Market Density")
        density_map = make_density_heatmap(map_df)

        if density_map is None:
            st.warning("The heatmap couldn't be created from this selection.")
        else:
            # [MAP] Second PyDeck map using HeatmapLayer for density visualization
            st.pydeck_chart(density_map, use_container_width=True)

        st.caption(
            "Brighter areas = more markets clustered together. "
            "Useful for spotting regional hotspots versus rural gaps."
        )

# ============================================================
# TAB 4: DATA TABLE — state selector + city selector + name search
# ============================================================

with tab_data:
    st.header("4. Browse the Full Table")

    st.markdown(
        """
        <div class="section-note">
        The full filtered list of markets, sorted by state, city, and name. Use
        the search box to find a specific market by name. The chart above the
        table updates as you filter.
        </div>
        """,
        unsafe_allow_html=True
    )

    data_filter_col1, data_filter_col2, data_filter_col3 = st.columns([1, 1, 1.5])

    with data_filter_col1:
        data_state = st.selectbox(
            "State",
            ["All States"] + sorted(df["state_clean"].dropna().unique()),
            key="data_state"
        )

    if data_state == "All States":
        data_state_df = df.copy()
    else:
        data_state_df = df[df["state_clean"] == data_state].copy()

    with data_filter_col2:
        # [ST2] Streamlit selectbox widget
        data_city = st.selectbox(
            "City",
            ["All Cities"] + sorted(data_state_df["city_clean"].dropna().unique()),
            key="data_city"
        )

    with data_filter_col3:
        data_search = st.text_input("Search by market name", key="data_search")

    table_df = data_state_df.copy()

    if data_city != "All Cities":
        table_df = table_df[table_df["city_clean"] == data_city]

    if data_search.strip() != "":
        table_df = table_df[
            table_df["listing_name"].str.contains(data_search.strip(), case=False, na=False)
        ]

    if table_df.empty:
        st.warning("No markets match these filters.")
    else:
        st.caption(f"Showing {len(table_df):,} markets matching the current filters.")

        if table_df["city_clean"].nunique() > 1:
            top_cities_filtered = top_counts(
                table_df, "city_clean", top_n=10
            ).rename(columns={
                "city_clean": "City",
                "markets": "Markets"
            })

            fig5 = make_horizontal_bar_chart(
                top_cities_filtered,
                x_col="Markets",
                y_col="City",
                title="Top Cities in Current Selection",
                x_label="Number of Markets",
                y_label="City",
                color="#2e7d32"
            )
            # [VIZ4] Horizontal bar chart with title, color, axis labels, and legend
            st.pyplot(fig5)

        display_columns = [
            "listing_name", "city_clean", "state_clean", "location_address",
            "accepts_snap", "accepts_wic", "accepts_senior_fmnp",
            "accepts_credit_debit", "accepts_cash", "accepts_check",
            "location_indoor", "latitude", "longitude"
        ]
        display_columns = [col for col in display_columns if col in table_df.columns]

        sorted_table = table_df[display_columns].sort_values(
            by=["state_clean", "city_clean", "listing_name"],
            ascending=[True, True, True]
        )

        column_renames = {
            "listing_name": "Market Name",
            "city_clean": "City",
            "state_clean": "State",
            "location_address": "Address",
            "accepts_snap": "SNAP",
            "accepts_wic": "WIC",
            "accepts_senior_fmnp": "Senior FMNP",
            "accepts_credit_debit": "Credit/Debit",
            "accepts_cash": "Cash",
            "accepts_check": "Check",
            "location_indoor": "Indoor?",
            "latitude": "Latitude",
            "longitude": "Longitude"
        }

        display_table = sorted_table.rename(columns=column_renames)

        st.dataframe(display_table, use_container_width=True, hide_index=True)

        csv_data = sorted_table.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download as CSV",
            data=csv_data,
            file_name="filtered_farmers_markets.csv",
            mime="text/csv"
        )

# ============================================================
# TAB 5: ABOUT THE PROJECT
# ============================================================

with tab_about:
    st.header("5. About This Project")

    st.image("fm.png", use_container_width=True)

    st.markdown(
        """
        ### What this is

        Farmers markets sit at an interesting intersection. They're partly
        about food — fresh produce, local growers, the kind of stuff you can't
        get at a regular grocery store. But they're also part of a much bigger
        question about **food access**: who can actually shop there, and who
        can't? A market that only takes credit cards is functionally closed
        off to anyone using SNAP, WIC, or senior nutrition benefits, even if
        it's right down the street.

        This app is a tool for digging into that question using the USDA's
        Farmers Markets Directory — a public dataset listing thousands of
        markets across the country with information on where they are, what
        forms of payment they accept, and which assistance programs they
        participate in.

        ### What you can do here

        The app is split into four explorable tabs. The first answers
        *where are markets concentrated?* — by state, or by the cities
        within whichever states you pick. The second focuses on
        *how accessible are they?* — SNAP/EBT availability, payment
        flexibility, and how those rates vary state by state. The third
        is the map view, with two ways of looking at the same geography:
        individual market locations color-coded by SNAP status, and a
        density heatmap that surfaces regional clusters and gaps. The
        fourth is the raw data, filterable down to a specific city or
        market name.

        ### Why it matters

        The dataset isn't perfect — some states have much more complete
        records than others, and "doesn't list SNAP" doesn't always mean
        "doesn't accept SNAP." But even with those caveats, you can see
        real patterns: certain regions cluster densely with markets, others
        have almost none. SNAP acceptance rates swing wildly by state.
        Cities with strong public market traditions look completely different
        from the rest of the country.

        Whether or not those patterns translate to *actual* food access on
        the ground is a bigger question this app can't answer on its own.
        But it's a starting point — somewhere to look, before going to ask
        better questions.
        """
    )

    st.caption("Data source: USDA Farmers Markets Directory.")