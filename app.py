import streamlit as st
import OpenDartReader
import pandas as pd
import io
import time
import requests
import zipfile
import re
import datetime
import json

# 1. 페이지 설정
st.set_page_config(
    page_title="DART 모바일",
    page_icon="📱",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 스타일 커스텀
st.markdown("""
    <style>
    .stButton>button {
        width: 100%;
        border-radius: 10px;
        height: 3em;
        font-weight: bold;
    }
    div.block-container {
        padding-top: 2rem;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("📱 내 손안의 DART (디버그판)")

# 2. 설정 및 입력
api_key = None
if "dart_api_key" in st.secrets:
    api_key = st.secrets["dart_api_key"]
else:
    with st.expander("🔐 API 키 설정", expanded=False):
        api_key = st.text_input("OpenDART API Key", type="password")

# --- 입력 폼 ---
with st.form(key='search_form'):
    corp_name = st.text_input("회사명", placeholder="예: 삼성전자")
    
    st.write("📅 조회 기간")
    col1, col2 = st.columns(2)
    with col1:
        default_start = datetime.datetime.now().year - 1
        start_year = st.number_input("시작 연도", 2000, 2030, default_start)
    with col2:
        default_end = datetime.datetime.now().year
        end_year = st.number_input("종료 연도", 2000, 2030, default_end)

    st.write("📑 보고서 종류")
    target_reports = st.multiselect(
        "포함할 보고서",
        ["사업보고서", "반기보고서", "분기보고서"],
        default=["사업보고서", "반기보고서", "분기보고서"]
    )

    submit_button = st.form_submit_button(label="🔍 조회 시작")

def clean_filename(text):
    return re.sub(r'[\\/*?:"<>|]', "_", text)

# --- 메인 로직 ---
if submit_button:
    if not api_key:
        st.error("API 키가 없습니다!")
    elif not corp_name:
        st.warning("회사명을 입력해주세요.")
    elif not target_reports:
        st.warning("보고서 종류를 선택해주세요.")
    else:
        try:
            dart = OpenDartReader(api_key)
            status_container = st.container()
            
            with status_container:
                with st.spinner(f"'{corp_name}' 검색 중..."):
                    # 1. 목록 가져오기
                    start_date = str(start_year) + "0101"
                    end_date = str(end_year) + "1231"
                    report_list = dart.list(corp_name, start=start_date, end=end_date, kind='A')
                    
                    if report_list is None or len(report_list) == 0:
                        st.error("보고서가 없습니다.")
                    else:
                        filter_condition = report_list['report_nm'].str.contains('|'.join(target_reports))
                        filtered_list = report_list[filter_condition]
                        count = len(filtered_list)
                        
                        if count == 0:
                            st.warning("선택한 종류의 보고서가 없습니다.")
                        else:
                            st.success(f"총 {count}개의 보고서 발견!")
                            
                            tab1, tab2 = st.tabs(["📑 본문 다운로드", "💰 재무제표 엑셀"])
                            
                            # [TAB 1] XML 다운로드 (수정된 부분)
                            with tab1:
                                if st.button("XML 본문 받기"):
                                    zip_buffer = io.BytesIO()
                                    bar = st.progress(0)
                                    log_area = st.empty() # 진행상황 텍스트 표시
                                    
                                    success_cnt = 0
                                    fail_cnt = 0
                                    
                                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as master_zip:
                                        for i, row in filtered_list.iterrows():
                                            rcept_no = row['rcept_no']
                                            report_nm = clean_filename(row['report_nm'])
                                            rcept_dt = row['rcept_dt']
                                            
                                            log_area.text(f"처리중 ({i+1}/{count}): {report_nm}...")
                                            
                                            try:
                                                url = f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={api_key}&rcept_no={rcept_no}"
                                                res = requests.get(url)
                                                
                                                # [핵심] 진짜 파일인지 에러 메시지인지 확인!
                                                if res.content.startswith(b'{'):
                                                    # JSON 에러 메시지인 경우
                                                    error_json = json.loads(res.content)
                                                    print(f"API Error: {error_json}") 
                                                    fail_cnt += 1
                                                else:
                                                    # 정상 ZIP 파일인 경우
                                                    with zipfile.ZipFile(io.BytesIO(res.content)) as inner_zip:
                                                        max_size = 0
                                                        best_file_name = None
                                                        for info in inner_zip.infolist():
                                                            if info.filename.lower().endswith(('.xml', '.dsd', '.html', '.xhtml')):
                                                                if info.file_size > max_size:
                                                                    max_size = info.file_size
                                                                    best_file_name = info.filename
                                                        
                                                        if best_file_name:
                                                            source_data = inner_zip.read(best_file_name)
                                                            ext = best_file_name.split('.')[-1]
                                                            new_name = f"{rcept_dt}_{report_nm}.{ext}"
                                                            master_zip.writestr(new_name, source_data)
                                                            success_cnt += 1
                                            except Exception as e:
                                                print(f"Error: {e}")
                                                fail_cnt += 1
                                                pass
                                            
                                            time.sleep(0.2) # API 과부하 방지
                                            bar.progress((i + 1) / count)
                                    
                                    if success_cnt > 0:
                                        st.success(f"완료! (성공: {success_cnt}, 실패: {fail_cnt})")
                                        st.download_button(
                                            label="📦 ZIP 파일 다운로드",
                                            data=zip_buffer.getvalue(),
                                            file_name=f"{corp_name}_본문모음.zip",
                                            mime="application/zip"
                                        )
                                    else:
                                        st.error(f"다운로드 실패! (API 키를 확인하거나, 하루 사용량을 확인하세요. 실패: {fail_cnt})")

                            # [TAB 2] 재무제표 (기존 유지)
                            with tab2:
                                if st.button("재무제표 엑셀 받기"):
                                    bar2 = st.progress(0)
                                    log_area2 = st.empty()
                                    all_financials = []
                                    years = list(range(start_year, end_year + 1))
                                    
                                    codes_to_fetch = []
                                    if "사업보고서" in target_reports: codes_to_fetch.append(('11011', '사업보고서'))
                                    if "반기보고서" in target_reports: codes_to_fetch.append(('11012', '반기보고서'))
                                    if "분기보고서" in target_reports: 
                                        codes_to_fetch.append(('11013', '1분기보고서'))
                                        codes_to_fetch.append(('11014', '3분기보고서'))
                                    
                                    total_steps = len(years)
                                    for i, year in enumerate(years):
                                        log_area2.text(f"{year}년도 데이터 수집 중...")
                                        for code, code_name in codes_to_fetch:
                                            try:
                                                fs = dart.finstate(corp_name, year, code)
                                                if fs is not None:
                                                    fs['귀속년도'] = year
                                                    fs['보고서종류'] = code_name
                                                    all_financials.append(fs)
                                                time.sleep(0.1)
                                            except: pass
                                        bar2.progress((i + 1) / total_steps)
                                        
                                    if all_financials:
                                        merged_df = pd.concat(all_financials, ignore_index=True)
                                        buffer_fs = io.BytesIO()
                                        with pd.ExcelWriter(buffer_fs, engine='xlsxwriter') as writer:
                                            merged_df.to_excel(writer, index=False, sheet_name='통합재무제표')
                                        st.download_button(
                                            label="📥 엑셀 다운로드",
                                            data=buffer_fs,
                                            file_name=f"{corp_name}_재무제표.xlsx",
                                            mime="application/vnd.ms-excel"
                                        )
                                    else:
                                        st.warning("데이터가 없습니다.")

        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")
