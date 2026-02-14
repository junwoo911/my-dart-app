import streamlit as st
import OpenDartReader
import pandas as pd
import io
import zipfile
import re
import datetime
import requests
from bs4 import BeautifulSoup

# --- [핵심] 1. 페이지 설정: 사이드바 'collapsed'(접힘)으로 시작 ---
st.set_page_config(
    page_title="기업 보고서 다운로드", 
    page_icon="📥", 
    layout="wide",
    initial_sidebar_state="collapsed" # 앱 실행 시 사이드바를 강제로 접습니다
)

# --- 2. 타이틀 바로 배치 (메인화면 진입 즉시 보임) ---
st.title("📥 기업 보고서 즉시 다운로드")

# --- 3. API 키 설정 ---
if 'api_key' not in st.session_state:
    if "dart_api_key" in st.secrets:
        st.session_state.api_key = st.secrets["dart_api_key"]
    else:
        st.error("⚠️ API 키가 설정되지 않았습니다. (secrets.toml 확인 필요)")
        st.stop()

api_key = st.session_state.api_key

# --- 4. 기능 함수들 (DART 연결, 텍스트 변환) ---
@st.cache_resource
def get_dart_system(key):
    return OpenDartReader(key)

@st.cache_data(ttl=3600)
def fetch_report_list_clean(corp_name, start_date, end_date):
    dart = get_dart_system(api_key)
    return dart.list(corp_name, start=start_date, end=end_date, kind='A')

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

# --- 5. 화면 UI 구성 (컨테이너로 깔끔하게) ---
with st.container(border=True):
    col_input, col_btn = st.columns([4, 1])
    
    with col_input:
        # 엔터 키 입력 시 처리를 위해 form 대신 단순 입력창 사용하되, 직관적 배치
        corp_name = st.text_input("회사명 입력", placeholder="예: 삼성전자", label_visibility="collapsed")
    
    with col_btn:
        btn_search = st.button("검색", type="primary", use_container_width=True)

    # 기간 및 옵션 설정 (기본적으로 펼쳐두어 바로 수정 가능하게 함)
    with st.expander("📅 기간 및 보고서 종류 설정 (필요시 클릭)", expanded=True):
        opt_col1, opt_col2, opt_col3 = st.columns([1, 1, 2])
        
        with opt_col1:
            start_year = st.number_input("시작 연도", min_value=1990, max_value=2030, value=2024, step=1)
        with opt_col2:
            end_year = st.number_input("종료 연도", min_value=1990, max_value=2030, value=2025, step=1)
        with opt_col3:
            report_options = ["1분기보고서", "반기보고서", "3분기보고서", "사업보고서"]
            selected_types = st.multiselect("종류", report_options, default=["사업보고서"], label_visibility="collapsed")

# --- 6. 검색 및 결과 처리 로직 ---
if btn_search or ('target_df' in st.session_state and st.session_state.target_df is not None):
    # 버튼을 눌렀을 때만 새로운 검색 실행
    if btn_search:
        if not corp_name:
            st.warning("회사명을 입력해주세요.")
            st.stop()
            
        start_date = f"{start_year}0101"
        end_date = f"{end_year}1231"
        
        with st.spinner(f"🔎 '{corp_name}' 공시 찾는 중..."):
            try:
                df = fetch_report_list_clean(corp_name, start_date, end_date)
                
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
                    st.error("검색된 결과가 없습니다.")
                    st.session_state.target_df = None
            except Exception as e:
                st.error(f"오류: {e}")

    # 결과 표시 및 다운로드
    if 'target_df' in st.session_state and st.session_state.target_df is not None:
        df = st.session_state.target_df
        corp_name_fixed = st.session_state.get('current_corp', corp_name)
        
        st.divider()
        st.subheader(f"✅ 검색 결과 ({len(df)}건)")
        st.dataframe(df[['rcept_dt', 'report_nm']], use_container_width=True, hide_index=True)
        
        if len(df) > 0:
            if st.button("🚀 전체 다운로드 (ZIP 생성)", type="primary", use_container_width=True):
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
                            url = f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={api_key}&rcept_no={row['rcept_no']}"
                            res = requests.get(url, timeout=10)
                            with zipfile.ZipFile(io.BytesIO(res.content)) as z_orig:
                                target_file = max(z_orig.infolist(), key=lambda f: f.file_size).filename
                                raw_data = z_orig.read(target_file)
                                try: content_html = raw_data.decode('utf-8')
                                except: content_html = raw_data.decode('euc-kr', 'ignore')
                                clean_text = extract_ai_friendly_text(content_html)
                                
                                final_content = f"### {corp_name_fixed} {report_name} ###\n접수일: {row['rcept_dt']}\n\n{clean_text}"
                                zip_file.writestr(file_name, final_content)
                        except Exception as e:
                            st.error(f"실패: {file_name} - {e}")
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
