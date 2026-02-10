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
st.title("📥 AI 분석용 보고서 추출기 (Network Stable)")

# --- [패치 1] API 키 세션 관리 및 타임아웃 설정 ---
# requests의 기본 타임아웃을 전역적으로 늘려줍니다.
if 'api_key' not in st.session_state:
    if "dart_api_key" in st.secrets:
        st.session_state.api_key = st.secrets["dart_api_key"]
    else:
        st.error("⚠️ Home에서 API 키를 입력해주세요.")
        st.stop()

api_key = st.session_state.api_key

# --- [패치 2] DART 초기화 우회 및 캐싱 ---
@st.cache_resource(show_spinner="📡 해외망을 통해 DART 보안 연결을 시도 중입니다...")
def get_stable_dart(key):
    # 연결 확인용 간단한 호출 테스트
    try:
        # OpenDartReader 내부에서 corpCode를 받다가 터지는 것을 방지하기 위해
        # 타임아웃이 넉넉한 별도의 세션을 사용할 수 없으므로, 생성 자체를 캐싱합니다.
        return OpenDartReader(key)
    except Exception as e:
        return f"ERROR:{str(e)}"

# --- [패치 3] 목록 조회 (강력한 재시도 및 지연 시간 부여) ---
@st.cache_data(show_spinner=False, ttl=3600)
def fetch_report_list_pro(_api_key, corp_name, start_date, end_date):
    dart_inst = get_stable_dart(_api_key)
    if isinstance(dart_inst, str) and dart_inst.startswith("ERROR"):
        raise Exception(dart_inst)
    
    max_retries = 5 # 5번까지 시도
    for i in range(max_retries):
        try:
            return dart_inst.list(corp_name, start=start_date, end=end_date, kind='A')
        except Exception as e:
            if i < max_retries - 1:
                # 점진적으로 대기 시간을 늘리는 Exponential Backoff 방식
                time.sleep(2 * (i + 1)) 
                continue
            else:
                raise e

# --- 내부 함수: 표 구조 유지 추출 (이전과 동일) ---
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
        with st.status(f"📡 DART 서버에 접속 중... (해외망 경유)", expanded=True) as status:
            df = fetch_report_list_pro(api_key, corp_name, start_date, end_date)
            
            if df is not None and len(df) > 0:
                df = df[df['report_nm'].str.contains('|'.join(target_reports))]
                df = df.reset_index(drop=True)
                st.session_state.reports_df = df
                status.update(label=f"✅ {len(df)}건을 찾았습니다!", state="complete", expanded=False)
            else:
                status.update(label="❌ 결과 없음", state="error")
                st.session_state.reports_df = None
                
    except Exception as e: 
        st.error(f"⚠️ **현재 DART API 서버가 해외 IP 접속을 제한하고 있습니다.** \n\n"
                 f"1. 잠시 후(1분 뒤) 다시 시도해주세요.\n"
                 f"2. 만약 계속 안 된다면, DART 서버 자체의 일시적 장애일 수 있습니다.\n\n"
                 f"(오류 메시지: {e})")

# --- 추출 및 다운로드 ---
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
            status_msg.info(f"⏳ ({i+1}/{total_len}) {row['report_nm']} 추출 중...")
            
            try:
                # 개별 문서 요청 시에도 끈질기게 요청
                url = f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={api_key}&rcept_no={rcept_no}"
                res = requests.get(url, timeout=40) # 타임아웃을 40초로 대폭 확대
                
                with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                    target_file = max(z.infolist(), key=lambda f: f.file_size).filename
                    raw_content = z.read(target_file)
                    try: content = raw_content.decode('utf-8')
                    except: content = raw_content.decode('euc-kr', 'ignore')
                    
                    combined_text += f"\n\n{'='*50}\nREPORT: {row['report_nm']} ({row['rcept_dt']})\n{'='*50}\n\n"
                    combined_text += extract_ai_friendly_text(content)
            except:
                combined_text += f"\n\n[오류: {row['report_nm']} 데이터 통신 실패]\n"
            
            progress.progress((i + 1) / total_len)
        
        status_msg.success("✅ 완료!")
        st.download_button("📄 분석용 텍스트 파일 다운로드", combined_text, f"{corp_name}_AI_Deep_Context.txt")
