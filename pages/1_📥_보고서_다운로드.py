import streamlit as st
import OpenDartReader
import pandas as pd
import io
import zipfile
import re
import datetime
import requests
from bs4 import BeautifulSoup

st.set_page_config(page_title="AI 공시 분석 센터", page_icon="📥", layout="wide")
st.title("📥 AI 분석용 보고서 추출기 (Structured Text)")

# --- [패치 1] API 키 세션 관리 및 캐싱 ---
api_key = st.session_state.get("api_key")
if not api_key:
    if "dart_api_key" in st.secrets: api_key = st.secrets["dart_api_key"]
    else:
        st.error("⚠️ Home에서 API 키를 입력해주세요.")
        st.stop()

# --- [패치 2] 검색 결과 캐싱 (속도 향상의 핵심) ---
@st.cache_data(show_spinner=False, ttl=3600) # 1시간 동안 검색 결과 기억
def fetch_report_list(_dart, corp_name, start_date, end_date):
    # A(정기공시) 유형만 가져오도록 API 레벨에서 필터링
    return _dart.list(corp_name, start=start_date, end=end_date, kind='A')

# --- 내부 함수: 표 구조 유지 추출 ---
def extract_ai_friendly_text(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    for s in soup(["script", "style", "head", "title"]): s.decompose()
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            rows.append(" | ".join(cells))
        table.replace_with("\n" + "\n".join(rows) + "\n")
    text = soup.get_text(separator="\n")
    return re.sub(r'\n\s*\n+', '\n\n', text)

# --- 사이드바 검색 폼 ---
with st.sidebar:
    st.header("🔍 검색 설정")
    corp_name = st.text_input("회사명", "삼성전자")
    curr_year = datetime.datetime.now().year
    years = st.slider("조회 기간", 2015, curr_year, (curr_year-2, curr_year))
    target_reports = st.multiselect("종류", ["사업보고서", "반기보고서", "분기보고서"], default=["사업보고서"])
    submit = st.button("보고서 목록 가져오기")

# --- 검색 실행부 ---
if submit:
    try:
        dart = OpenDartReader(api_key)
        start_date, end_date = f"{years[0]}0101", f"{years[1]}1231"
        
        # [패치 3] 진행 상태 시각화
        with st.status(f"📡 DART 서버에서 '{corp_name}' 목록 조회 중...", expanded=True) as status:
            df = fetch_report_list(dart, corp_name, start_date, end_date)
            
            if df is not None and len(df) > 0:
                status.update(label="🎯 조건에 맞는 보고서 필터링 중...", state="running")
                df = df[df['report_nm'].str.contains('|'.join(target_reports))]
                df = df.reset_index(drop=True)
                st.session_state.reports_df = df
                status.update(label=f"✅ {len(df)}건의 보고서를 찾았습니다!", state="complete", expanded=False)
            else:
                status.update(label="❌ 조회 결과가 없습니다.", state="error")
                st.session_state.reports_df = None
                
    except Exception as e: 
        st.error(f"DART 접속 에러: {e}")

# --- 결과 노출 및 추출 ---
if 'reports_df' in st.session_state and st.session_state.reports_df is not None:
    reports = st.session_state.reports_df
    st.dataframe(reports[['rcept_dt', 'report_nm', 'corp_name']], use_container_width=True)
    
    if st.button("🚀 AI용 텍스트 파일 생성 (전체 통합)"):
        combined_text = f"### {corp_name} AI 분석용 통합 데이터 ({years[0]}~{years[1]}) ###\n\n"
        progress = st.progress(0.0)
        status_msg = st.empty()
        
        total_len = len(reports)
        for i, (idx, row) in enumerate(reports.iterrows()):
            rcept_no = row['rcept_no']
            report_nm = row['report_nm']
            status_msg.info(f"⏳ ({i+1}/{total_len}) {report_nm} 데이터 추출 중...")
            
            try:
                url = f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={api_key}&rcept_no={rcept_no}"
                res = requests.get(url, timeout=15)
                
                with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                    # 가장 큰 파일이 메인 보고서일 확률이 높음
                    target_file = max(z.infolist(), key=lambda f: f.file_size).filename
                    raw_content = z.read(target_file)
                    
                    try: content = raw_content.decode('utf-8')
                    except: content = raw_content.decode('euc-kr', 'ignore')
                    
                    refined_text = extract_ai_friendly_text(content)
                    
                    combined_text += f"\n\n{'='*50}\nREPORT: {report_nm} ({row['rcept_dt']})\n{'='*50}\n\n"
                    combined_text += refined_text
                    
            except Exception as e:
                combined_text += f"\n\n[오류: {report_nm} 추출 실패 - {e}]\n"
            
            progress.progress((i + 1) / total_len)
        
        status_msg.success("✅ 모든 데이터 추출 및 구조화 완료!")
        st.download_button(
            label="📄 AI 분석용 통합 텍스트 다운로드",
            data=combined_text,
            file_name=f"{corp_name}_AI_Deep_Context.txt",
            mime="text/plain"
        )
