import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import datetime

st.set_page_config(page_title="종합 차트 분석", page_icon="📈", layout="wide")
st.title("📈 종합 기술적 분석 센터")

# --- 보조지표 계산 함수 ---
def calculate_technical_indicators(df):
    df = df.copy()
    
    # 1. 이동평균선
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    
    # 2. 볼린저 밴드 (20일, 승수2)
    df['std'] = df['Close'].rolling(window=20).std()
    df['Upper_Band'] = df['MA20'] + (df['std'] * 2)
    df['Lower_Band'] = df['MA20'] - (df['std'] * 2)
    
    # 3. MACD
    df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
    df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = df['EMA12'] - df['EMA26']
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    # 4. RSI (14일)
    delta = df['Close'].diff(1)
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    return df

# --- 사이드바 설정 ---
with st.sidebar:
    st.header("설정")
    stock_name = st.text_input("종목명", "삼성전자")
    period_days = st.slider("분석 기간 (일)", 100, 500, 200)

if stock_name:
    try:
        # 종목코드 찾기
        krx = fdr.StockListing('KRX')
        target = krx[krx['Name'] == stock_name]
        
        if target.empty:
            st.error("정확한 종목명을 입력해주세요.")
        else:
            code = target.iloc[0]['Code']
            
            # 데이터 수집
            start_dt = datetime.datetime.now() - datetime.timedelta(days=period_days*1.5)
            df = fdr.DataReader(code, start_dt)
            
            if len(df) < 60:
                st.warning("데이터가 부족하여 분석할 수 없습니다.")
            else:
                # 지표 계산
                df = calculate_technical_indicators(df)
                latest = df.iloc[-1]
                prev = df.iloc[-2]
                
                # --- [1] 헤드라인 ---
                change = latest['Close'] - prev['Close']
                rate = (change / prev['Close']) * 100
                st.metric(label=f"{stock_name} 현재가", 
                          value=f"{latest['Close']:,}원", 
                          delta=f"{change:,.0f}원 ({rate:.2f}%)")
                
                # --- [2] 차트 ---
                tab1, tab2 = st.tabs(["기본 차트 (MA+Bollinger)", "보조지표 (MACD+RSI)"])
                with tab1:
                    st.line_chart(df[['Close', 'MA20', 'MA60', 'Upper_Band', 'Lower_Band']].tail(period_days))
                    st.caption("파란색: 주가 / 밴드: 볼린저 밴드")
                with tab2:
                    st.subheader("MACD & Signal")
                    st.line_chart(df[['MACD', 'Signal']].tail(period_days))
                    st.subheader("RSI")
                    st.line_chart(df[['RSI']].tail(period_days))

                # --- [3] AI 진단 리포트 ---
                st.markdown("### 🤖 AI 기술적 진단 리포트")
                diagnosis = []
                
                # 이동평균선 분석
                if latest['Close'] > latest['MA20'] and latest['MA20'] > latest['MA60']:
                    diagnosis.append("✅ **[상승 추세]** 주가 > 20일선 > 60일선 정배열 상태입니다. 매수세가 강합니다.")
                elif latest['MA5'] > latest['MA20'] and prev['MA5'] <= prev['MA20']:
                    diagnosis.append("🔥 **[골든 크로스]** 5일선이 20일선을 돌파했습니다! 단기 급등 신호일 수 있습니다.")
                elif latest['MA5'] < latest['MA20'] and prev['MA5'] >= prev['MA20']:
                    diagnosis.append("❄️ **[데드 크로스]** 5일선이 20일선을 하향 돌파했습니다. 조심하세요.")

                # 볼린저 밴드 분석
                if latest['Close'] > latest['Upper_Band']:
                    diagnosis.append("🔴 **[과열권]** 주가가 밴드 상단을 뚫었습니다. 단기 조정 가능성이 높습니다.")
                elif latest['Close'] < latest['Lower_Band']:
                    diagnosis.append("🔵 **[침체권]** 주가가 밴드 하단을 뚫었습니다. 반등이 기대됩니다.")

                # RSI 분석
                if latest['RSI'] >= 70:
                    diagnosis.append(f"🚨 **[RSI 과매수 ({latest['RSI']:.1f})]** 너무 많이 올랐습니다. 차익 실현 매물을 주의하세요.")
                elif latest['RSI'] <= 30:
                    diagnosis.append(f"💎 **[RSI 과매도 ({latest['RSI']:.1f})]** 공포에 질려 너무 많이 팔렸습니다. 저점 매수 기회입니다.")

                # 결과 출력
                if not diagnosis:
                    st.info("특이사항 없이 무난한 흐름입니다.")
                else:
                    for msg in diagnosis:
                        st.write(msg)

    except Exception as e:
        st.error(f"분석 중 오류 발생: {e}")
