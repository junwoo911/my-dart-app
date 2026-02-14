import streamlit as st
import OpenDartReader
import pandas as pd
import io
import zipfile
import re
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- [필수] 사이드바 접기 설정 ---
st.set_page_config(
    page_title="보고서 다운로드", 
    page_icon="📥", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- [핵심 패치] DART 서버 접속 뚫기 (User-Agent 위장) ---
# 이 부분이 없으면 해외 서버에서 접속 시 무한 로딩이 걸립니다.
def patch_request_headers():
    default_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': '*/*',
        'Connection': 'keep-alive'
    }
    return default_headers

# --- 1. API 키 설정 ---
st.title("📥 기업 보고서 즉시 다운로드")

if 'api_key' not in st.session_state:
    if "dart_api_key" in st.secrets:
        st.session_state.api_key = st.secrets["dart_api_key"]
    else:
        st.error("API 키가 없습니다. secrets.toml을 확인해주세요.")
        st.stop()

api_key = st.session_state.api_key

# --- 2. DART 객체 생성 (안전장치 추가) ---
@st.cache_resource
def get_dart_system(key):
    # DART 객체 생성 시에는 별도 헤더 설정이 어려우므로, 
    # 첫 실행 시 데이터 다운로드를 위해 안내 메시지를 띄웁니다.
    return OpenDartReader(key)

# --- 3. 보고서 목록 조회 (강제 타임아웃 및 재시도 적용) ---
@st.cache_data(ttl=3600)
def fetch_report_list_safe(corp_name, start_date, end_date):
    # 1. OpenDartReader 인스턴스 가져오기
    dart = get_dart_system(api_key)
    
    # 2. 직접 코드를 찾아서 요청 (라이브러리 내부 로직이 멈출 수 있어서 우회)
    # GKL 같은 영문명이나 사명 검색을 위해 라이브러리 기능 시도
    try:
        # User-Agent 강제 적용을 위해 requests 라이브러리 전역 설정 업데이트
        requests.utils.default_headers().update(patch_request_headers())
        
        # 목록 가져오기
        return dart.list(corp_name, start=start_date, end=end_date, kind='A')
    except Exception as e:
        # 혹시 라이브러리가 멈추면 에러를 반환
        return None

# --- 4. 텍스트 변환 함수 ---
def extract_ai_friendly_text(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    for s in soup(["script", "style", "head", "svg", "img"]):
        s.decompose()
    for table in soup.find_all("table"):
        rows = []
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if headers:
            rows.append("| " + " | ".join(headers) + " |")
            rows.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            if cells:
                rows.append("| " + " | ".join(cells) + " |")
        table_md = "\n" + "\n".join(rows) + "\n"
        table.replace_with(table_md)
    text = soup.get_text(separator="\n")
    return re.sub(r'\n\s*\n+', '\n\n', text).strip()

# --- 5. UI 구성 ---
with st.container(border=True):
    col_input, col_btn = st.columns([4, 1])
    with col_input:
        corp_name = st.text_input("회사명 입력", placeholder="예: GKL, 삼성전자", label_visibility="collapsed")
    with col_btn:
        btn_search = st.button("검색", type="primary", use_container_width=True)

    with st.expander("📅 기간 및 보고서 종류 (기본값: 최근 1년, 사업보고서)", expanded=True):
        opt_col1, opt_col2, opt_col3 = st.columns([1, 1, 2])
        with opt_col1:
            start_year = st.number_input("시작 연도", min_value=1990, max_value=2030, value=2024, step=1)
        with opt_col2:
            end_year = st.number_input("종료 연도", min_value=1990, max_value=2030, value=2025, step=1)
        with opt_col3:
            report_options = ["1분기보고서", "반기보고서", "3분기보고서", "사업보고서"]
            selected_types = st.multiselect("종류", report_options, default=["사업보고서"], label_visibility="collapsed")

# --- 6. 실행 로직 ---
if btn_search or ('target_df' in st.session_state and st.session_state.target_df is not None):
    if btn_search:
        if not corp_name:
            st.warning("회사명을 입력해주세요.")
            st.stop()
        
        start_date = f"{start_year}0101"
        end_date = f"{end_year}1231"
        
        # 스피너에 메시지 구체화
        with st.spinner(f"📡 '{corp_name}' 접속 시도 중... (첫 검색은 20~30초 걸릴 수 있습니다)"):
            try:
                # 타임아웃 걸린 요청 실행
                df = fetch_report_list_safe(corp_name, start_date, end_date)
                
                if df is not None and len(df) > 0:
                    conditions = []
                    if "사업보고서" in selected_types: conditions.append(df['report_nm'].str.contains("사업보고서"))
                    if "반기보고서" in selected_types: conditions.append(df['report_nm'].str.contains("반기보고서"))
                    if "1분기보고서" in selected_types:
                        conditions.append((df['report_nm'].str.contains("분기보고서")) & (df['report_nm'].str.contains(r"\.03|\.3월", regex=True)))
                    if "3분기보고서" in selected_types:
                        conditions.append((df['report_nm'].str.contains("분기보고서")) & (df['report_nm'].str.contains(r"\.09|\.9월", regex=True)))

                    if conditions:
                        final_mask = pd.concat(conditions, axis=1).any(axis=1)
                        filtered_df = df[final_mask].copy().reset_index(drop=True)
                    else:
                        filtered_df = pd.DataFrame()

                    st.session_state.target_df = filtered_df
                    st.session_state.current_corp = corp_name
                else:
                    st.error("❌ 검색 결과가 없거나 DART 서버 응답이 지연되고 있습니다.")
                    st.session_state.target_df = None
            except Exception as e:
                st.error(f"오류 발생: {e}")

    # 결과 표시 및 다운로드
    if 'target_df' in st.session_state and st.session_state.target_df is not None:
        df = st.session_state.target_df
        corp_name_fixed = st.session_state.get('current_corp', corp_name)
        
        st.divider()
        st.subheader(f"✅ 검색 결과 ({len(df)}건)")
        st.dataframe(df[['rcept_dt', 'report_nm']], use_container_width=True, hide_index=True)
        
        if len(df) > 0:
            if st.button("🚀 전체 다운로드 (ZIP)", type="primary", use_container_width=True):
                zip_buffer = io.BytesIO()
                progress_bar = st.progress(0)
                status_text = st.empty()
                total = len(df)
                
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for idx, row in df.iterrows():
                        report_name = row['report_nm']
                        file_name = f"{corp_name_fixed}_{report_name}.txt"
                        file_name = re.sub(r'[\\/*?:"<>|]', "", file_name)
                        
                        status_text.info(f"⏳ ({idx+1}/{total}) {file_name} 추출 중...")
                        
                        try:
                            # 개별 파일 다운로드 시에도 헤더 적용
                            url = f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={api_key}&rcept_no={row['rcept_no']}"
                            # requests.get 사용 시 headers 추가
                            res = requests.get(url, timeout=15, headers=patch_request_headers())
                            
                            with zipfile.ZipFile(io.BytesIO(res.content)) as z_orig:
                                target_file = max(z_orig.infolist(), key=lambda f: f.file_size).filename
                                raw_data = z_orig.read(target_file)
                                try: content_html = raw_data.decode('utf-8')
                                except: content_html = raw_data.decode('euc-kr', 'ignore')
                                clean_text = extract_ai_friendly_text(content_html)
                                
                                final_content = f"### {corp_name_fixed} {report_name} ###\n접수일: {row['rcept_dt']}\n\n{clean_text}"
                                zip_file.writestr(file_name, final_content)
                        except Exception as e:
                            st.error(f"실패: {file_name}")
                        progress_bar.progress((idx + 1) / total)

                status_text.success("완료! 버튼을 눌러 저장하세요.")
                st.download_button(
                    label="💾 ZIP 파일 저장하기",
                    data=zip_buffer.getvalue(),
                    file_name=f"{corp_name_fixed}_Reports.zip",
                    mime="application/zip",
                    type="primary",
                    use_container_width=True
                )
