import streamlit as st

st.set_page_config(
    page_title="DART & Stock AI",
    page_icon="🤖",
    layout="centered"
)

st.title("🤖 DART & 주식 통합 솔루션")
st.markdown("""
### 환영합니다! 👋
이 앱은 **재무제표 수집**과 **주가 기술적 분석**을 분리하여 전문적으로 제공합니다.

**좌측 사이드바(> 화살표)**를 열어서 원하시는 메뉴를 선택하세요.
1. **📥 보고서 다운로드:** DART 원본 파일 수집
2. **📈 종합 차트 분석:** 주가 심층 진단
""")

# --- API 키 통합 관리 ---
st.info("🔐 서비스 이용을 위해 API 키를 설정해주세요.")

# 세션 상태 초기화
if "api_key" not in st.session_state:
    st.session_state.api_key = ""

# Secrets에 있으면 자동 로드
if "dart_api_key" in st.secrets:
    st.session_state.api_key = st.secrets["dart_api_key"]
    st.success("Secrets에서 API 키를 불러왔습니다! 왼쪽 메뉴를 선택하세요.")
else:
    # 없으면 입력 받기
    key_input = st.text_input("OpenDART API Key", value=st.session_state.api_key, type="password")
    if key_input:
        st.session_state.api_key = key_input
        st.success("API 키 저장 완료! 왼쪽 메뉴를 선택하세요.")
