import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import datetime
import yfinance as yf
import OpenDartReader

st.set_page_config(page_title="종합 차트 분석", page_icon="📈", layout="wide")
st.title("📈 종합 기술적 분석 센터 (Full)")

# --- [핵심] DART에서 전 종목 리스트 가져오기 ---
@st.cache_data(show_spinner=False)
def get_corp_dict():
    # API 키 확인
    api_key = st.session_state.get("api_key")
    if not api_key:
        if "dart_api_key" in st.secrets:
            api_key = st.secrets["dart_api_key"]
        else:
            return None # 키가 없으면 못 가져옴

    try:
        dart = OpenDartReader(api_key)
        # DART에서 전체 기업 목록 다운로드 (약 3~5초 소요)
        corp_list = dart.corp_codes
        
        # 종목코드(stock_code)가 있는 회사만 필터링 (상장사)
        listed_df = corp_list[corp_list['stock_code'].notnull()]
        
        # 이름:코드 딕셔너리로 변환
        # 예: {'삼성전자': '005930', '카카오': '035720', ...}
        corp_dict = dict(zip(listed_df['corp_name'], listed_df['stock_code']))
        return corp_dict
    except:
        return None

# --- 데이터 수집 (자동 매핑 기능 탑재) ---
@st.cache_data(ttl=600)
def get_stock_data(user_input, period_days):
    df = pd.DataFrame()
    code = ""
    name = user_input
    source = ""
    
    # 1. DART 명단에서 이름 찾기 (가장 정확함)
    corp_dict = get_corp_dict()
    
    # 입력값이 숫자 6자리(코드)면 바로 사용
    if user_input.isdigit() and len(user_input) == 6:
        code = user_input
        name = f"Code: {code}"
    # 한글 이름이면 DART 명단에서 검색
    elif corp_dict:
        # 정확히 일치하는 경우
        if user_input in corp_dict:
            code = corp_dict[user_input]
            name = user_input
        else:
            # (옵션) 비슷한 이름 찾기? 일단은 정확한 일치만
            return None, None, None, f"'{user_input}'을 찾을 수 없습니다. 회사명을 정확히 입력해주세요."
    else:
        # API 키가 없어서 명단을 못 만들었을 경우 -> KRX 시도 (백업)
        try:
            krx = fdr.StockListing('KRX')
            target = krx[krx['Name'] == user_input]
            if target.empty:
                return None, None, None, "검색 실패. 종목코드로 입력해주세요."
            code = target.iloc[0]['Code']
            name = user_input
        except:
            return None, None, None, "DART API 키가 없거나 KRX 접속 실패. 코드로 입력해주세요."

    # 2. 데이터 다운로드 (야후 -> 네이버)
    end_dt = datetime.datetime.now() + datetime.timedelta(days=1)
    start_dt = datetime.datetime.now() - datetime.timedelta(days=period_days*2)
    
    try:
        candidates = [f"{code}.KS", f"{code}.KQ"]
        for ticker in candidates:
            temp_df = yf.download(ticker, start=start_dt, end=end_dt, progress=False, auto_adjust=True)
            if not temp_df.empty:
                df = temp_df
                source = "Yahoo Finance"
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                break
    except: pass

    if df.empty:
        try:
            df = fdr.DataReader(code, start_dt)
            source = "Naver Finance"
        except: pass
    
    if df.empty:
        return None, None, None, f"데이터 수집 실패 ({name}/{code}). 상장폐지되었거나 코드가 다를 수 있습니다."
        
    df = df.dropna()
    
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC').tz_convert('Asia/Seoul')
    else:
        df.index = df.index.tz_convert('Asia/Seoul')
    df.index = df.index.strftime('%Y-%m-%d')
        
    return df, name, code, source

# --- 보조지표 및 분석 함수 (기존과 동일) ---
def calculate_indicators(df):
    df = df.copy()
    close = df['Close']
    df['MA5'] = close.rolling(5).mean()
    df['MA20'] = close.rolling(20).mean()
    df['MA60'] = close.rolling(60).mean()
    df['std'] = close.rolling(20).std()
    df['Upper'] = df['MA20'] + (df['std'] * 2)
    df['Lower'] = df['MA20'] - (df['std'] * 2)
    df['EMA12'] = close.ewm(span=12).mean()
    df['EMA26'] = close.ewm(span=26).mean()
    df['MACD'] = df['EMA12'] - df['EMA26']
    df['Signal'] = df['MACD'].ewm(span=9).mean()
    delta = close.diff(1)
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    df['Vol_MA20'] = df['Volume'].rolling(20).mean()
    df['Resistance'] = df['High'].rolling(60).max()
    df['Support'] = df['Low'].rolling(60).min()
    return df

def analyze_market(df):
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    score = 50
    report = []
    
    if latest['Close'] > latest['MA20']:
        score += 10
        report.append("📈 **[추세]** 20일선 위 상승 추세")
    else:
        score -= 10
        report.append("📉 **[추세]** 20일선 아래 하락 우려")
        
    if latest['RSI'] >= 70:
        score -= 20
        report.append(f"⚠️ **[심리]** RSI 과매수({latest['RSI']:.1f})")
    elif latest['RSI'] <= 30:
        score += 20
        report.append(f"💎 **[심리]** RSI 과매도({latest['RSI']:.1f})")
    
    if latest['Vol_MA20'] > 0:
        vol_ratio = (latest['Volume'] / latest['Vol_MA20']) * 100
        if vol_ratio > 150 and latest['Close'] > prev['Close']:
            score += 10
            report.append("📢 **[수급]** 거래량 실린 강한 상승")

    if latest['Close'] > latest['Upper']: report.append("🔴 밴드 상단 돌파 (과열)")
    elif latest['Close'] < latest['Lower']: report.append("🔵 밴드 하단 이탈 (반등 기대)")

    score = max(0, min(100, score))
    sent = "중립"
    col = "gray"
    if score >= 80: sent, col = "강력 매수", "green"
    elif score >= 60: sent, col = "매수 우위", "blue"
    elif score <= 20: sent, col = "강력 매도", "red"
    elif score <= 40: sent, col = "매도 우위", "orange"
    
    return score, sent, col, report, latest['Support'], latest['Resistance']

# --- 사이드바 ---
with st.sidebar:
    st.header("설정")
    
    # [상태 표시] 명단 로딩 확인
    corp_dict = get_corp_dict()
    if corp_dict:
        st.success(f"✅ {len(corp_dict):,}개 종목 로딩 완료!")
    else:
        st.warning("⚠️ API 키가 없어서 자동완성 기능이 꺼졌습니다.")

    user_input = st.text_input("종목명/코드", "삼성전자")
    period_days = st.slider("차트 기간", 100, 600, 300)
    if st.button("🔄 새로고침"): st.cache_data.clear()

# --- 메인 ---
if user_input:
    with st.spinner(f"'{user_input}' 분석 중..."):
        df, name, code, msg = get_stock_data(user_input, period_days)
        
        if df is None:
            st.error(msg)
        else:
            try:
                df = calculate_indicators(df)
                score, sentiment, color, report_text, support, resistance = analyze_market(df)
                
                latest = df.iloc[-1]
                prev = df.iloc[-2]
                change = latest['Close'] - prev['Close']
                rate = (change / prev['Close']) * 100
                
                st.metric(f"{name} ({code})", f"{latest['Close']:,.0f}원", f"{change:,.0f}원 ({rate:.2f}%)")
                
                st.divider()
                c1, c2 = st.columns([1, 3])
                with c1:
                    st.markdown(f"<h1 style='text-align:center; color:{color};'>{score}점</h1>", unsafe_allow_html=True)
                    st.markdown(f"<p style='text-align:center;'>{sentiment}</p>", unsafe_allow_html=True)
                    st.progress(score/100)
                with c2:
                    for l in report_text: st.write(l)
                    st.caption(f"지지: {support:,.0f} / 저항: {resistance:,.0f}")
                
                st.divider()
                tab1, tab2 = st.tabs(["차트", "지표"])
                with tab1: st.line_chart(df[['Close', 'MA20', 'Upper', 'Lower']].tail(period_days), color=["#0000FF", "#FFA500", "#CCCCCC", "#CCCCCC"])
                with tab2: st.line_chart(df[['MACD', 'Signal', 'RSI']].tail(period_days))
                
            except Exception as e: st.error(f"Error: {e}")
