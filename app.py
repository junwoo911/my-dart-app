import streamlit as st
import OpenDartReader
import pandas as pd
import io
import time
import requests
import zipfile
import re
import datetime

# 1. 페이지 설정 (모바일 친화적)
st.set_page_config(
    page_title="DART 모바일",
    page_icon="📱",
    layout="centered", # 모바일은 centered가 보기 좋습니다
    initial_sidebar_state="collapsed"
)

# 스타일 커스텀 (버튼을 꽉 차게, 여백 조정)
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

st.title("📱 내 손안의 DART")

# 2. 설정 및 입력 (사이드바 대신 메인 화면에 배치)
# API 키는 금고에 있으면 패스, 없으면 확장 메뉴(Expander)로 숨김
api_key = None
if "dart_api_key" in st.secrets:
    api_key = st.secrets["dart_api_key"]
else:
    with st.expander("🔐 API 키 설정 (클릭)", expanded=False):
        api_key = st.text_input("OpenDART API Key", type="password")

# --- 입력 폼 (여기서 엔터 치면 실행됨) ---
with st.form(key='search_form'):
    # (1) 회사명 입력
    corp_name = st.text_input("회사명", placeholder="예: 삼성전자 (입력 후 조회)")

    # (2) 기간 선택 (2단 배열)
    st.write("📅 조회 기간")
    col1, col2 = st.columns(2)
    with col1:
        # 기본값: 작년
        default_start = datetime.datetime.now().year - 1
        start_year = st.number_input("시작 연도", 2000, 2030, default_start)
    with col2:
        # 기본값: 올해
        default_end = datetime.datetime.now().year
        end_year = st.number_input("종료 연도", 2000, 2030, default_end)

    # (3) 보고서 종류 (칩 형태로 선택)
    st.write("📑 보고서 종류")
    target_reports = st.multiselect(
        "포함할 보고서 선택",
        ["사업보고서", "반기보고서", "분기보고서"],
        default=["사업보고서", "반기보고서", "분기보고서"]
    )

    # (4) 조회 버튼 (가장 중요!)
    submit_button = st.form_submit_button(label="🔍 조회 시작")


# --- 내부 함수들 (파일명 정리 등) ---
def clean_filename(text):
    return re.sub(r'[\\/*?:"<>|]', "_", text)

# --- 메인 로직 (조회 버튼을 눌렀을 때만 실행) ---
if submit_button:
    if not api_key:
        st.error("API 키가 필요합니다. 설정 메뉴를 확인해주세요.")
    elif not corp_name:
        st.warning("회사명을 입력해주세요.")
    elif not target_reports:
        st.warning("보고서 종류를 선택해주세요.")
    else:
        try:
            dart = OpenDartReader(api_key)
            
            # 진행 상황 표시
            status_container = st.container()
            with status_container:
                with st.spinner(f"'{corp_name}' 데이터를 검색 중입니다..."):
                    
                    # 1. 목록 가져오기
                    start_date = str(start_year) + "0101"
                    end_date = str(end_year) + "1231"
                    report_list = dart.list(corp_name, start=start_date, end=end_date, kind='A')
                    
                    if report_list is None or len(report_list) == 0:
                        st.error(f"'{corp_name}'에 대한 보고서가 없습니다.")
                    else:
                        # 필터링
                        filter_condition = report_list['report_nm'].str.contains('|'.join(target_reports))
                        filtered_list = report_list[filter_condition]
                        count = len(filtered_list)
                        
                        if count == 0:
                            st.warning("검색 결과는 있지만, 선택한 종류의 보고서가 없습니다.")
                        else:
                            st.success(f"총 {count}개의 보고서를 찾았습니다!")
                            
                            # --- 탭으로 기능 분리 (깔끔하게) ---
                            tab1, tab2 = st.tabs(["📑 본문 다운로드", "💰 재무제표 엑셀"])
                            
                            # [TAB 1] 본문 XML 다운로드
                            with tab1:
                                st.info("압축을 풀면 '본문 파일'만 나옵니다.")
                                if st.button("XML 본문 받기"):
                                    zip_buffer = io.BytesIO()
                                    bar = st.progress(0)
                                    
                                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as master_zip:
                                        for i, row in filtered_list.iterrows():
                                            rcept_no = row['rcept_no']
                                            report_nm = clean_filename(row['report_nm'])
                                            rcept_dt = row['rcept_dt']
                                            
                                            try:
                                                url = f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={api_key}&rcept_no={rcept_no}"
                                                res = requests.get(url)
                                                if res.status_code == 200:
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
                                            except: pass
                                            bar.progress((i + 1) / count)
                                            
                                    st.download_button(
                                        label="📦 ZIP 파일 다운로드",
                                        data=zip_buffer.getvalue(),
                                        file_name=f"{corp_name}_본문모음.zip",
                                        mime="application/zip"
                                    )

                            # [TAB 2] 재무제표 엑셀
                            with tab2:
                                st.info("선택한 기간의 재무제표를 통합합니다.")
                                if st.button("재무제표 엑셀 받기"):
                                    bar2 = st.progress(0)
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

# 첫 화면 안내 문구 (조회 전)
if not submit_button:
    st.info("👆 위 조건 입력 후 '조회 시작' 버튼을 눌러주세요.")
