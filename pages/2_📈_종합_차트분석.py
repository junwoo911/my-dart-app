import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import datetime
import yfinance as yf

st.set_page_config(page_title="종합 차트 분석", page_icon="📈", layout="wide")
st.title("📈 종합 기술적 분석 센터")

# --- [핵심] 주가 데이터 수집 함수 (하이브리드 엔진) ---
@st.cache_data
def get_stock_data(stock_name, period_days):
    df = pd.DataFrame()
    code = ""
    source = ""
    
    try:
        # 1. 종목 코드 찾기
        krx = fdr.StockListing('KRX')
        target = krx[krx['Name'] == stock_name]
        
        if target.empty:
            return None, None, "종목명을 정확히 입력해주세요."
        
        code = target.iloc[0]['Code']
        
        # 2. 날짜 설정
        start_dt = datetime.datetime.now() - datetime.timedelta(days=period_days*2)
        
        # --- 시도 1: 야후 파이낸스 (IP 차단 회피용) ---
        try:
            candidates = [f"{code}.KS", f"{code}.KQ"]
            for ticker in candidates:
                # auto_adjust=True: 액면분할 등 자동 수정
                temp_df = yf.download(ticker, start=start_dt, progress=False, auto_adjust=True)
                
                if not temp_df.empty:
                    df = temp_df
                    source = "Yahoo Finance"
                    # [중요] yfinance 최신 버전 컬럼 문제 해결 (MultiIndex 해제)
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    break
        except:
            pass

        # --- 시도 2: FinanceDataReader (야후 실패 시 백업) ---
        if df.empty:
            try:
                df = fdr.DataReader(code, start_dt)
                source = "Naver Finance (Backup)"
            except:
                pass
        
        # 3. 데이터 검증
        if df.empty:
            return None, None, "데이터를 가져올 수 없습니다. (상장폐지 또는 통신 에러)"
            
        # 4. 결측치 제거 및 데이터 최소 개수 확인
        df = df.dropna()
        if len(df) < 20:
            return None, None, "분석할 데이터가 너무 적습니다. (최근 상장주 등)"
            
        return df, code, source
        
    except Exception as e:
        return None, None, f"시스템 에러 발생: {e}"

# --- 보조지표 계산 ---
def calculate_technical_indicators(df):
    df = df.copy()
    
    # 데이터가 Series인지 확인하고 처리
    close = df['Close']
    
    # 1. 이동평균선
    df['MA5'] = close.rolling(window=5).mean()
    df['MA20'] = close.rolling(window=20).mean()
    df['MA60'] = close.rolling(window=60).mean()
    
    # 2. 볼린저 밴드
    df['std'] = close.rolling(window=20).std()
    df['Upper_Band'] = df['MA20'] + (df['std'] * 2)
    df['Lower_Band'] = df['MA20'] - (df['std'] * 2)
    
    # 3. MACD
    df['EMA12'] = close.ewm(span=12, adjust=False).mean()
    df['EMA26'] = close.ewm(span=26, adjust=False).mean()
    df['MACD'] = df['EMA12'] - df['EMA26']
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    # 4. RSI
    delta = close.diff(1)
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
        df, code, source = get_stock_data(stock_name, period_days)
        
        if df is None:
            st.error(f"❌ 오류: {source}") # source 변수에 에러 메시지가 담김
        else:
            # 지표 계산
            try:
                df = calculate_technical_indicators(df)
                
                latest = df.iloc[-1]
                prev = df.iloc[-2]
                
                # 1. 헤드라인
                change = latest['Close'] - prev['Close']
                rate = (change / prev['Close']) * 100
                st.metric(label=f"{stock_name} ({code})", 
                          value=f"{latest['Close']:,.0f}원", 
                          delta=f"{change:,.0f}원 ({rate:.2f}%)")
                st.caption(f"데이터 출처: {source}")
                
                # 2. 차트
                tab1, tab2 = st.tabs(["기본 차트", "보조지표"])
                with tab1:
                    st.line_chart(df[['Close', 'MA20', 'Upper_Band', 'Lower_Band']].tail(period_days), color=["#0000FF", "#FFA500", "#CCCCCC", "#CCCCCC"])
                with tab2:
                    st.line_chart(df[['MACD', 'Signal', 'RSI']].tail(period_days))

                # 3. AI 진단
                st.divider()
                st.subheader("🤖 AI 기술적 진단 리포트")
                
                diagnosis = []
                
                # 이평선
                if latest['Close'] > latest['MA20'] and latest['MA20'] > latest['MA60']:
                    diagnosis.append("✅ **[상승 정배열]** 주가 > 20일선 > 60일선 정배열 상태입니다. 매수세가 강합니다.")
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
                
                if not diagnosis:
                    st.info("특이사항 없이 무난한 흐름을 보이고 있습니다.")
                else:
                    for msg in diagnosis:
                        st.write(msg)

            except Exception as e:
                st.error(f"지표 계산 중 오류 발생: {e}")
                st.write("데이터 원본:", df.tail()) # 디버깅용 데이터 표시
