import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import datetime

st.set_page_config(page_title="종합 차트 분석", page_icon="📈", layout="wide")
st.title("📈 종합 기술적 분석 센터")

# --- 보조지표 계산 함수 모음 ---
def calculate_technical_indicators(df):
    df = df.copy()
    
    # 1. 이동평균선 (단기, 중기, 장기)
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    df['MA120'] = df['Close'].rolling(window=120).mean()
    
    # 2. 볼린저 밴드 (20일 기준)
    df['std'] = df['Close'].rolling(window=20).std()
    df['Upper_Band'] = df['MA20'] + (df['std'] * 2)
    df['Lower_Band'] = df['MA20'] - (df['std'] * 2)
    
    # 3. MACD
    df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
    df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = df['EMA12'] - df['EMA26']
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['Signal']
    
    # 4. RSI (14일)
    delta = df['Close'].diff(1)
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    return df

# --- 입력 창 ---
with st.sidebar:
    st.header("설정")
    stock_name = st.text_input("종목명", "삼성전자")
    period_days = st.slider("분석 기간 (일)", 100, 500, 200)
    st.info("기간이 길수록 이평선 분석이 정확해집니다.")

if stock_name:
    try:
        # 종목코드 찾기
        krx = fdr.StockListing('KRX')
        target = krx[krx['Name'] == stock_name]
        
        if target.empty:
            st.error("정확한 종목명을 입력해주세요.")
        else:
            code = target.iloc[0]['Code']
            
            # 데이터 수집 (기간 넉넉하게)
            start_dt = datetime.datetime.now() - datetime.timedelta(days=period_days*1.5)
            df = fdr.DataReader(code, start_dt)
            
            if len(df) < 60:
                st.warning("데이터가 부족하여 분석할 수 없습니다.")
            else:
                # 지표 계산
                df = calculate_technical_indicators(df)
                latest = df.iloc[-1]
                prev = df.iloc[-2]
                
                # --- [1] 헤드라인 (가격 정보) ---
                change = latest['Close'] - prev['Close']
                rate = (change / prev['Close']) * 100
                color = "red" if change > 0 else "blue"
                
                st.metric(label=f"{stock_name} 현재가", 
                          value=f"{latest['Close']:,}원", 
                          delta=f"{change:,.0f}원 ({rate:.2f}%)")
                
                # --- [2] 차트 시각화 (탭으로 구분) ---
                tab1, tab2 = st.tabs(["기본 차트 (MA+Bollinger)", "보조지표 (MACD+RSI)"])
                
                with tab1:
                    st.line_chart(df[['Close', 'MA20', 'MA60', 'Upper_Band', 'Lower_Band']].tail(period_days))
                    st.caption("파란색: 주가 / 밴드: 볼린저 밴드")
                
                with tab2:
                    st.subheader("MACD & Signal")
                    st.line_chart(df[['MACD', 'Signal']].tail(period_days))
                    st.subheader("RSI")
                    st.line_chart(df[['RSI']].tail(period_days))

                # --- [3] 종합 AI 진단 리포트 (선생님이 원하신 기능!) ---
                st.markdown("### 🤖 종합 기술적 진단 리포트")
                
                diagnosis = []
                
                # 1. 추세 분석 (이평선)
                if latest['Close'] > latest['MA20'] and latest['MA20'] > latest['MA60']:
                    diagnosis.append("✅ **[강한 상승 추세]** 주가가 20일, 60일 이평선 위에 정배열되어 있습니다. 매수 심리가 강합니다.")
                elif latest['Close'] < latest['MA20'] and latest['MA20'] < latest['MA60']:
                    diagnosis.append("⚠️ **[하락 추세]** 역배열 상태입니다. 바닥을 확인하기 전까지 보수적 접근이 필요합니다.")
                elif latest['MA5'] > latest['MA20'] and prev['MA5'] <= prev['MA20']:
                    diagnosis.append("🔥 **[골든 크로스]** 5일선이 20일선을 돌파했습니다! 단기 급등 신호일 수 있습니다.")
                elif latest['MA5'] < latest['MA20'] and prev['MA5'] >= prev['MA20']:
                    diagnosis.append("❄️ **[데드 크로스]** 5일선이 20일선을 하향 돌파했습니다. 단기 조정에 주의하세요.")

                # 2. 변동성 분석 (볼린저 밴드)
                if latest['Close'] > latest['Upper_Band']:
                    diagnosis.append("🔴 **[과열권]** 주가가 볼린저 밴드 상단을 뚫었습니다. 단기적으로 조정이 올 수 있습니다.")
                elif latest['Close'] < latest['Lower_Band']:
                    diagnosis.append("🔵 **[침체권]** 주가가 볼린저 밴드 하단을 뚫었습니다. 기술적 반등이 기대됩니다.")
                elif (latest['Upper_Band'] - latest['Lower_Band']) < (prev['Upper_Band'] - prev['Lower_Band']):
                    diagnosis.append("⚡ **[에너지 응축]** 밴드 폭이 좁아지고 있습니다. 조만간 큰 방향성(위든 아래든)이 나올 전조입니다.")

                # 3. 모멘텀 분석 (MACD, RSI)
                if latest['MACD'] > latest['Signal']:
                    diagnosis.append("📈 **[MACD 매수 신호]** MACD가 시그널 선 위에 있습니다. 상승 모멘텀이 유지 중입니다.")
                if latest['RSI'] >= 70:
                    diagnosis.append(f"🚨 **[RSI 과매수]** RSI가 {latest['RSI']:.1f}입니다. 차익 실현 매물이 나올 수 있습니다.")
                elif latest['RSI'] <= 30:
                    diagnosis.append(f"💎 **[RSI 과매도]** RSI가 {latest['RSI']:.1f}입니다. 저가 매수 기회일 수 있습니다.")

                # 4. 거래량 분석
                vol_ratio = (latest['Volume'] / df['Volume'].rolling(20).mean().iloc[-1]) * 100
                if vol_ratio > 200:
                    diagnosis.append(f"📢 **[거래량 폭발]** 평소 거래량의 {vol_ratio:.0f}%가 터졌습니다. 세력의 개입이나 이슈가 발생했습니다.")

                # 결과 출력
                if not diagnosis:
                    st.info("특별한 기술적 특이사항이 없는 평범한 흐름입니다.")
                else:
                    for msg in diagnosis:
                        st.write(msg)

    except Exception as e:
        st.error(f"분석 중 오류 발생: {e}")
