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
    page_title="DART 모바일 (디버그)",
    page_icon="🐞",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 스타일 커스텀
st.markdown("""
    <style>
    .stButton>button {
        width: 100%;
        border-radius: 12px;
        height: 3.5em;
        font-weight: bold;
        font-size: 16px;
    }
    div[data-testid="stDownloadButton"] > button {
        background-color: #007BFF;
        color: white;
    }
    div.block-container {
        padding-top: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🐞 DART 문제 해결 모드")

# --- 기억 장치 초기화 ---
if 'search_result' not in st.session_state:
    st.session_state.search_result = None
if 'xml_zip_data' not in st.session_state:
    st.session_state.xml_zip_data = None
if 'search_period' not in st.session_state:
    st.session_state.search_period = ""

# 2. API 키 설정
api_key = None
if "dart_api_key" in st.secrets:
    api_key = st.secrets["dart_api_key"]
else:
    with st.expander("🔐 API 키 설정", expanded=False):
        api_key = st.text_input("OpenDART API Key", type="password")

# --- 입력 폼 ---
with st.form(key='search_form'):
    corp_name = st.text_input("회사명", placeholder="예: 삼성전자")
    
    col1, col2 = st.columns(2)
    with col1:
        start_year = st.number_input("시작", 2000, 2030, datetime.datetime.now().year - 1)
    with col2:
        end_year = st.number_input("종료", 2000, 2030, datetime.datetime.now().year)

    target_reports = st.multiselect(
        "보고서 종류",
        ["사업보고서", "반기보고서", "분기보고서"],
        default=["사업보고서", "반기보고서", "분기보고서"]
    )
    
    st.markdown("---")
    auto_prepare = st.checkbox("⚡ 조회 시 다운로드 파일 바로 생성하기", value=True)

    submit_button = st.form_submit_button(label="🔍 조회 및 실행")

def clean_filename(text):
    return re.sub(r'[\\/*?:"<>|]', "_", text)

# --- 메인 로직 ---
if submit_button:
    if not api_key:
        st.error("API 키가 없습니다.")
    elif not corp_name:
        st.warning("회사명을 입력해주세요.")
    else:
        try:
            dart = OpenDartReader(api_key)
            status_container = st.empty()
            
            with status_container.container():
                with st.spinner(f"'{corp_name}' 데이터를 검색하고 있습니다..."):
                    
                    # 1. 목록 조회
                    start_date = str(start_year) + "0101"
                    end_date = str(end_year) + "1231"
                    
                    # [디버그] 목록 조회 에러 체크
                    try:
                        report_list = dart.list(corp_name, start=start_date, end=end_date, kind='A')
                    except Exception as e:
                        st.error(f"❌ 목록 조회 실패: {e}")
                        report_list = None

                    if report_list is None or len(report_list) == 0:
                        st.error("보고서가 없거나 API 키가 잘못되었습니다.")
                        st.session_state.search_result = None
                        st.session_state.xml_zip_data = None
                    else:
                        filter_condition = report_list['report_nm'].str.contains('|'.join(target_reports))
                        filtered_list = report_list[filter_condition]
                        
                        if len(filtered_list) == 0:
                            st.warning("선택한 보고서가 없습니다.")
                            st.session_state.search_result = None
                        else:
                            st.session_state.search_result = filtered_list
                            st.session_state.xml_zip_data = None
                            st.session_state.search_period = f"{start_year}-{end_year}"
                            
                            # 자동 생성 로직
                            if auto_prepare:
                                log_text = st.empty()
                                progress_bar = st.progress(0)
                                zip_buffer = io.BytesIO()
                                count = len(filtered_list)
                                success_cnt = 0
                                fail_cnt = 0
                                last_error_msg = ""
                                
                                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as master_zip:
                                    for i, row in filtered_list.iterrows():
                                        rcept_no = row['rcept_no']
                                        report_nm = clean_filename(row['report_nm'])
                                        rcept_dt = row['rcept_dt']
                                        
                                        log_text.text(f"파일 준비 중 ({i+1}/{count}): {report_nm}")
                                        
                                        try:
                                            url = f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={api_key}&rcept_no={rcept_no}"
                                            res = requests.get(url)
                                            
                                            # [디버그] DART 에러 메시지 확인
                                            if res.content.startswith(b'{'):
                                                err_json = json.loads(res.content)
                                                err_msg = err_json.get('message', '알 수 없는 오류')
                                                print(f"API Error: {err_msg}")
                                                last_error_msg = err_msg
                                                fail_cnt += 1
                                            else:
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
                                            fail_cnt += 1
                                            last_error_msg = str(e)
                                        
                                        time.sleep(0.1)
                                        progress_bar.progress((i + 1) / count)
                                
                                if success_cnt > 0:
                                    st.session_state.xml_zip_data = zip_buffer.getvalue()
                                    st.success(f"준비 끝! (성공: {success_cnt}, 실패: {fail_cnt})")
                                    if fail_cnt > 0:
                                        st.warning(f"⚠️ 일부 실패 원인: {last_error_msg}")
                                else:
                                    st.error(f"❌ 파일 생성 실패! 원인: {last_error_msg}")
                            else:
                                st.success(f"조회 완료! (총 {len(filtered_list)}건)")

        except Exception as e:
            st.error(f"❌ 시스템 에러 발생: {e}")

# --- 결과 화면 ---
if st.session_state.search_result is not None:
    df = st.session_state.search_result
    period_str = st.session_state.search_period
    
    st.divider()
    
    tab1, tab2 = st.tabs(["🚀 XML 다운로드", "📊 재무제표"])

    with tab1:
        if st.session_state.xml_zip_data is not None:
            st.info("파일 준비가 완료되었습니다.")
            st.download_button(
                label="📥 ZIP 파일 즉시 다운로드",
                data=st.session_state.xml_zip_data,
                file_name=f"{corp_name}_{period_str}_보고서.zip",
                mime="application/zip"
            )
        else:
            st.warning("아직 파일이 생성되지 않았습니다.")
            if st.button("파일 생성 시작하기"):
                st.rerun()

    with tab2:
        if st.button("재무제표 엑셀 생성"):
            with st.spinner("재무 데이터 수집 중..."):
                # [디버그] 재무제표 에러 체크
                try:
                    all_financials = []
                    years = sorted(list(set(df['rcept_dt'].str[:4])))
                    codes_to_fetch = [('11011','사업'),('11012','반기'),('11013','1분기'),('11014','3분기')]
                    
                    for year in years:
                        for code, name in codes_to_fetch:
                            try:
                                fs = dart.finstate(corp_name, year, code)
                                if fs is not None:
                                    fs['귀속년도']=year; fs['보고서']=name; all_financials.append(fs)
                                time.sleep(0.1)
                            except: pass
                    
                    if all_financials:
                        merged = pd.concat(all_financials)
                        buf = io.BytesIO()
                        with pd.ExcelWriter(buf) as w: merged.to_excel(w, index=False)
                        st.download_button("📥 엑셀 다운로드", buf.getvalue(), f"{corp_name}_{period_str}_재무제표.xlsx")
                    else:
                        st.warning("데이터를 찾을 수 없습니다. (API 한도 초과일 수 있음)")
                except Exception as e:
                    st.error(f"재무제표 생성 실패: {e}")
