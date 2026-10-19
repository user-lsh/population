
import io
import json
import re
import zipfile

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

st.set_page_config(page_title="전국 고령화 단계구분도", layout="wide")
st.title("전국 고령화 단계구분도")
st.caption("2026년 6월 읍·면·동 인구를 시군구별로 합산한 65세 이상 인구 비율")

# GitHub의 /blob/ 링크가 아니라 원본(raw) 파일 주소를 사용합니다.
DATA_URL = "https://raw.githubusercontent.com/user-lsh/population/main/population_ts_yearly_gender.zip"
GEOJSON_URL = "https://raw.githubusercontent.com/user-lsh/population/main/sigungu_kr.geojson.txt"


def normalize_code(series, digits=5):
    """코드를 문자열로 유지하고, 앞의 5자리 시군구 코드를 얻습니다."""
    return (
        series.astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(digits)
        .str.slice(0, digits)
    )


@st.cache_data(show_spinner="2026년 인구 데이터를 불러오는 중...")
def load_population():
    response = requests.get(DATA_URL, timeout=120)
    response.raise_for_status()

    # ZIP 안에 CSV가 하나 이상 있어도 첫 번째 CSV를 읽습니다.
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if not csv_names:
            raise ValueError("압축 파일 안에서 CSV 파일을 찾지 못했습니다.")
        csv_bytes = archive.read(csv_names[0])

    df = None
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            df = pd.read_csv(
                io.BytesIO(csv_bytes),
                encoding=encoding,
                low_memory=False,
                dtype={"코드": "string"},
            )
            break
        except UnicodeDecodeError:
            continue

    if df is None:
        raise ValueError("CSV 문자 인코딩을 확인해 주세요.")

    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.replace("\ufeff", "", regex=False)
    )

    required = {"연도", "코드"}
    if not required.issubset(df.columns):
        raise ValueError(
            f"필수 열이 없습니다: {sorted(required - set(df.columns))}"
        )

    # '2026', 2026, '2026년' 표기를 모두 허용합니다.
    years = df["연도"].astype("string").str.extract(
        r"(\d{4})", expand=False
    )
    df = df.loc[years.eq("2026")].copy()

    if df.empty:
        raise ValueError("2026년 인구 데이터가 없습니다.")

    # 전체 인구는 '계_'로 시작하는 모든 열을 사용합니다.
    age_columns = [
        c for c in df.columns if c.startswith("계_")
    ]

    # 65세 이상 인구를 계산할 열
    elderly_columns = [
        c for c in age_columns
        if re.fullmatch(r"계_\d+세(?: 이상)?", c)
        and int(re.search(r"\d+", c).group()) >= 65
    ]

    if not age_columns or not elderly_columns:
        raise ValueError(
            "'계_0세' ~ '계_100세 이상' 형식의 인구 열을 찾지 못했습니다."
        )

    # 남_ / 여_ 열은 중복 계산을 피하기 위해 사용하지 않습니다.
    numeric_ages = df[age_columns].apply(
        lambda col: pd.to_numeric(
            col.astype("string")
            .str.replace(",", "", regex=False)
            .str.strip(),
            errors="coerce",
        )
    ).fillna(0)

    df["전체인구"] = numeric_ages.sum(axis=1)
    df["고령인구"] = numeric_ages[elderly_columns].sum(axis=1)

    # 동 코드 앞 5자리 추출
    df["시군구코드"] = normalize_code(df["코드"])

    # 시군구별 인구 합산
    result = (
        df.groupby("시군구코드", as_index=False)[
            ["전체인구", "고령인구"]
        ]
        .sum()
    )

    # 시군구별 고령화율 계산
    result["고령화율"] = np.where(
        result["전체인구"] > 0,
        result["고령인구"] / result["전체인구"] * 100,
        np.nan,
    )

    return result


@st.cache_data(show_spinner="시군구 경계를 불러오는 중...")
def load_geojson():
    response = requests.get(GEOJSON_URL, timeout=90)
    response.raise_for_status()

    geojson = response.json()
    features = geojson.get("features", [])

    if not features:
        raise ValueError(
            "GeoJSON에 시군구 경계(features)가 없습니다."
        )

    for feature in features:
        props = feature.get("properties") or {}

        props["코드"] = (
            str(props.get("코드", ""))
            .strip()
            .removesuffix(".0")
            .zfill(5)[:5]
        )

        feature["properties"] = props

    return geojson


try:
    population = load_population()
    geojson = load_geojson()

except Exception as exc:
    st.error(f"데이터 로딩 오류: {exc}")
    st.stop()


# GeoJSON의 코드와 인구 데이터의 코드 연결
names = pd.DataFrame(
    [
        {
            "시군구코드": f["properties"]["코드"],
            "시도": f["properties"].get("시도", ""),
            "시군구": f["properties"].get("시군구", ""),
        }
        for f in geojson["features"]
    ]
).drop_duplicates(subset="시군구코드")

merged = names.merge(
    population,
    on="시군구코드",
    how="left",
    validate="one_to_one",
)

valid = merged.dropna(subset=["고령화율"]).copy()

if valid.empty:
    st.error(
        "인구 데이터와 GeoJSON의 5자리 시군구 코드가 일치하지 않습니다."
    )
    st.stop()


# 전국 고령화율 계산
total_pop = valid["전체인구"].sum()
total_older = valid["고령인구"].sum()

national_rate = (
    total_older / total_pop * 100
    if total_pop > 0
    else np.nan
)


# 상단 지표 카드
m1, m2, m3 = st.columns(3)

m1.metric(
    "전국 65세 이상 비율",
    f"{national_rate:.1f}%"
)

m2.metric(
    "지도에 표시된 시군구",
    f"{len(valid):,}개"
)

m3.metric(
    "자료가 없는 경계",
    f"{len(merged) - len(valid):,}개"
)


# Plotly 전국 고령화 단계구분도
fig = go.Figure(
    go.Choropleth(
        geojson=geojson,
        locations=valid["시군구코드"],
        featureidkey="properties.코드",
        z=valid["고령화율"],
        text=valid["시군구"],
        customdata=valid[["시도"]].to_numpy(),

        # 고령화율이 높을수록 진한 빨간색
        colorscale=[
            [0.0, "#fff5f0"],
            [0.25, "#fcbba1"],
            [0.5, "#fb6a4a"],
            [0.75, "#cb181d"],
            [1.0, "#67000d"],
        ],

        zmin=0,
        zmax=max(
            40,
            float(
                np.ceil(
                    valid["고령화율"].max() / 10
                ) * 10
            )
        ),

        marker_line_color="#ffffff",
        marker_line_width=0.35,

        colorbar=dict(
            title="고령화율 (%)",
            ticksuffix="%"
        ),

        # 마우스를 올렸을 때 표시할 정보
        hovertemplate=(
            "%{customdata[0]} %{text}"
            "<br>고령화율: %{z:.1f}%"
            "<extra></extra>"
        ),
    )
)


# 배경 지도 없이 시군구 경계만 표시
fig.update_geos(
    fitbounds="locations",
    projection_type="mercator",
    visible=False,
    showframe=False,
    showcoastlines=False,
    showland=False,
    showcountries=False,
    showlakes=False,
)


fig.update_layout(
    margin=dict(l=0, r=0, t=10, b=0),
    height=780,
    paper_bgcolor="white",
    geo=dict(bgcolor="white"),
)


st.plotly_chart(
    fig,
    use_container_width=True,
    config={"displaylogo": False},
)

st.caption(
    "색이 진할수록 65세 이상 인구 비율이 높습니다. "
    "배경 지도 타일은 사용하지 않았습니다."
)


# 시군구별 통계표
with st.expander("시군구별 고령화율 표 보기"):

    table = valid[
        [
            "시도",
            "시군구",
            "시군구코드",
            "전체인구",
            "고령인구",
            "고령화율",
        ]
    ].copy()

    table = table.sort_values(
        "고령화율",
        ascending=False
    )

    st.dataframe(
        table.style.format(
            {
                "전체인구": "{:,.0f}",
                "고령인구": "{:,.0f}",
                "고령화율": "{:.2f}%",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
