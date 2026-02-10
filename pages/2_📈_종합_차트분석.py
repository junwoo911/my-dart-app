import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import datetime
import yfinance as yf

st.set_page_config(page_title="종합 차트 분석", page_icon="📈", layout="wide")
st.title("📈 종합 기술적 분석 센터")

# --- [핵심] 주가 데이터 수집 함수 (에러 방지 버전) ---
# 캐싱을 적용해서 속도를 높입니다.
@st.cache_data
def get_stock_data(stock_name, period_days):
    try:
        # 1. 종목 코드 찾기
        krx = fdr.StockListing('KRX')
        target = krx[krx['Name'] == stock_name]
        
        if target.empty:
            return None, "종목명을 정확히 입력해주세요."
        
        code = target.iloc[0]['Code']
        
        # 2. 야후 파이낸스 티커 추측 (코스피? 코스닥?)
        # 둘 다 시도해보고 데이터 있는 놈을 가져옵니다.
        candidates = [f"{code}.KS", f"{code}.KQ"]
        df = pd.DataFrame()
        
        start_dt = datetime.datetime.now() - datetime.timedelta(days=period_days*2) # 넉넉하게
        
        for ticker in candidates:
            temp_df = yf.download(ticker, start=start_dt, progress=False)
            if not temp_df.empty:
                df = temp_df
                break
        
        if df.empty:
            return None, "데이터를 가져올 수 없습니다. (상장폐지 또는 티커 오류)"
            
        # 3. [중요] yfinance 최신 버전 호환성 패치
        # 컬럼이 MultiIndex(복잡한 형태)로 올 경우 단순화
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # 4. 데이터 정제 (결측치 제거)
        df = df.dropna()
        
        if len(df) < 20:
            return None, "분석할 데이터가 너무 적습니다."
            
        return df, code
        
    except Exception as e:
        return None, f"에러 발생: {e}"

# --- 보조지표 계산 ---
def calculate_technical_indicators(df):
    df = df.copy()
    
    # 이동평균선
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    
    # 볼린저 밴드
    df['std'] = df['Close'].rolling(window=20).std()
    df['Upper_Band'] = df['MA20'] + (df['std'] * 2)
    df['Lower_Band'] = df['MA20'] - (df['std'] * 2)
    
    # MACD
    df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
    df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = df['EMA12'] - df['EMA26']
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    # RSI
    delta = df['Close'].diff(1)
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    return df

# --- 사이드바 ---
with st.sidebar:
    st.header("설정")
    stock_name = st.text_input("종목명", "삼성전자")
    period_days = st.slider("분석 기간 (일)", 100, 500, 200)

# --- 메인 실행 ---
if stock_name:
    with st.spinner(f"'{stock_name}' 데이터를 분석 중입니다..."):
        df, code_or_err = get_stock_data(stock_name, period_days)
        
        if df is None:
            st.error(code_or_err) # 에러 메시지 출력
        else:
            code = code_or_err
            
            # 지표 계산
            df = calculate_technical_indicators(df)
            
            # 최신 데이터
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            # 1. 헤드라인
            change = latest['Close'] - prev['Close']
            rate = (change / prev['Close']) * 100
            st.metric(label=f"{stock_name} ({code})", 
                      value=f"{latest['Close']:,.0f}원", 
                      delta=f"{change:,.0f}원 ({rate:.2f}%)")
            
            # 2. 차트
            st.subheader("주가 및 볼린저 밴드")
            chart_data = df[['Close', 'MA20', 'Upper_Band', 'Lower_Band']].tail(period_days)
            st.line_chart(chart_data, color=["#0000FF", "#FFA500", "#CCCCCC", "#CCCCCC"]) 
            
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("MACD")
                st.line_chart(df[['MACD', 'Signal']].tail(period_days))
            with col2:
                st.subheader("RSI (과매수/과매도)")
                st.line_chart(df[['RSI']].tail(period_days))
                # 기준선 표시 (30, 70)
                st.caption("RSI 70 이상: 과매수 / 30 이하: 과매도")

            # 3. AI 진단
            st.divider()
            st.subheader("🤖 AI 기술적 진단 리포트")
            
            diagnosis = []
            
            # 이평선
            if latest['Close'] > latest['MA20'] and latest['MA20'] > latest['MA60']:
                diagnosis.append("✅ **[상승 정배열]** 주가와 이평선이 정배열입니다. 상승 추세가 견고합니다.")
            elif latest['MA5'] > latest['MA20'] and prev['MA5'] <= prev['MA20']:
                diagnosis.append("🔥 **[골든 크로스]** 단기선이 장기선을 뚫고 올라갔습니다. 매수 신호입니다!")
            elif latest['MA5'] < latest['MA20'] and prev['MA5'] >= prev['MA20']:
                diagnosis.append("❄️ **[데드 크로스]** 단기선이 무너졌습니다. 조정이 예상됩니다.")
                
            # 볼린저 밴드
            if latest['Close'] > latest['Upper_Band']:
                diagnosis.append("🔴 **[과열 경고]** 볼린저 밴드 상단을 돌파했습니다. 단기 고점일 수 있습니다.")
            elif latest['Close'] < latest['Lower_Band']:
                diagnosis.append("🔵 **[반등 기대]** 볼린저 밴드 하단을 이탈했습니다. 기술적 반등이 나올 자리입니다.")
                
            # RSI
            if latest['RSI'] >= 70:
                diagnosis.append(f"🚨 **[RSI 과매수 ({latest['RSI']:.0f})]** 매수세가 너무 강합니다. 차익 실현을 고려하세요.")
            elif latest['RSI'] <= 30:
                diagnosis.append(f"💎 **[RSI 과매도 ({latest['RSI']:.0f})]** 공포 구간입니다. 저점 매수 기회일 수 있습니다.")
            
            # 거래량 (야후 데이터에 Volume이 있는 경우)
            if 'Volume' in df.columns and latest['Volume'] > 0:
                 vol_avg = df['Volume'].rolling(20).mean().iloc[-1]
                 if latest['Volume'] > vol_avg * 2:
                     diagnosis.append("📢 **[거래량 폭발]** 평소보다 2배 이상의 거래량이 터졌습니다. 큰 변동성이 시작되었습니다.")

            if not diagnosis:
                st.info("특이사항 없이 무난한 흐름을 보이고 있습니다.")
            else:
                for msg in diagnosis:
                    st.write(msg)
