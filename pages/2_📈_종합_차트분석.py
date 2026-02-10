import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import datetime
import yfinance as yf
import OpenDartReader

st.set_page_config(page_title="종합 차트 분석", page_icon="📈", layout="centered")
st.title("📈 AI 기술적 심층 분석")

# --- 1. DART 전 종목 리스트 (검색용) ---
@st.cache_data(show_spinner=False)
def get_corp_dict():
    api_key = st.session_state.get("api_key")
    if not api_key:
        if "dart_api_key" in st.secrets: api_key = st.secrets["dart_api_key"]
        else: return None
    try:
        dart = OpenDartReader(api_key)
        corp_list = dart.corp_codes
        listed_df = corp_list[corp_list['stock_code'].notnull()]
        return dict(zip(listed_df['corp_name'], listed_df['stock_code']))
    except: return None

# --- 2. 데이터 수집 (가격 정보만 확실하게!) ---
@st.cache_data(ttl=600)
def get_stock_data(user_input, period_days):
    df = pd.DataFrame()
    code = ""
    name = user_input
    source = ""
    
    corp_dict = get_corp_dict()
    
    if user_input.isdigit() and len(user_input) == 6:
        code = user_input
        name = f"Code: {code}"
    elif corp_dict and user_input in corp_dict:
        code = corp_dict[user_input]
        name = user_input
    else:
        try:
            krx = fdr.StockListing('KRX')
            target = krx[krx['Name'] == user_input]
            if target.empty: return None, None, None, f"'{user_input}'을 찾을 수 없습니다."
            code = target.iloc[0]['Code']
            name = user_input
        except: return None, None, None, "검색 실패."

    end_dt = datetime.datetime.now() + datetime.timedelta(days=1)
    start_dt = datetime.datetime.now() - datetime.timedelta(days=period_days*2)
    
    try:
        candidates = [f"{code}.KS", f"{code}.KQ"]
        for ticker in candidates:
            # 펀더멘털 로직 삭제 -> 속도 훨씬 빨라짐
            temp_df = yf.download(ticker, start=start_dt, end=end_dt, progress=False, auto_adjust=True)
            if not temp_df.empty:
                df = temp_df
                source = "Yahoo Finance"
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                break
    except: pass

    if df.empty:
        try:
            df = fdr.DataReader(code, start_dt)
            source = "Naver Finance"
        except: pass
    
    if df.empty: return None, None, None, "데이터 수집 실패."
        
    df = df.dropna()
    if df.index.tz is None: df.index = df.index.tz_localize('UTC').tz_convert('Asia/Seoul')
    else: df.index = df.index.tz_convert('Asia/Seoul')
    df.index = df.index.strftime('%Y-%m-%d')
        
    return df, name, code, source

# --- 3. 지표 계산 ---
def calculate_indicators(df):
    df = df.copy()
    close = df['Close']
    df['MA20'] = close.rolling(20).mean()
    df['MA60'] = close.rolling(60).mean()
    df['std'] = close.rolling(20).std()
    df['Upper'] = df['MA20'] + (df['std'] * 2)
    df['Lower'] = df['MA20'] - (df['std'] * 2)
    df['Vol_MA20'] = df['Volume'].rolling(20).mean()
    delta = close.diff(1)
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    df['Resistance'] = df['High'].rolling(60).max()
    df['Support'] = df['Low'].rolling(60).min()
    return df

# --- 4. 상세 분석 엔진 (여전히 수다쟁이 버전 유지) ---
def analyze_market(df):
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    score = 50
    report = []
    
    # (1) 추세 분석
    if latest['Close'] > latest['MA20']:
        score += 10
        report.append("📈 **[추세]** 주가가 생명선인 20일 이동평균선 위에 안착해 있습니다. 단기 상승 추세가 살아있어 긍정적입니다.")
    else:
        score -= 10
        report.append("📉 **[추세]** 주가가 20일 이동평균선 아래로 처져있습니다. 상승 동력이 약해진 상태라 주의가 필요합니다.")
        
    if latest['MA20'] > latest['MA60']:
        score += 5
        report.append("또한 20일선이 60일선 위에 있는 **정배열** 상태라 중기적인 상승 기조는 유지되고 있습니다.")
    elif latest
