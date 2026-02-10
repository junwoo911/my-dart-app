import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import datetime
import yfinance as yf
import OpenDartReader

st.set_page_config(page_title="종합 차트 분석", page_icon="📈", layout="centered") # wide -> centered로 변경 (집중도 향상)
st.title("📈 AI 기술적 분석 리포트")

# --- 1. DART 전 종목 리스트 (검색용) ---
@st.cache_data(show_spinner=False)
def get_corp_dict():
    api_key = st.session_state.get("api_key")
    if not api_key:
        if "dart_api_key" in st.secrets:
            api_key = st.secrets["dart_api_key"]
        else:
            return None
    try:
        dart = OpenDartReader(api_key)
        corp_list = dart.corp_codes
        listed_df = corp_list[corp_list['stock_code'].notnull()]
        corp_dict = dict(zip(listed_df['corp_name'], listed_df['stock_code']))
        return corp_dict
    except: return None

# --- 2. 데이터 수집 ---
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
        except: return None, None, None, "검색 실패. 코드를 입력해주세요."

    end_dt = datetime.datetime.now() + datetime.timedelta(days=1)
    start_dt = datetime.datetime.now() - datetime.timedelta(days=period_days*2)
    
    try:
        candidates = [f"{code}.KS", f"{code}.KQ"]
        for ticker in candidates:
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

# --- 3. 지표 계산 (차트는 안 그려도 계산은 해야 함) ---
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

# --- 4. 분석 엔진 ---
def analyze_market(df):
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    score = 50
    report = []
    
    # 추세
    if latest['Close'] > latest['MA20']:
        score += 10
        report.append("📈 **[추세]** 주가가 20일선 위에 있어 **단기 상승세**입니다.")
    else:
        score -= 10
        report.append("📉 **[추세]** 주가가 20일선 아래로 꺾여 **약세 흐름**입니다.")
        
    if latest['MA20'] > latest['MA60']:
        score += 5
        report.append("또한 20일선이 60일선 위에 있는 **정배열** 상태라 중기 방향성은 좋습니다.")
    elif latest['MA20'] < latest['MA60']:
        score -= 5
        report.append("20일선이 60일선 아래에 있는 **역배열** 상태라 매물 압박이 있을 수 있습니다.")

    # 심리 (RSI)
    if latest['RSI'] >= 70:
        score -= 15
        report.append(f"⚠️ **[심리]** RSI {latest['RSI']:.0f}로 **과매수** 구간입니다. 차익 실현 물량을 조심하세요.")
    elif latest['RSI'] <= 30:
        score += 15
        report.append(f"💎 **[심리]** RSI {latest['RSI']:.0f}로 **과매도** 구간입니다. 기술적 반등이 기대됩니다.")
    else:
        report.append(f"😌 **[심리]** RSI {latest['RSI']:.0f}로 과열 없이 안정적인 상태입니다.")

    # 수급
    if latest['Vol_MA20'] > 0:
        vol_ratio = (latest['Volume'] / latest['Vol_MA20']) * 100
        if latest['Close'] > prev['Close'] and vol_ratio > 150:
            score += 10
            report.append(f"📢 **[수급]** 평소보다 **{vol_ratio:.0f}% 많은 거래량**이 터지며 상승했습니다. 긍정적 신호입니다.")
        elif latest['Close'] < prev['Close'] and vol_ratio > 150:
            score -= 10
            report.append(f"📢 **[수급]** 하락하면서 **대량 거래({vol_ratio:.0f}%)**가 터졌습니다. 매도세가 강합니다.")

    # 변동성
    if latest['Close'] > latest['Upper']: report.append("🔴 **[변동성]** 볼린저 밴드 상단 돌파 (단기 과열)")
    elif latest['Close'] < latest['Lower']: report.append("🔵 **[변동성]** 볼린저 밴드 하단 이탈 (단기 과매도)")

    score = max(0, min(100, score))
    
    sentiment = "관망 (Hold)"
    color = "gray"
    if score >= 80: sentiment, color = "강력 매수", "green"
    elif score >= 60: sentiment, color = "매수 우위", "blue"
    elif score <= 20: sentiment, color = "강력 매도", "red"
    elif score <= 40: sentiment, color = "매도 우위", "orange"
        
    return score, sentiment, color, report, latest['Support'], latest['Resistance']

# --- 사이드바 ---
with st.sidebar:
    st.header("🔍 종목 검색")
    corp_dict = get_corp_dict()
    if corp_dict: st.caption(f"DB 연동 완료 ({len(corp_dict):,}개)")
    
    user_input = st.text_input("종목명/코드", "삼성전자")
    if st.button("🔄 새로고침"): st.cache_data.clear()

# --- 메인 ---
if user_input:
    with st.spinner(f"'{user_input}' 분석 중..."):
        df, name, code, msg = get_stock_data(user_input, 300)
        
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
                
                # 1. 헤드라인 (가격)
                st.markdown(f"### {name} ({code})")
                st.metric(label="현재 주가", 
                          value=f"{latest['Close']:,.0f}원", 
                          delta=f"{change:,.0f}원 ({rate:.2f}%)")
                
                st.divider()

                # 2. 핵심 점수판 (가장 중요)
                col1, col2, col3 = st.columns([1, 1, 1])
                with col1:
                    st.markdown("**AI 투자 의견**")
                    st.markdown(f"<h2 style='color:{color}; margin:0;'>{sentiment}</h2>", unsafe_allow_html=True)
                with col2:
                    st.markdown("**종합 점수**")
                    st.markdown(f"<h2 style='color:{color}; margin:0;'>{score}점</h2>", unsafe_allow_html=True)
                with col3:
                    st.markdown("**지지 / 저항**")
                    st.caption(f"저항: {resistance:,.0f}원")
                    st.caption(f"지지: {support:,.0f}원")

                st.progress(score/100)
                
                st.divider()

                # 3. 상세 리포트 (차트 대신 글자로!)
                st.subheader("📝 상세 분석 리포트")
                
                for line in report_text:
                    # 메시지 성격에 따라 색깔 박스로 구분
                    if "📈" in line or "💎" in line or "긍정적" in line:
                        st.success(line)
                    elif "📉" in line or "⚠️" in line or "🔴" in line:
                        st.error(line)
                    else:
                        st.info(line)
                        
                st.caption(f"※ 분석 기준일: {df.index[-1]} | 출처: {msg}")

            except Exception as e: st.error(f"Error: {e}")
