import streamlit as st
import OpenDartReader
import pandas as pd
import io
import zipfile
import re
import datetime
import requests
import time
from bs4 import BeautifulSoup

st.set_page_config(page_title="AI 공시 분석 센터", page_icon="📥", layout="wide")
st.title("📥 AI 분석용 보고서 추출기 (Stable Version)")

# --- [패치 1] DART 객체 생성 캐싱 (매번 연결하지 않도록 설정) ---
@st.cache_resource(show_spinner="📡 DART 서버와 보안 연결 설정 중...")
def get_dart_instance(api_key):
    # 타임아웃 문제를 방지하기 위해 연결 테스트를 겸함
    return OpenDartReader(api_key)

api_key = st.session_state.get("api_key")
if not api_key:
    if "dart_api_key" in st.secrets: api_key = st.secrets["dart_api_key"]
    else:
        st.error("⚠️ Home에서 API 키를 입력해주세요.")
        st.stop()

# --- [패치 2] 목록 조회 시 재시도 로직 (Retry Logic) ---
@st.cache_data(show_spinner=False, ttl=3600)
def fetch_report_list_stable(_api_key, corp_name, start_date, end_date):
    dart = OpenDartReader(_api_key)
    max_retries = 3
    for i in range(max_retries):
        try:
            # 실질적인 데이터 호출
            return dart.list(corp_name, start=start_date, end=end_date, kind='A')
        except Exception as e:
            if i < max_retries - 1:
                time.sleep(2) # 2초 쉬고 다시 시도
                continue
            else:
                raise e # 3번 다 실패하면 에러 노출

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
    return re.sub(r'\n\s*\n+', '\n\n', soup.get_text(separator="\n"))

# --- 사이드바 검색 ---
with st.sidebar:
    st.header("🔍 검색 설정")
    corp_name = st.text_input("회사명", "삼성전자")
    curr_year = datetime.datetime.now().year
    years = st.slider("조회 기간", 2015, curr_year, (curr_year-2, curr_year))
    target_reports = st.multiselect("종류", ["사업보고서", "반기보고서", "분기보고서"], default=["사업보고서"])
    submit = st.button("보고서 목록 가져오기")

if submit:
    try:
        start_date, end_date = f"{years[0]}0101", f"{years[1]}1231"
        
        with st.status(f"📡 DART 서버(KR)에 접속 시도 중... (시도 1/3)", expanded=True) as status:
            df = fetch_report_list_stable(api_key, corp_name, start_date, end_date)
            
            if df is not None and len(df) > 0:
                status.update(label="🎯 데이터 필터링 중...", state="running")
                df = df[df['report_nm'].str.contains('|'.join(target_reports))]
                df = df.reset_index(drop=True)
                st.session_state.reports_df = df
                status.update(label=f"✅ {len(df)}건의 보고서를 찾았습니다!", state="complete", expanded=False)
            else:
                status.update(label="❌ 조회 결과가 없습니다.", state="error")
                st.session_state.reports_df = None
                
    except Exception as e: 
        st.error(f"❌ DART 서버 응답 지연: 현재 DART 서버 접속자가 많아 연결이 원활하지 않습니다. 잠시 후 다시 시도해주세요. \n\n(상세 에러: {e})")

# --- 추출 및 다운로드 (이전과 동일) ---
if 'reports_df' in st.session_state and st.session_state.reports_df is not None:
    reports = st.session_state.reports_df
    st.dataframe(reports[['rcept_dt', 'report_nm', 'corp_name']], use_container_width=True)
    
    if st.button("🚀 AI용 텍스트 파일 생성"):
        combined_text = f"### {corp_name} AI 분석 데이터 ###\n\n"
        progress = st.progress(0.0)
        status_msg = st.empty()
        
        total_len = len(reports)
        for i, (idx, row) in enumerate(reports.iterrows()):
            rcept_no = row['rcept_no']
            status_msg.info(f"⏳ ({i+1}/{total_len}) {row['report_nm']} 데이터 추출 중...")
            
            try:
                # 텍스트 추출 시에도 timeout 설정
                url = f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={api_key}&rcept_no={rcept_no}"
                res = requests.get(url, timeout=30) # 30초 넉넉하게 대기
                
                with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                    target_file = max(z.infolist(), key=lambda f: f.file_size).filename
                    raw_content = z.read(target_file)
                    try: content = raw_content.decode('utf-8')
                    except: content = raw_content.decode('euc-kr', 'ignore')
                    
                    combined_text += f"\n\n{'='*50}\nREPORT: {row['report_nm']} ({row['rcept_dt']})\n{'='*50}\n\n"
                    combined_text += extract_ai_friendly_text(content)
            except:
                combined_text += f"\n\n[오류: {row['report_nm']} 추출 실패]\n"
            
            progress.progress((i + 1) / total_len)
        
        status_msg.success("✅ 추출 완료!")
        st.download_button("📄 AI 분석용 텍스트 다운로드", combined_text, f"{corp_name}_AI_Deep_Context.txt")
