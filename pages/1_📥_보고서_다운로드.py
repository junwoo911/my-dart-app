import streamlit as st
import OpenDartReader
import pandas as pd
import io
import zipfile
import re
import datetime
import requests
from bs4 import BeautifulSoup

# 페이지 설정
st.set_page_config(page_title="AI 공시 분석 센터", page_icon="📂", layout="wide")
st.title("📂 기업 공시 개별 다운로더")

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
    # 정기공시(A) 전체를 가져온 후 필터링하는 방식이 가장 확실함
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

# --- 사이드바 UI 설정 ---
with st.sidebar:
    st.header("🔍 검색 옵션")
    
    # [요청 5] 회사명 default 값 제거 (빈칸)
    corp_name = st.text_input("회사명", value="", placeholder="예: 삼성전자")
    
    # [요청 3] 연도를 직접 숫자로 입력
    col1, col2 = st.columns(2)
    with col1:
        start_year = st.number_input("시작 연도", min_value=1990, max_value=2030, value=2024, step=1)
    with col2:
        end_year = st.number_input("종료 연도", min_value=1990, max_value=2030, value=2025, step=1)
    
    # [요청 2] 보고서 종류 4가지로 세분화
    # DART에서는 '1분기'와 '3분기'를 통칭 '분기보고서'라고 하지만, 사용자가 선택하기 쉽게 나눔
    report_options = ["1분기보고서", "반기보고서", "3분기보고서", "사업보고서"]
    selected_types = st.multiselect("보고서 종류 선택", report_options, default=["사업보고서"])
    
    btn_search = st.button("목록 조회", type="primary")

# --- 메인 로직 ---
if btn_search:
    if not corp_name:
        st.warning("회사명을 입력해주세요.")
    else:
        start_date = f"{start_year}0101"
        end_date = f"{end_year}1231"
        
        with st.spinner(f"📡 '{corp_name}'의 공시를 조회 중..."):
            try:
                df = fetch_report_list_clean(corp_name, start_date, end_date)
                
                if df is not None and len(df) > 0:
                    # 선택한 보고서 종류에 따라 필터링 로직
                    # 사용자는 1분기/3분기를 구분했지만, 실제 데이터에는 '분기보고서'로 들어올 수 있음
                    # 따라서 이름에 포함된 텍스트로 유연하게 찾습니다.
                    
                    filter_keywords = []
                    if "사업보고서" in selected_types: filter_keywords.append("사업보고서")
                    if "반기보고서" in selected_types: filter_keywords.append("반기보고서")
                    if "1분기보고서" in selected_types or "3분기보고서" in selected_types:
                        filter_keywords.append("분기보고서") # DART 원본 명칭 대응

                    # 정규식으로 필터링 (OR 조건)
                    if filter_keywords:
                        mask = df['report_nm'].str.contains('|'.join(filter_keywords))
                        filtered_df = df[mask].copy().reset_index(drop=True)
                    else:
                        filtered_df = pd.DataFrame()

                    st.session_state.target_df = filtered_df
                    
                    if len(filtered_df) > 0:
                        st.success(f"✅ {len(filtered_df)}건의 보고서가 검색되었습니다.")
                    else:
                        st.warning("선택하신 조건에 맞는 보고서가 없습니다.")
                else:
                    st.error("해당 기간에 검색된 보고서가 없습니다.")
                    st.session_state.target_df = None
            except Exception as e:
                st.error(f"오류 발생: {e}")

# --- 다운로드 섹션 ---
if 'target_df' in st.session_state and st.session_state.target_df is not None:
    df = st.session_state.target_df
    
    st.dataframe(df[['rcept_dt', 'corp_name', 'report_nm']], use_container_width=True, hide_index=True)
    
    # [요청 6] 개별 파일로 분리하여 다운로드 (ZIP 패키징)
    if st.button("🚀 선택된 보고서 개별 추출 시작"):
        
        # 압축 파일을 위한 메모리 버퍼 생성
        zip_buffer = io.BytesIO()
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        total = len(df)
        
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for idx, row in df.iterrows():
                report_name = row['report_nm']
                rcept_dt = row['rcept_dt'] # YYYYMMDD 형식
                
                # [요청 4] 파일명 생성: 회사명_보고서명(연도.월).txt
                # 날짜 포맷 변경: 20240312 -> 2024.03
                formatted_date = f"{rcept_dt[:4]}.{rcept_dt[4:6]}"
                file_name = f"{corp_name}_{report_name}({formatted_date}).txt"
                
                # 파일명에서 윈도우 파일명 금지 문자 제거
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
                        
                        # 개별 파일 내용 구성
                        final_content = f"### {corp_name} {report_name} ###\n"
                        final_content += f"접수일: {formatted_date}\n\n"
                        final_content += clean_text
                        
                        # ZIP 파일에 개별 txt 추가
                        zip_file.writestr(file_name, final_content)
                        
                except Exception as e:
                    st.error(f"{file_name} 처리 중 오류: {e}")
                
                progress_bar.progress((idx + 1) / total)

        status_text.success("🎉 변환 완료! 아래 버튼을 눌러 압축 파일을 받으세요.")
        
        # ZIP 파일 다운로드 버튼 제공
        st.download_button(
            label="💾 보고서 모음 다운로드 (ZIP)",
            data=zip_buffer.getvalue(),
            file_name=f"{corp_name}_Reports_{start_year}_{end_year}.zip",
            mime="application/zip",
            type="primary"
        )
