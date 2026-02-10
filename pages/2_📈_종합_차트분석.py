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
        if "dart_api_key" in st.secrets:
            api_key = st.secrets["dart_api_key"]
        else:
            return None
    try:
        dart = OpenDartReader(api_key)
        corp_list = dart.corp_codes
        listed_df = corp_list[corp_list['stock_code'].notnull()]
        return dict(zip(listed_df['corp_name'], listed_df['stock_code']))
    except:
        return None

# --- 2. 데이터 수집 (가격 정보만) ---
@st.cache_data(ttl=600)
def get_stock_data(user_input, period_days):
    df = pd.DataFrame()
    code = ""
    name = user_input
    source = ""
    
    corp_dict = get_corp_dict()
    
    # 입력값 처리
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
            if target.empty:
                return None, None, None, f"'{user_input}'을 찾을 수 없습니다."
            code = target.iloc[0]['Code']
            name = user_input
        except:
            return None, None, None, "검색 실패."

    # 기간 설정
    end_dt = datetime.datetime.now() + datetime.timedelta(days=1)
    start_dt = datetime.datetime.now() - datetime.timedelta(days=period_days*2)
    
    # 야후 파이낸스 시도
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
    except:
        pass

    # 네이버 파이낸스 백업
    if df.empty:
        try:
            df = fdr.DataReader(code, start_dt)
            source = "Naver Finance"
        except:
            pass
    
    if df.empty:
        return None, None, None, "데이터 수집 실패."
        
    # 데이터 정리
    df = df.dropna()
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC').tz_convert('Asia/Seoul')
    else:
        df.index = df.index.tz_convert('Asia/Seoul')
    df.index = df.index.strftime('%Y-%m-%d')
        
    return df, name, code, source

# --- 3. 지표 계산 ---
def calculate_indicators(df):
    df = df.copy()
    close = df['Close']
    
    # 이동평균선
    df['MA20'] = close.rolling(20).mean()
    df['MA60'] = close.rolling(60).mean()
    
    # 볼린저 밴드
    df['std'] = close.rolling(20).std()
    df['Upper'] = df['MA20'] + (df['std'] * 2)
    df['Lower'] = df['MA20'] - (df['std'] * 2)
    
    # 거래량 이평
    df['Vol_MA20'] = df['Volume'].rolling(20).mean()
    
    # RSI
    delta = close.diff(1)
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # 지지/저항
    df['Resistance'] = df['High'].rolling(60).max()
    df['Support'] = df['Low'].rolling(60).min()
    
    return df

# --- 4. 상세 분석 엔진 ---
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
    elif latest['MA20'] < latest['MA60']:
        score -= 5
        report.append("20일선이 60일선 아래에 있는 **역배열** 상태입니다. 위로 올라갈 때마다 매물 저항을 받을 수 있습니다.")

    # (2) 심리 분석 (RSI)
    if latest['RSI'] >= 70:
        score -= 15
        report.append(f"⚠️ **[심리]** RSI 지표가 {latest['RSI']:.0f}로 **과매수** 구간입니다. 매수세가 너무 뜨겁습니다. 단기 차익실현 매물이 쏟아질 수 있습니다.")
    elif latest['RSI'] <= 30:
        score += 15
        report.append(f"💎 **[심리]** RSI 지표가 {latest['RSI']:.0f}로 **과매도** 구간입니다. 공포감에 과하게 팔린 상태라 기술적 반등이 나올 확률이 높습니다.")
    else:
        report.append(f"😌 **[심리]** RSI는 {latest['RSI']:.0f}로 과열되지도, 침체되지도 않은 중립적인 심리 상태입니다.")

    # (3) 수급 분석 (Volume)
    if latest['Vol_MA20'] > 0:
        vol_ratio = (latest['Volume'] / latest['Vol_MA20']) * 100
        if latest['Close'] > prev['Close'] and vol_ratio > 150:
            score += 10
            report.append(f"📢 **[수급]** 평소보다 **{vol_ratio:.0f}% 많은 거래량**을 동반하며 상승했습니다. '진짜 매수세'가 들어왔을 가능성이 큽니다.")
        elif latest['Close'] < prev['Close'] and vol_ratio > 150:
            score -= 10
            report.append(f"📢 **[수급]** 하락하면서 **대량 거래({vol_ratio:.0f}%)**가 터졌습니다. 실망 매물이 쏟아지고 있으니 바닥을 확인하기 전까지 관망해야 합니다.")
        elif latest['Close'] > prev['Close'] and vol_ratio < 50:
            report.append("☁️ **[수급]** 주가는 올랐지만 거래량이 평소의 절반도 안 됩니다. 힘이 없는 반등이라 다시 밀릴 수 있습니다.")

    # (4) 변동성 (Bollinger)
    if latest['Close'] > latest['Upper']:
        report.append("🔴 **[변동성]** 주가가 볼린저 밴드 상단을 뚫었습니다. 단기적으로 조정이 올 가능성이 매우 큽니다.")
    elif latest['Close'] < latest['Lower']:
        report.append("🔵 **[변동성]** 주가가 볼린저 밴드 하단을 뚫고 내려갔습니다. 과도한 하락으로 판단되어 기술적 반등이 기대됩니다.")

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
    if corp_dict:
        st.caption(f"DB 연동 완료 ({len(corp_dict):,}개)")
    
    user_input = st.text_input("종목명/코드", "삼성전자")
    if st.button("🔄 새로고침"):
        st.cache_data.clear()

# --- 메인 ---
if user_input:
    with st.spinner(f"'{user_input}' 심층 분석 중..."):
        # 데이터 수집 (펀더멘털 제거됨)
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
                
                # 1. 헤드라인
                st.markdown(f"### {name} ({code})")
                st.metric(label="현재 주가", 
                          value=f"{latest['Close']:,.0f}원", 
                          delta=f"{change:,.0f}원 ({rate:.2f}%)")
                
                st.divider()

                # 2. 기술적 점수판
                col1, col2 = st.columns([1, 1])
                with col1:
                    st.markdown(f"**AI 기술적 의견: <span style='color:{color}'>{sentiment}</span>**", unsafe_allow_html=True)
                with col2:
                    st.markdown(f"**종합 점수: <span style='color:{color}'>{score}점</span>**", unsafe_allow_html=True)
                
                st.progress(score/100)
                st.caption(f"1차 지지선: {support:,.0f}원 / 1차 저항선: {resistance:,.0f}원")

                st.divider()

                # 3. 상세 리포트
                st.subheader("📝 상세 분석 리포트")
                for line in report_text:
                    if "📈" in line or "💎" in line or "긍정" in line:
                        st.success(line)
                    elif "📉" in line or "⚠️" in line or "🔴" in line:
                        st.error(line)
                    else:
                        st.info(line)
                        
                st.caption(f"※ 분석 기준일: {df.index[-1]} | 데이터: {msg}")

            except Exception as e:
                st.error(f"Error: {e}")
