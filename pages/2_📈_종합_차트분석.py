import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import datetime
import yfinance as yf

st.set_page_config(page_title="종합 차트 분석", page_icon="📈", layout="wide")
st.title("📈 종합 기술적 분석 센터 (Pro)")

# --- [핵심] 주가 데이터 수집 (우회 접속 + 시간 보정) ---
@st.cache_data(ttl=600)
def get_stock_data(user_input, period_days):
    df = pd.DataFrame()
    code = ""
    name = user_input
    source = ""
    
    if user_input.isdigit() and len(user_input) == 6:
        code = user_input
        name = f"Code: {code}"
    else:
        try:
            krx = fdr.StockListing('KRX')
            target = krx[krx['Name'] == user_input]
            if target.empty:
                return None, None, None, "종목명을 찾을 수 없습니다. '005930' 같은 코드를 입력해보세요."
            code = target.iloc[0]['Code']
            name = user_input
        except:
            return None, None, None, "KRX 검색 불가. 종목코드로 입력해주세요."

    end_dt = datetime.datetime.now() + datetime.timedelta(days=1)
    start_dt = datetime.datetime.now() - datetime.timedelta(days=period_days*2) # 넉넉히 수집
    
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
        return None, None, None, "데이터 수집 실패. 코드를 확인해주세요."
        
    df = df.dropna()
    
    # 시간대 보정
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC').tz_convert('Asia/Seoul')
    else:
        df.index = df.index.tz_convert('Asia/Seoul')
    df.index = df.index.strftime('%Y-%m-%d')
        
    return df, name, code, source

# --- [업그레이드] 고급 보조지표 계산 ---
def calculate_indicators(df):
    df = df.copy()
    close = df['Close']
    
    # 1. 이동평균선
    df['MA5'] = close.rolling(window=5).mean()
    df['MA20'] = close.rolling(window=20).mean()
    df['MA60'] = close.rolling(window=60).mean()
    df['MA120'] = close.rolling(window=120).mean()
    
    # 2. 볼린저 밴드
    df['std'] = close.rolling(window=20).std()
    df['Upper'] = df['MA20'] + (df['std'] * 2)
    df['Lower'] = df['MA20'] - (df['std'] * 2)
    
    # 3. MACD
    df['EMA12'] = close.ewm(span=12).mean()
    df['EMA26'] = close.ewm(span=26).mean()
    df['MACD'] = df['EMA12'] - df['EMA26']
    df['Signal'] = df['MACD'].ewm(span=9).mean()
    df['MACD_Hist'] = df['MACD'] - df['Signal']
    
    # 4. RSI
    delta = close.diff(1)
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # 5. 거래량 이평
    df['Vol_MA20'] = df['Volume'].rolling(window=20).mean()

    # 6. [NEW] 지지/저항선 (최근 60일 고가/저가)
    df['Resistance'] = df['High'].rolling(window=60).max()
    df['Support'] = df['Low'].rolling(window=60).min()
    
    return df

# --- [NEW] 전문가 분석 엔진 ---
def analyze_market(df):
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    score = 50 # 기본 점수 50점
    reasons = [] # 점수 이유
    report = [] # 상세 리포트 문장
    
    # 1. 추세 분석 (Trend)
    trend_score = 0
    if latest['Close'] > latest['MA20']:
        trend_score += 10
        report.append("📈 **[추세]** 주가가 생명선인 20일 이동평균선 위에 안착해 있습니다. 단기 추세가 살아있습니다.")
    else:
        trend_score -= 10
        report.append("📉 **[추세]** 주가가 20일 이동평균선 아래로 처져있어 힘이 약한 상태입니다.")
        
    if latest['MA20'] > latest['MA60']:
        trend_score += 10
        report.append("또한 20일선이 60일선 위에 있는 '정배열' 초기 혹은 지속 구간으로 중기적인 방향성도 우상향입니다.")
    elif latest['MA20'] < latest['MA60']:
        trend_score -= 10
        report.append("하지만 20일선이 60일선 아래에 있는 '역배열' 상태라 상승 시마다 매물 압박을 받을 수 있습니다.")

    score += trend_score
    
    # 2. 모멘텀 분석 (RSI)
    rsi = latest['RSI']
    if rsi >= 70:
        score -= 20
        report.append(f"⚠️ **[심리]** 현재 RSI가 {rsi:.1f}로 '과매수' 구간입니다. 매수세가 너무 뜨거워 단기 차익실현 매물이 쏟아질 수 있으니 추격 매수는 위험합니다.")
    elif rsi <= 30:
        score += 20
        report.append(f"💎 **[심리]** 현재 RSI가 {rsi:.1f}로 '과매도' 구간입니다. 공포감에 투매가 나왔으나, 기술적 반등이 임박한 저점 매수 기회일 수 있습니다.")
    else:
        report.append(f"😌 **[심리]** RSI는 {rsi:.1f}로 과열되지도, 침체되지도 않은 중립적인 심리 상태입니다.")

    # 3. 거래량 분석 (Volume)
    vol_ratio = (latest['Volume'] / latest['Vol_MA20']) * 100
    if latest['Close'] > prev['Close']: # 상승장
        if vol_ratio > 150:
            score += 10
            report.append(f"📢 **[수급]** 평소보다 {vol_ratio:.0f}% 많은 거래량을 동반하며 상승했습니다. 이는 세력이나 메이저 주체의 매수세가 유입된 '진짜 상승'일 가능성이 높습니다.")
        elif vol_ratio < 50:
            score -= 5
            report.append("☁️ **[수급]** 주가는 올랐지만 거래량이 평소의 절반도 안 됩니다. 매수세가 약한 '불안한 상승'이니 곧 다시 하락할 수 있습니다.")
    else: # 하락장
        if vol_ratio > 150:
            score -= 10
            report.append(f"📢 **[수급]** 대량 거래({vol_ratio:.0f}%)를 동반한 하락이 나왔습니다. 실망 매물이 쏟아지고 있으니 바닥을 확인하기 전까지는 관망해야 합니다.")

    # 4. 볼린저 밴드 (Volatility)
    if latest['Close'] > latest['Upper']:
        report.append("🔴 **[변동성]** 주가가 볼린저 밴드 상단을 뚫었습니다. 통계적으로 밴드 안으로 회귀하려는 성질이 있어 조정 가능성이 큽니다.")
    elif latest['Close'] < latest['Lower']:
        report.append("🔵 **[변동성]** 주가가 볼린저 밴드 하단을 뚫고 내려갔습니다. 과도한 하락으로 판단되어 기술적 반등이 기대됩니다.")

    # 점수 보정 (0~100)
    score = max(0, min(100, score))
    
    # 종합 의견 도출
    final_sentiment = ""
    color = ""
    if score >= 80: 
        final_sentiment = "강력 매수 (Strong Buy)"
        color = "green"
    elif score >= 60: 
        final_sentiment = "매수 우위 (Buy)"
        color = "blue"
    elif score >= 40: 
        final_sentiment = "중립/관망 (Hold)"
        color = "gray"
    elif score >= 20: 
        final_sentiment = "매도 우위 (Sell)"
        color = "orange"
    else: 
        final_sentiment = "강력 매도 (Strong Sell)"
        color = "red"
        
    return score, final_sentiment, color, report, latest['Support'], latest['Resistance']

# --- 사이드바 ---
with st.sidebar:
    st.header("설정")
    st.info("💡 팁: '삼성전자'가 안 되면 '005930' 코드를 입력하세요.")
    user_input = st.text_input("종목명/코드", "005930")
    period_days = st.slider("차트 기간", 100, 600, 300)
    if st.button("🔄 새로고침"): st.cache_data.clear()

# --- 메인 화면 ---
if user_input:
    with st.spinner("전문가 알고리즘으로 분석 중..."):
        df, name, code, msg = get_stock_data(user_input, period_days)
        
        if df is None:
            st.error(msg)
        else:
            try:
                # 지표 계산
                df = calculate_indicators(df)
                
                # 전문가 분석 실행
                score, sentiment, color, report_text, support, resistance = analyze_market(df)
                
                latest = df.iloc[-1]
                prev = df.iloc[-2]
                change = latest['Close'] - prev['Close']
                rate = (change / prev['Close']) * 100
                
                # [1] 상단 요약 배너
                st.metric(label=f"{name} ({code})", 
                          value=f"{latest['Close']:,.0f}원", 
                          delta=f"{change:,.0f}원 ({rate:.2f}%)")
                
                # [2] 종합 점수판 (게이지)
                st.divider()
                col_score, col_text = st.columns([1, 3])
                
                with col_score:
                    st.subheader("AI 투자 점수")
                    # 점수에 따른 색상 및 게이지 표시
                    st.markdown(f"""
                        <h1 style='text-align: center; color: {color}; font-size: 60px;'>{score}점</h1>
                        <p style='text-align: center; font-weight: bold;'>{sentiment}</p>
                    """, unsafe_allow_html=True)
                    st.progress(score / 100)
                
                with col_text:
                    st.subheader("📝 상세 분석 리포트")
                    for line in report_text:
                        st.write(line)
                    
                    st.markdown("---")
                    c1, c2 = st.columns(2)
                    c1.info(f"**🛡️ 1차 지지선 (바닥):** {support:,.0f}원")
                    c2.warning(f"**🚧 1차 저항선 (천장):** {resistance:,.0f}원")

                # [3] 차트 영역
                st.divider()
                tab1, tab2 = st.tabs(["종합 차트", "보조지표"])
                
                with tab1:
                    st.subheader("가격 이동평균 & 볼린저 밴드")
                    st.line_chart(df[['Close', 'MA20', 'MA60', 'Upper', 'Lower']].tail(period_days), 
                                  color=["#000000", "#FF0000", "#00FF00", "#DDDDDD", "#DDDDDD"])
                
                with tab2:
                    st.subheader("MACD & RSI & 거래량")
                    st.line_chart(df[['MACD', 'Signal']].tail(period_days))
                    st.bar_chart(df['Volume'].tail(period_days))

            except Exception as e:
                st.error(f"분석 중 에러: {e}")
