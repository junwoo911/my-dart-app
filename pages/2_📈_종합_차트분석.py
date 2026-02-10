import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import datetime
import yfinance as yf
import OpenDartReader

st.set_page_config(page_title="종합 차트 분석", page_icon="📈", layout="centered")
st.title("📈 AI 기술적 심층 정밀 진단")

# --- 1. DART 전 종목 리스트 ---
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
        except: return None, None, None, "검색 실패."

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

# --- 3. [핵심] 모든 지표 총동원 계산 ---
def calculate_indicators(df):
    df = df.copy()
    close = df['Close']
    
    # (1) 이동평균선 (단기/중기/장기/초장기)
    df['MA5'] = close.rolling(5).mean()
    df['MA20'] = close.rolling(20).mean()
    df['MA60'] = close.rolling(60).mean()
    df['MA120'] = close.rolling(120).mean()
    
    # (2) 볼린저 밴드
    df['std'] = close.rolling(20).std()
    df['Upper'] = df['MA20'] + (df['std'] * 2)
    df['Lower'] = df['MA20'] - (df['std'] * 2)
    df['BandWidth'] = (df['Upper'] - df['Lower']) / df['MA20'] * 100 # 밴드폭(%)
    
    # (3) MACD
    df['EMA12'] = close.ewm(span=12).mean()
    df['EMA26'] = close.ewm(span=26).mean()
    df['MACD'] = df['EMA12'] - df['EMA26']
    df['Signal'] = df['MACD'].ewm(span=9).mean()
    df['Hist'] = df['MACD'] - df['Signal']
    
    # (4) RSI
    delta = close.diff(1)
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # (5) 거래량 이평
    df['Vol_MA5'] = df['Volume'].rolling(5).mean()
    df['Vol_MA20'] = df['Volume'].rolling(20).mean()
    
    # (6) 지지/저항 (최근 60일 기준)
    df['High60'] = df['High'].rolling(60).max()
    df['Low60'] = df['Low'].rolling(60).min()
    
    return df

# --- 4. [복구] 심층 정밀 분석 엔진 (모든 데이터 해석) ---
def analyze_market_deep(df):
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    score = 50
    report = []
    
    # --- [1] 추세 분석 (이동평균선 & 배열) ---
    trend_msg = []
    # 20일선 (생명선)
    if curr['Close'] > curr['MA20']:
        score += 10
        trend_msg.append("✅ 주가가 **20일선(생명선)** 위에 안착해 상승 추세를 유지 중입니다.")
    else:
        score -= 10
        trend_msg.append("⛔ 주가가 **20일선** 아래로 무너져 단기적으로 약세입니다.")
    
    # 정배열/역배열 (5 > 20 > 60)
    if curr['MA5'] > curr['MA20'] > curr['MA60']:
        score += 10
        trend_msg.append("✅ **완벽한 정배열** 상태입니다. (5일>20일>60일) 상승 에너지가 가장 강한 구간입니다.")
    elif curr['MA5'] < curr['MA20'] < curr['MA60']:
        score -= 10
        trend_msg.append("⛔ **완벽한 역배열** 상태입니다. (5일<20일<60일) 하락 압력이 강해 바닥을 논하기 이릅니다.")
    
    # 골든/데드 크로스
    if curr['MA5'] > curr['MA20'] and prev['MA5'] <= prev['MA20']:
        score += 5
        trend_msg.append("🔥 방금 **5일선이 20일선을 돌파(골든크로스)**했습니다! 단기 급등 신호일 수 있습니다.")
    
    report.append({"title": "1. 추세 (Trend)", "content": " ".join(trend_msg), "score": score})


    # --- [2] 변동성 분석 (볼린저 밴드) ---
    vol_msg = []
    # 위치 파악
    if curr['Close'] > curr['Upper']:
        score -= 5
        vol_msg.append("🔴 주가가 **밴드 상단**을 뚫었습니다. 단기 과열로 인해 밴드 안쪽으로 회귀하려는 성질이 강합니다 (조정 주의).")
    elif curr['Close'] < curr['Lower']:
        score += 5
        vol_msg.append("🔵 주가가 **밴드 하단**을 뚫고 내려갔습니다. 통계적으로 과도한 하락이라 기술적 반등이 나올 확률이 높습니다.")
    else:
        vol_msg.append("⚪ 주가가 밴드 내부에서 안정적으로 움직이고 있습니다.")
        
    # 밴드폭 (스퀴즈)
    if curr['BandWidth'] < 10: # 밴드폭이 매우 좁음
        vol_msg.append("⚡ **밴드폭이 극도로 좁아졌습니다(스퀴즈).** 조만간 위든 아래든 큰 방향성이 터질 전조 증상입니다.")
        
    report.append({"title": "2. 변동성 (Volatility)", "content": " ".join(vol_msg)})


    # --- [3] 모멘텀 & 심리 (MACD + RSI) ---
    mom_msg = []
    # MACD
    if curr['MACD'] > curr['Signal']:
        mom_msg.append("✅ **MACD**가 시그널 선 위에 있어 상승 모멘텀이 살아있습니다.")
        if curr['Hist'] > prev['Hist'] and curr['Hist'] > 0:
             mom_msg.append("(상승 강도가 점점 세지고 있습니다.)")
    else:
        mom_msg.append("⛔ **MACD**가 시그널 선 아래에 있어 하락 모멘텀이 우세합니다.")

    # RSI
    if curr['RSI'] >= 70:
        score -= 10
        mom_msg.append(f"⚠️ **RSI({curr['RSI']:.0f}) 과매수!** 매수세가 너무 뜨겁습니다. 신규 진입은 자제하고 차익 실현을 고려하세요.")
    elif curr['RSI'] <= 30:
        score += 10
        mom_msg.append(f"💎 **RSI({curr['RSI']:.0f}) 과매도!** 공포에 질려 투매가 나왔습니다. 저점 매수의 기회일 수 있습니다.")
    else:
        mom_msg.append(f"⚪ RSI는 {curr['RSI']:.0f}로 과열/침체 없는 중립 구간입니다.")
        
    report.append({"title": "3. 심리 & 모멘텀", "content": " ".join(mom_msg)})


    # --- [4] 수급 & 거래량 (Volume) ---
    vol_analysis = []
    vol_ratio = (curr['Volume'] / curr['Vol_MA20']) * 100
    
    if vol_ratio > 200:
        vol_analysis.append(f"📢 **거래량 폭발({vol_ratio:.0f}%)!** 평소의 2배가 넘는 거래량이 터졌습니다.")
        if curr['Close'] > prev['Close']:
            score += 5
            vol_analysis.append("양봉에 대량 거래가 실렸으니 **강력한 매수세(세력)**가 유입된 것으로 보입니다.")
        else:
            score -= 5
            vol_analysis.append("음봉에 대량 거래가 실렸으니 **강력한 매도세(실망 매물)**가 쏟아진 것입니다.")
    elif vol_ratio < 50:
        vol_analysis.append(f"☁️ 거래량이 평소의 {vol_ratio:.0f}% 수준으로 매우 적습니다. 시장의 관심에서 멀어져 있습니다.")
        
    report.append({"title": "4. 수급 (Volume)", "content": " ".join(vol_analysis) if vol_analysis else "평이한 거래량 흐름입니다."})


    # --- [5] 지지 & 저항 (Support/Resistance) ---
    sr_msg = []
    # 현재가가 저항선 근처인가?
    if curr['High60'] > 0:
        dist_res = (curr['High60'] - curr['Close']) / curr['Close'] * 100
        if dist_res < 3: # 3% 이내 접근
            sr_msg.append(f"🚧 주가가 **60일 최고가({curr['High60']:,.0f}원)**인 저항선에 근접했습니다. 여기를 뚫으면 신고가 랠리가 가능합니다.")
    
    # 현재가가 지지선 근처인가?
    if curr['Low60'] > 0:
        dist_sup = (curr['Close'] - curr['Low60']) / curr['Close'] * 100
        if dist_sup < 3:
            sr_msg.append(f"🛡️ 주가가 **60일 최저가({curr['Low60']:,.0f}원)**인 바닥권에 근접했습니다. 지지 여부를 잘 봐야 합니다.")
            
    if not sr_msg: sr_msg.append("현재 의미 있는 지지/저항선과 거리가 있어 자유로운 구간입니다.")
    
    report.append({"title": "5. 지지 & 저항", "content": " ".join(sr_msg)})

    # 점수 최종 보정
    score = max(0, min(100, score))
    sentiment = "관망 (Hold)"
    color = "gray"
    if score >= 80: sentiment, color = "강력 매수", "green"
    elif score >= 60: sentiment, color = "매수 우위", "blue"
    elif score <= 20: sentiment, color = "강력 매도", "red"
    elif score <= 40: sentiment, color = "매도 우위", "orange"
        
    return score, sentiment, color, report, curr['Low60'], curr['High60']

# --- 사이드바 ---
with st.sidebar:
    st.header("🔍 종목 검색")
    corp_dict = get_corp_dict()
    if corp_dict: st.caption(f"DB 연동 완료 ({len(corp_dict):,}개)")
    user_input = st.text_input("종목명/코드", "삼성전자")
    if st.button("🔄 새로고침"): st.cache_data.clear()

# --- 메인 ---
if user_input:
    with st.spinner(f"'{user_input}'의 모든 데이터를 샅샅이 뒤지는 중..."):
        df, name, code, msg = get_stock_data(user_input, 300)
        
        if df is None:
            st.error(msg)
        else:
            try:
                df = calculate_indicators(df)
                score, sentiment, color, report_data, support, resistance = analyze_market_deep(df)
                
                latest = df.iloc[-1]
                prev = df.iloc[-2]
                change = latest['Close'] - prev['Close']
                rate = (change / prev['Close']) * 100
                
                # 헤드라인
                st.markdown(f"### {name} ({code})")
                st.metric(label="현재 주가", 
                          value=f"{latest['Close']:,.0f}원", 
                          delta=f"{change:,.0f}원 ({rate:.2f}%)")
                
                st.divider()

                # 점수판
                c1, c2 = st.columns([1, 1])
                with c1:
                    st.markdown(f"**AI 종합 의견**")
                    st.markdown(f"<h2 style='color:{color};'>{sentiment}</h2>", unsafe_allow_html=True)
                with c2:
                    st.markdown(f"**기술적 점수**")
                    st.markdown(f"<h2 style='color:{color};'>{score}점</h2>", unsafe_allow_html=True)
                st.progress(score/100)
                
                st.divider()

                # [핵심] 심층 분석 리포트 출력
                st.subheader("📝 심층 정밀 분석 리포트")
                
                for item in report_data:
                    with st.expander(f"**{item['title']}**", expanded=True):
                        content = item['content']
                        if "✅" in content or "💎" in content or "🔥" in content:
                            st.success(content)
                        elif "⛔" in content or "⚠️" in content or "🔴" in content:
                            st.error(content)
                        else:
                            st.info(content)

                st.divider()
                st.caption(f"※ 60일 최저가(지지): {support:,.0f}원 / 60일 최고가(저항): {resistance:,.0f}원")
                st.caption(f"※ 기준일: {df.index[-1]} | 데이터: {msg}")

            except Exception as e: st.error(f"Error: {e}")
