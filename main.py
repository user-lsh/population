
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ----------------------------------------
# 1. 앱의 기본 설정과 화면 디자인
# ----------------------------------------
st.set_page_config(page_title="동네별 인구 피라미드", page_icon="🏡", layout="wide")

st.markdown(
    """
    <style>
    .stApp { background-color: #FFF9F3; }
    h1, h2, h3 { color: #674B42; }
    div[data-testid="stMetric"] {
        background: #FFFFFF;
        border: 1px solid #F0DFD0;
        border-radius: 14px;
        padding: 12px 18px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🏡 동네별 인구 피라미드")
st.write("우리 동네에는 어느 나이의 사람들이 많이 살고 있을까요? 지역을 골라 인구 구조를 살펴보세요.")

# GitHub의 /blob/ 주소는 웹페이지이므로, 판다스에서 직접 읽을 수 있는 원본 주소로 바꿉니다.
DATA_URL = (
    "https://raw.githubusercontent.com/user-lsh/population/"
    "main/population_ts_yearly_gender.zip"
)


# ----------------------------------------
# 2. 데이터 불러오기 (한 번 읽은 데이터는 캐시에 저장)
# ----------------------------------------
@st.cache_data(show_spinner="전국 인구 데이터를 불러오는 중이에요...")
def load_data():
    # ZIP 안에 CSV가 하나 들어 있다면 압축을 직접 풀 필요가 없습니다.
    # 한글 인코딩이 서로 다른 CSV를 대비해 순서대로 읽기를 시도합니다.
    last_error = None
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            data = pd.read_csv(DATA_URL, compression="zip", encoding=encoding, low_memory=False)
            break
        except UnicodeError as error:
            last_error = error
    else:
        raise ValueError("CSV 파일의 문자 인코딩을 확인해 주세요.") from last_error

    # CSV 열 이름에 불필요한 공백이 있으면 제거합니다.
    data.columns = data.columns.astype(str).str.strip()
    required = ["연도", "시도", "시군구", "동"]
    missing = [col for col in required if col not in data.columns]
    if missing:
        raise ValueError(f"필요한 열이 없습니다: {', '.join(missing)}")

    # 연도를 숫자로 변환하고, 실제 데이터에 존재하는 가장 최신 연도만 사용합니다.
    data["연도"] = pd.to_numeric(data["연도"], errors="coerce")
    latest_year = data["연도"].max()
    if pd.isna(latest_year):
        raise ValueError("'연도' 열에서 유효한 연도를 찾을 수 없습니다.")
    data = data.loc[data["연도"] == latest_year].copy()

    # 비어 있는 지역명은 선택 목록에서 제외합니다.
    for col in ("시도", "시군구", "동"):
        data[col] = data[col].astype("string").str.strip()
        data = data.loc[data[col].notna() & data[col].ne("")]

    return data, int(latest_year)


try:
    df, year = load_data()
except Exception as error:
    st.error("데이터를 불러오지 못했어요. GitHub 주소와 ZIP 파일 구성을 확인해 주세요.")
    st.exception(error)
    st.stop()

st.caption(f"📅 데이터 기준: {year}년 · 전국 읍·면·동 인구")

# ----------------------------------------
# 3. 시도 → 시군구 → 동 순서로 선택하기
# ----------------------------------------
st.subheader("📍 지역 선택")
col1, col2, col3 = st.columns(3)

with col1:
    sido = st.selectbox("① 시도", sorted(df["시도"].dropna().unique().tolist()))

# 앞에서 고른 시도에 포함된 시군구만 보여 줍니다.
sido_df = df.loc[df["시도"] == sido]
with col2:
    sigungu = st.selectbox("② 시군구", sorted(sido_df["시군구"].dropna().unique().tolist()))

# 앞에서 고른 시도와 시군구에 포함된 동만 보여 줍니다.
sigungu_df = sido_df.loc[sido_df["시군구"] == sigungu]
with col3:
    dong = st.selectbox("③ 동 (읍·면 포함)", sorted(sigungu_df["동"].dropna().unique().tolist()))

selected = sigungu_df.loc[sigungu_df["동"] == dong]
if selected.empty:
    st.warning("선택한 지역의 데이터가 없습니다.")
    st.stop()

# ----------------------------------------
# 4. 0세부터 100세 이상까지 남녀 인구 꺼내기
# ----------------------------------------
# 숫자 나이를 그대로 세로축에 사용하면 0세는 맨 아래, 100세 이상은 맨 위에 놓입니다.
ages = list(range(101))
age_labels = [f"{age}세" for age in range(100)] + ["100세 이상"]
male_columns = [f"남_{label}" for label in age_labels]
female_columns = [f"여_{label}" for label in age_labels]

missing_population_columns = [
    col for col in male_columns + female_columns if col not in selected.columns
]
if missing_population_columns:
    st.error(f"인구 열이 누락되어 있습니다: {', '.join(missing_population_columns[:8])}")
    st.stop()

# 같은 이름의 행이 여러 개라면 해당 지역 인구를 합칩니다.
# 쉼표가 포함된 숫자도 처리합니다(예: '1,234').
def population_sum(columns):
    values = selected[columns].astype("string").replace({",": ""}, regex=True)
    values = values.apply(pd.to_numeric, errors="coerce").fillna(0)
    return values.sum(axis=0).to_numpy(dtype="int64")

male = population_sum(male_columns)
female = population_sum(female_columns)

male_total = int(male.sum())
female_total = int(female.sum())
total = male_total + female_total

st.subheader(f"🌷 {sido} {sigungu} {dong}의 인구 구조")
m1, m2, m3 = st.columns(3)
m1.metric("전체 인구", f"{total:,}명")
m2.metric("남성 인구", f"{male_total:,}명")
m3.metric("여성 인구", f"{female_total:,}명")

# ----------------------------------------
# 5. Plotly로 인구 피라미드 그리기
# ----------------------------------------
fig = go.Figure()

# 남자는 음수이므로 왼쪽, 여자는 양수이므로 오른쪽에 그려집니다.
# 마우스를 올리면 음수 기호 없이 실제 인구수를 보여 줍니다.
fig.add_trace(
    go.Bar(
        x=-male,
        y=ages,
        orientation="h",
        name="남성",
        marker_color="#81AFC2",
        customdata=male,
        hovertemplate="남성 · %{y}세: %{customdata:,}명<extra></extra>",
    )
)
fig.add_trace(
    go.Bar(
        x=female,
        y=ages,
        orientation="h",
        name="여성",
        marker_color="#EAA5A2",
        customdata=female,
        hovertemplate="여성 · %{y}세: %{customdata:,}명<extra></extra>",
    )
)

# 좌우 비교가 공정하도록 인구수의 최대 범위를 똑같이 설정합니다.
max_population = max(int(male.max()), int(female.max()), 1)
limit = max_population * 1.12

# 왼쪽의 음수 값도 화면 눈금에서는 양수 인구로 표시합니다.
tick_step = max(1, int(max_population / 3))
x_tick_values = [-tick_step * i for i in range(3, 0, -1)] + [0] + [tick_step * i for i in range(1, 4)]
x_tick_values = [x for x in x_tick_values if abs(x) <= limit]

fig.update_layout(
    barmode="relative",
    bargap=0.04,
    height=980,
    margin=dict(l=20, r=25, t=45, b=45),
    paper_bgcolor="#FFF9F3",
    plot_bgcolor="#FFF9F3",
    font=dict(color="#5F5049", size=13),
    legend=dict(orientation="h", x=0.5, xanchor="center", y=1.05),
    xaxis=dict(
        title="인구수 (명)",
        range=[-limit, limit],
        tickmode="array",
        tickvals=x_tick_values,
        ticktext=[f"{abs(value):,}" for value in x_tick_values],
        showgrid=True,
        gridcolor="#EBDDD2",
        zeroline=True,
        zerolinecolor="#8F7A6C",
        zerolinewidth=1,
    ),
    yaxis=dict(
        title="나이",
        type="linear",  # 문자열 정렬 대신 실제 숫자 나이를 사용합니다.
        range=[-0.5, 100.5],  # 아래=0세, 위=100세 이상 (축 뒤집기 없음)
        tickmode="array",  # 나이 라벨의 위치와 순서를 명시적으로 고정합니다.
        tickvals=ages,
        ticktext=age_labels,
        tickfont=dict(size=9),
        showgrid=False,
    ),
)

# 축 방향을 코드에서도 확인합니다: 첫 눈금=0세, 마지막 눈금=100세 이상.
assert ages[0] == 0 and age_labels[0] == "0세"
assert ages[-1] == 100 and age_labels[-1] == "100세 이상"
assert fig.layout.yaxis.range[0] < fig.layout.yaxis.range[1]

st.plotly_chart(fig, use_container_width=True)
st.caption("🔵 남성은 왼쪽, 🌸 여성은 오른쪽입니다. 막대에 마우스를 올리면 나이별 인구를 볼 수 있어요.")
st.caption("나이 축: 맨 아래 0세 → 맨 위 100세 이상 (오름차순 고정)")
