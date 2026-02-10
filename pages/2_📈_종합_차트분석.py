import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import datetime
import yfinance as yf
import pytz

st.set_page_config(page_title="종합 차트 분석", page_icon="📈", layout="wide")
st.title("📈 종합 기술적 분석 센터")

# --- [핵심] 주가 데이터 수집 (코드 직접 입력 지원) ---
@st.cache_data(ttl=600)
def get_stock_data(user_input, period_days):
    df = pd.DataFrame()
    code = ""
    name = user_input
    source = ""
    
    # 1. 입력값이 '종목코드 6자리'인지 확인 (숫자만 있는지)
    if user_input.isdigit() and len(user_input) == 6:
        code = user_input
        name = f"Code: {code}" # 이름 대신 코드로 표시
    else:
        # 입력값이 '이름'이면 KRX에서 코드 찾기 시도
        try:
            krx = fdr.StockListing('KRX')
            target = krx[krx['Name'] == user_input]
            if target.empty:
                return None, None, None, "종목명을 찾을 수 없습니다. '종목코드 6자리'를 입력해보세요."
            code = target.iloc[0]['Code']
            name = user_input
        except Exception as e:
            # KRX 차단 시 메시지 리턴
            return None, None, None, f"⚠️ KRX 검색이 차단되었습니다. 회사명 대신 '종목코드 6자리'(예: 005930)를 입력해주세요!"

    # 2. 데이터 수집 (야후 파이낸스)
    end_dt = datetime.datetime.now() + datetime.timedelta(days=1)
    start_dt = datetime.datetime.now() - datetime.timedelta(days=period_days*2)
    
    try:
        # 코스피(.KS)인지 코스닥(.KQ)인지 모르니 둘 다 찔러보기
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

    # 3. 백업 (FDR)
    if df.empty:
        try:
            df = fdr.DataReader(code, start_dt)
            source = "Naver Finance"
        except: pass
    
    # 4. 검증 및 시간 보정
    if df.empty:
        return None, None, None, "데이터를 찾을 수 없습니다. (종목코드를 확인해주세요)"
        
    df = df.dropna()
    if len(df) < 20:
        return None, None, None, "분석할 데이터가 부족합니다."

    # 시간대 보정 (KST)
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC').tz_convert('Asia/Seoul')
    else:
        df.index = df.index.tz_convert('Asia/Seoul')
    df.index = df.index.strftime('%Y-%m-%d')
        
    return df, name, code, source

# --- 보조지표 계산 ---
def calculate_technical_indicators(df):
    df = df.copy()
    close = df['Close']
    
    df['MA5'] = close.rolling(window=5).mean()
    df['MA20'] = close.rolling(window=20).mean()
    df['MA60'] = close.rolling(window=60).mean()
    
    df['std'] = close.rolling(window=20).std()
    df['Upper_Band'] = df['MA20'] + (df['std'] * 2)
    df['Lower_Band'] = df['MA20'] - (df['std'] * 2)
    
    df['EMA12'] = close.ewm(span=12, adjust=False).mean()
    df['EMA26'] = close.ewm(span=26, adjust=False).mean()
    df['MACD'] = df['EMA12'] - df['EMA26']
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    delta = close.diff(1)
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    return df

# --- 사이드바 ---
with st.sidebar:
    st.header("설정")
    # [안내 문구 추가]
    st.info("💡 팁: '삼성전자' 검색이 안 되면 '005930' 같은 종목코드를 직접 입력하세요.")
    user_input = st.text_input("종목명 또는 종목코드", "005930") # 기본값을 코드로 변경
    period_days = st.slider("분석 기간 (일)", 100, 500, 200)
    
    if st.button("🔄 새로고침"):
        st.cache_data.clear()

# --- 메인 실행 ---
if user_input:
    with st.spinner(f"'{user_input}' 분석 중..."):
        df, name, code, msg = get_stock_data(user_input, period_days)
        
        if df is None:
            st.error(msg)
        else:
            try:
                df = calculate_technical_indicators(df)
                latest = df.iloc[-1]
                prev = df.iloc[-2]
                
                change = latest['Close'] - prev['Close']
                rate = (change / prev['Close']) * 100
                
                st.metric(label=f"{name} ({code})", 
                          value=f"{latest['Close']:,.0f}원", 
                          delta=f"{change:,.0f}원 ({rate:.2f}%)")
                st.caption(f"기준일: {df.index[-1]} | 출처: {msg}")
                
                tab1, tab2 = st.tabs(["기본 차트", "보조지표"])
                with tab1:
                    st.line_chart(df[['Close', 'MA20', 'Upper_Band', 'Lower_Band']].tail(period_days), color=["#0000FF", "#FFA500", "#CCCCCC", "#CCCCCC"])
                with tab2:
                    st.line_chart(df[['MACD', 'Signal', 'RSI']].tail(period_days))

                st.divider()
                st.subheader("🤖 AI 기술적 진단")
                
                diagnosis = []
                
                # 진단 로직 (이평선, 볼린저, RSI)
                if latest['Close'] > latest['MA20'] and latest['MA20'] > latest['MA60']:
                    diagnosis.append("✅ **[상승 정배열]** 주가 > 20일 > 60일. 상승 추세입니다.")
                elif latest['MA5'] < latest['MA20'] and prev['MA5'] >= prev['MA20']:
                    diagnosis.append("❄️ **[데드 크로스]** 단기 하락 신호 발생.")
                
                if latest['Close'] > latest['Upper_Band']:
                    diagnosis.append("🔴 **[과열]** 볼린저 밴드 상단 돌파. 단기 고점 주의.")
                elif latest['Close'] < latest['Lower_Band']:
                    diagnosis.append("🔵 **[침체]** 볼린저 밴드 하단 이탈. 반등 가능성.")
                
                if latest['RSI'] >= 70:
                    diagnosis.append(f"🚨 **[RSI 과매수 ({latest['RSI']:.0f})]** 매수세 과열.")
                elif latest['RSI'] <= 30:
                    diagnosis.append(f"💎 **[RSI 과매도 ({latest['RSI']:.0f})]** 저점 매수 구간.")
                
                if not diagnosis:
                    st.info("특이사항 없는 무난한 흐름입니다.")
                else:
                    for d in diagnosis: st.write(d)

            except Exception as e:
                st.error(f"분석 중 오류: {e}")
