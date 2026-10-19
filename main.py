
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st

# ----------------------------------------
# 1. 앱 기본 설정
# ----------------------------------------
st.set_page_config(
    page_title="동네별 인구 피라미드",
    page_icon="🏡",
    layout="wide"
)

# 따뜻한 분위기의 화면 디자인
st.markdown("""
<style>
.stApp {
    background-color: #FFF9F3;
}
h1, h2, h3 {
    color: #674B42;
}
div[data-testid="stMetric"] {
    background-color: #FFFFFF;
    border: 1px solid #F0DFD0;
    border-radius: 14px;
    padding: 15px;
}
</style>
""", unsafe_allow_html=True)

st.title("🏡 동네별 인구 피라미드")
st.write(
    "우리 동네에는 어느 나이의 사람들이 많이 살고 있을까요? "
    "지역을 골라 인구 구조를 살펴보세요."
)

# GitHub ZIP 파일의 실제 다운로드 주소
DATA_URL = (
    "https://raw.githubusercontent.com/user-lsh/population/"
    "main/population_ts_yearly_gender.zip"
)


# ----------------------------------------
# 2. 데이터 불러오기
# ----------------------------------------
@st.cache_data(show_spinner="인구 데이터를 불러오는 중이에요...")
def load_data():

    # CSV가 들어 있는 ZIP 파일을 pandas로 바로 읽습니다.
    # 한글 파일에서 사용할 수 있는 인코딩을 순서대로 시도합니다.
    for encoding in ["utf-8-sig", "cp949", "euc-kr"]:
        try:
            df = pd.read_csv(
                DATA_URL,
                compression="zip",
                encoding=encoding,
                low_memory=False
            )
            break
        except UnicodeError:
            continue
    else:
        raise ValueError("CSV 파일의 인코딩을 확인해 주세요.")

    # 열 이름의 앞뒤 공백 제거
    df.columns = df.columns.astype(str).str.strip()

    # 연도를 숫자로 변환
    df["연도"] = pd.to_numeric(
        df["연도"],
        errors="coerce"
    )

    # 데이터에 있는 가장 최신 연도 선택
    latest_year = int(df["연도"].max())

    df = df[df["연도"] == latest_year].copy()

    # 지역 이름 정리
    for col in ["시도", "시군구", "동"]:
        df[col] = df[col].astype("string").str.strip()
        df = df[
            df[col].notna() & (df[col] != "")
        ]

    return df, latest_year


try:
    df, year = load_data()

except Exception as e:
    st.error("데이터를 불러오지 못했어요.")
    st.exception(e)
    st.stop()

st.caption(f"📅 데이터 기준: {year}년")


# ----------------------------------------
# 3. 지역 선택 드롭다운
# ----------------------------------------
st.subheader("📍 지역 선택")

col1, col2, col3 = st.columns(3)

# 첫 번째: 시도 선택
with col1:
    sido = st.selectbox(
        "① 시도",
        sorted(df["시도"].unique().tolist())
    )

# 두 번째: 선택한 시도의 시군구
sido_df = df[df["시도"] == sido]

with col2:
    sigungu = st.selectbox(
        "② 시군구",
        sorted(sido_df["시군구"].unique().tolist())
    )

# 세 번째: 선택한 시군구의 동
sigungu_df = sido_df[
    sido_df["시군구"] == sigungu
]

with col3:
    dong = st.selectbox(
        "③ 동 (읍·면 포함)",
        sorted(sigungu_df["동"].unique().tolist())
    )

# 최종 선택 지역
selected = sigungu_df[
    sigungu_df["동"] == dong
]

if selected.empty:
    st.warning("선택한 지역의 데이터가 없어요.")
    st.stop()


# ----------------------------------------
# 4. 나이별 남녀 인구 데이터 만들기
# ----------------------------------------

# 0세부터 100세 이상까지 총 101개 연령
ages = list(range(101))

age_labels = [
    f"{age}세" for age in range(100)
] + ["100세 이상"]

# CSV의 남녀 인구 열 이름
male_columns = [
    f"남_{label}" for label in age_labels
]

female_columns = [
    f"여_{label}" for label in age_labels
]

# 필요한 열이 있는지 확인
missing_columns = [
    col
    for col in male_columns + female_columns
    if col not in selected.columns
]

if missing_columns:
    st.error(
        "인구 데이터에 필요한 열이 없습니다: "
        + ", ".join(missing_columns[:10])
    )
    st.stop()


# 숫자 형태로 바꾸고 지역별 인구 합계 계산
def get_population(columns):

    values = selected[columns].copy()

    for col in columns:
        values[col] = pd.to_numeric(
            values[col]
            .astype("string")
            .str.replace(",", "", regex=False),
            errors="coerce"
        ).fillna(0)

    return values.sum(axis=0).to_numpy(dtype=int)


male = get_population(male_columns)
female = get_population(female_columns)

# 전체 인구
male_total = int(male.sum())
female_total = int(female.sum())
total = male_total + female_total

# 나이별 남녀 인구 합계
population_by_age = male + female


# ----------------------------------------
# 5. 추가 지표 계산
# ----------------------------------------

# 평균연령: 나이 × 해당 나이 인구수의 합 / 총인구
# 100세 이상은 계산 편의상 100세로 취급합니다.
if total > 0:
    average_age = (
        np.sum(
            np.array(ages) * population_by_age
        ) / total
    )
else:
    average_age = 0

# 65세 이상 인구
elderly_population = int(
    population_by_age[65:].sum()
)

# 0~14세 유소년 인구
child_population = int(
    population_by_age[:15].sum()
)

# 고령화율: 65세 이상 인구 / 총인구 × 100
if total > 0:
    aging_rate = elderly_population / total * 100
else:
    aging_rate = 0


# ----------------------------------------
# 6. 지표 카드 3개
# ----------------------------------------
st.subheader(
    f"🌷 {sido} {sigungu} {dong}의 인구 구조"
)

metric1, metric2, metric3 = st.columns(3)

with metric1:
    st.metric(
        label="👥 총인구",
        value=f"{total:,}명"
    )

with metric2:
    st.metric(
        label="🎂 평균연령",
        value=f"{average_age:.1f}세"
    )

with metric3:

    # 고령화율이 20%를 초과하면 주의 표시
    if aging_rate > 20:
        aging_label = "⚠️ 고령화율"
    else:
        aging_label = "🌿 고령화율"

    st.metric(
        label=aging_label,
        value=f"{aging_rate:.1f}%"
    )

# 고령화율 20% 초과 시 안내 문구
if aging_rate > 20:
    st.warning(
        "⚠️ 이 동네는 65세 이상 인구가 전체의 "
        "20%를 넘는 지역이에요."
    )


# ----------------------------------------
# 7. 인구 피라미드 그래프
# ----------------------------------------
fig = go.Figure()

# 남성 인구는 음수로 바꿔 왼쪽에 표시
fig.add_trace(
    go.Bar(
        x=-male,
        y=ages,
        name="남성",
        orientation="h",
        marker_color="#81AFC2",
        customdata=male,
        hovertemplate=(
            "남성 · %{y}세<br>"
            "%{customdata:,}명"
            "<extra></extra>"
        )
    )
)

# 여성 인구는 양수로 오른쪽에 표시
fig.add_trace(
    go.Bar(
        x=female,
        y=ages,
        name="여성",
        orientation="h",
        marker_color="#EAA5A2",
        customdata=female,
        hovertemplate=(
            "여성 · %{y}세<br>"
            "%{customdata:,}명"
            "<extra></extra>"
        )
    )
)

# 좌우 인구축을 대칭으로 설정
max_population = max(
    int(male.max()),
    int(female.max()),
    1
)

limit = max_population * 1.12

# 인구수 눈금
tick_step = max(1, int(max_population / 3))

x_tick_values = (
    [-tick_step * i for i in range(3, 0, -1)]
    + [0]
    + [tick_step * i for i in range(1, 4)]
)

x_tick_values = [
    value for value in x_tick_values
    if abs(value) <= limit
]

fig.update_layout(
    barmode="relative",
    bargap=0.04,
    height=980,

    paper_bgcolor="#FFF9F3",
    plot_bgcolor="#FFF9F3",

    font=dict(
        color="#5F5049",
        size=13
    ),

    margin=dict(
        l=20,
        r=25,
        t=45,
        b=45
    ),

    legend=dict(
        orientation="h",
        x=0.5,
        xanchor="center",
        y=1.05
    ),

    xaxis=dict(
        title="인구수 (명)",
        range=[-limit, limit],

        tickmode="array",
        tickvals=x_tick_values,

        # 왼쪽의 음수도 양수로 표시
        ticktext=[
            f"{abs(value):,}"
            for value in x_tick_values
        ],

        showgrid=True,
        gridcolor="#EBDDD2",

        zeroline=True,
        zerolinecolor="#8F7A6C"
    ),

    yaxis=dict(
        title="나이",

        # 실제 숫자 나이를 사용
        type="linear",

        # 아래 0세, 위 100세 이상
        range=[-0.5, 100.5],

        # 나이 순서를 직접 고정
        tickmode="array",
        tickvals=ages,
        ticktext=age_labels,

        tickfont=dict(size=9),
        showgrid=False
    )
)

# 세로축 순서 검증
assert ages[0] == 0
assert ages[-1] == 100
assert age_labels[0] == "0세"
assert age_labels[-1] == "100세 이상"

st.plotly_chart(
    fig,
    use_container_width=True
)

st.caption(
    "🔵 남성은 왼쪽, 🌸 여성은 오른쪽에 표시돼요. "
    "나이는 아래에서 위로 높아집니다."
)


# ----------------------------------------
# 8. 우리 동네 인구 특징 자동 설명
# ----------------------------------------
st.subheader(
    "🔎 이 동네는 아이가 많은 편인가요, "
    "어르신이 많은 편인가요?"
)

# 유소년과 고령 인구의 수를 비교해 문장 생성
if total == 0:
    explanation = (
        "이 동네는 인구 데이터가 0명으로 표시되어 "
        "인구 구조를 비교하기 어려워요."
    )

elif child_population > elderly_population:
    explanation = (
        "이 동네는 어르신(65세 이상)보다 "
        "아이(0~14세)가 더 많은 동네예요."
    )

elif child_population < elderly_population:
    explanation = (
        "이 동네는 아이(0~14세)보다 "
        "어르신(65세 이상)이 더 많은 동네예요."
    )

else:
    explanation = (
        "이 동네는 아이(0~14세)와 "
        "어르신(65세 이상)의 인구수가 같아요."
    )

st.info(explanation)
