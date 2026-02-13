import streamlit as st
import OpenDartReader
import pandas as pd
import io
import zipfile
import re
import datetime
import requests
from bs4 import BeautifulSoup

# --- 페이지 설정 ---
st.set_page_config(page_title="보고서 다운로드", page_icon="📥", layout="wide")

# [수정 2] 앱 제목을 '보고서 다운로드'로 직관적으로 변경
st.title("보고서 다운로드")

# --- 1. API 키 설정 ---
if 'api_key' not in st.session_state:
    if "dart_api_key" in st.secrets:
        st.session_state.api_key = st.secrets["dart_api_key"]
    else:
        st.error("API 키가 설정되지 않았습니다.")
        st.stop()

api_key = st.session_state.api_key

# --- 2. DART 객체 생성 ---
@st.cache_resource
def get_dart_system(key):
    return OpenDartReader(key)

# --- 3. 보고서 목록 조회 ---
@st.cache_data(ttl=3600)
def fetch_report_list_clean(corp_name, start_date, end_date):
    dart = get_dart_system(api_key)
    return dart.list(corp_name, start=start_date, end=end_date, kind='A')

# --- 4. 텍스트 변환 함수 ---
def extract_ai_friendly_text(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    for s in soup(["script", "style", "head", "svg", "img"]):
        s.decompose()
    
    # 표를 마크다운 스타일로 변환
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

# --- [수정 2 관련] 사이드바 제거하고 메인 화면에 검색창 배치 ---
# 폴드폰에서 사이드바를 열지 않아도 바로 검색할 수 있습니다.

with st.container(border=True):
    st.subheader("🔍 검색 설정")
    
    # 1행: 회사명 입력
    corp_name = st.text_input("회사명", value="", placeholder="예: 파라다이스")
    
    # 2행: 연도 선택 (가로로 배치)
    col1, col2 = st.columns(2)
    with col1:
        start_year = st.number_input("시작 연도", min_value=1990, max_value=2030, value=2024, step=1)
    with col2:
        end_year = st.number_input("종료 연도", min_value=1990, max_value=2030, value=2025, step=1)
    
    # 3행: 보고서 종류
    report_options = ["1분기보고서", "반기보고서", "3분기보고서", "사업보고서"]
    selected_types = st.multiselect("보고서 종류 선택", report_options, default=["사업보고서"])
    
    # 검색 버튼
    if st.button("목록 조회", type="primary", use_container_width=True):
        st.session_state.search_trigger = True
    else:
        # 버튼을 누르지 않았을 때도 결과가 유지되도록 처리 (Streamlit 특성)
        if 'search_trigger' not in st.session_state:
            st.session_state.search_trigger = False

# --- 메인 로직 ---
if st.session_state.search_trigger:
    if not corp_name:
        st.warning("회사명을 입력해주세요.")
    else:
        start_date = f"{start_year}0101"
        end_date = f"{end_year}1231"
        
        # 중복 호출 방지를 위해 결과가 없거나 검색 조건이 바뀌었을 때만 로딩 표시
        if 'target_df' not in st.session_state or st.session_state.target_df is None:
             spinner_text = f"📡 '{corp_name}'의 공시를 조회 중..."
        else:
             spinner_text = "결과를 갱신 중..."

        with st.spinner(spinner_text):
            try:
                df = fetch_report_list_clean(corp_name, start_date, end_date)
                
                if df is not None and len(df) > 0:
                    
                    # 1분기/3분기 정밀 필터링 로직
                    conditions = []
                    if "사업보고서" in selected_types:
                        conditions.append(df['report_nm'].str.contains("사업보고서"))
                    if "반기보고서" in selected_types:
                        conditions.append(df['report_nm'].str.contains("반기보고서"))
                    if "1분기보고서" in selected_types:
                        cond_q1 = (df['report_nm'].str.contains("분기보고서")) & \
                                  (df['report_nm'].str.contains(r"\.03|\.3월", regex=True))
                        conditions.append(cond_q1)
                    if "3분기보고서" in selected_types:
                        cond_q3 = (df['report_nm'].str.contains("분기보고서")) & \
                                  (df['report_nm'].str.contains(r"\.09|\.9월", regex=True))
                        conditions.append(cond_q3)

                    if conditions:
                        final_mask = pd.concat(conditions, axis=1).any(axis=1)
                        filtered_df = df[final_mask].copy().reset_index(drop=True)
                    else:
                        filtered_df = pd.DataFrame()

                    st.session_state.target_df = filtered_df
                    
                    if len(filtered_df) == 0:
                         st.warning("조건에 맞는 보고서가 없습니다.")
                else:
                    st.error("해당 기간에 검색된 보고서가 없습니다.")
                    st.session_state.target_df = None
            except Exception as e:
                st.error(f"오류 발생: {e}")

# --- 다운로드 섹션 ---
if 'target_df' in st.session_state and st.session_state.target_df is not None:
    df = st.session_state.target_df
    
    st.write(f"✅ **총 {len(df)}건 검색됨**")
    st.dataframe(df[['rcept_dt', 'corp_name', 'report_nm']], use_container_width=True, hide_index=True)
    
    if st.button("🚀 선택된 보고서 개별 추출 시작", use_container_width=True):
        
        zip_buffer = io.BytesIO()
        progress_bar = st.progress(0)
        status_text = st.empty()
        total = len(df)
        
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for idx, row in df.iterrows():
                report_name = row['report_nm']
                
                # [수정 1] 파일명 생성: 뒤에 붙던 (접수일) 제거
                # DART 보고서 이름 자체에 이미 (2025.09) 등이 포함되어 있으므로 그대로 사용
                file_name = f"{corp_name}_{report_name}.txt"
                
                # 파일명 특수문자 제거
                file_name = re.sub(r'[\\/*?:"<>|]', "", file_name)

                status_text.info(f"⏳ ({idx+1}/{total}) {file_name} 생성 중...")
                
                try:
                    url = f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={api_key}&rcept_no={row['rcept_no']}"
                    res = requests.get(url, timeout=10)
                    
                    with zipfile.ZipFile(io.BytesIO(res.content)) as z_orig:
                        target_file = max(z_orig.infolist(), key=lambda f: f.file_size).filename
                        raw_data = z_orig.read(target_file)
                        try: content_html = raw_data.decode('utf-8')
                        except: content_html = raw_data.decode('euc-kr', 'ignore')
                        
                        clean_text = extract_ai_friendly_text(content_html)
                        
                        final_content = f"### {corp_name} {report_name} ###\n"
                        # 문서 내부에만 참고용으로 접수일 기록 (파일명에는 안 씀)
                        final_content += f"접수일: {row['rcept_dt']}\n\n"
                        final_content += clean_text
                        
                        zip_file.writestr(file_name, final_content)
                        
                except Exception as e:
                    st.error(f"{file_name} 처리 중 오류: {e}")
                
                progress_bar.progress((idx + 1) / total)

        status_text.success("🎉 변환 완료! 아래 버튼을 눌러주세요.")
        
        st.download_button(
            label="💾 보고서 모음 다운로드 (ZIP)",
            data=zip_buffer.getvalue(),
            file_name=f"{corp_name}_Reports.zip",
            mime="application/zip",
            type="primary",
            use_container_width=True
        )
