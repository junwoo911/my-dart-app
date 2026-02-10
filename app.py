import streamlit as st
import OpenDartReader
import pandas as pd
import io
import time
import requests
import zipfile
import re
import datetime

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
        border-radius: 12px;
        height: 3.5em;
        font-weight: bold;
        font-size: 16px;
    }
    div.block-container {
        padding-top: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("📱 DART 모바일 (파일명 패치)")

# --- 기억 장치 초기화 ---
if 'search_result' not in st.session_state:
    st.session_state.search_result = None
if 'search_period' not in st.session_state:
    st.session_state.search_period = ""
if 'search_corp' not in st.session_state:
    st.session_state.search_corp = ""

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
    
    # 1단계: 조회만 수행 (안정성 확보)
    submit_button = st.form_submit_button(label="🔍 1단계: 조회하기")

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
            with st.spinner("목록을 가져오는 중..."):
                start_date = str(start_year) + "0101"
                end_date = str(end_year) + "1231"
                report_list = dart.list(corp_name, start=start_date, end=end_date, kind='A')
                
                if report_list is None or len(report_list) == 0:
                    st.error("보고서가 없습니다.")
                    st.session_state.search_result = None
                else:
                    filter_condition = report_list['report_nm'].str.contains('|'.join(target_reports))
                    filtered_list = report_list[filter_condition]
                    
                    if len(filtered_list) == 0:
                        st.warning("선택한 보고서가 없습니다.")
                        st.session_state.search_result = None
                    else:
                        # [핵심] 결과와 파일명에 쓸 정보를 기억장치에 저장
                        st.session_state.search_result = filtered_list
                        st.session_state.search_period = f"{start_year}-{end_year}"
                        st.session_state.search_corp = corp_name # 회사명도 저장 (입력창 바꿔도 유지되게)
                        st.success(f"조회 성공! ({len(filtered_list)}건)")

        except Exception as e:
            st.error(f"에러 발생: {e}")

# --- 2단계: 다운로드 화면 ---
if st.session_state.search_result is not None:
    df = st.session_state.search_result
    # 저장된 정보 불러오기
    saved_period = st.session_state.search_period
    saved_corp = st.session_state.search_corp
    
    st.divider()
    st.subheader(f"📂 {saved_corp} ({len(df)}건)")
    
    tab1, tab2 = st.tabs(["🚀 XML 다운로드", "📊 재무제표"])

    # [TAB 1] XML 다운로드
    with tab1:
        st.info("버튼을 누르면 파일 생성이 시작됩니다.")
        
        if st.button("📥 2단계: XML 생성 및 다운로드", key='xml_btn'):
            zip_buffer = io.BytesIO()
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            count = len(df)
            success_cnt = 0
            
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as master_zip:
                for i, row in df.iterrows():
                    rcept_no = row['rcept_no']
                    report_nm = clean_filename(row['report_nm'])
                    rcept_dt = row['rcept_dt']
                    
                    status_text.text(f"다운로드 중.. {report_nm}")
                    
                    try:
                        # 타임아웃 설정으로 멈춤 방지
                        url = f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={api_key}&rcept_no={rcept_no}"
                        res = requests.get(url, timeout=10)
                        
                        if not res.content.startswith(b'{'):
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
                    except: pass
                    
                    time.sleep(0.1)
                    progress_bar.progress((i + 1) / count)
            
            if success_cnt > 0:
                st.success("생성 완료! 버튼을 한 번 더 눌러주세요.")
                # [핵심] 파일명 지정: 회사명_기간_보고서.zip
                final_filename = f"{saved_corp}_{saved_period}_보고서.zip"
                
                st.download_button(
                    label=f"💾 {final_filename} 다운로드",
                    data=zip_buffer.getvalue(),
                    file_name=final_filename,
                    mime="application/zip"
                )
            else:
                st.error("파일 생성 실패 (API 한도 확인 필요)")

    # [TAB 2] 재무제표 엑셀
    with tab2:
        if st.button("📊 재무제표 엑셀 받기"):
            with st.spinner("데이터 수집 중..."):
                all_financials = []
                years = sorted(list(set(df['rcept_dt'].str[:4])))
                codes_to_fetch = [('11011','사업'),('11012','반기'),('11013','1분기'),('11014','3분기')]
                
                prog = st.progress(0)
                for idx, year in enumerate(years):
                    for code, name in codes_to_fetch:
                        try:
                            dart = OpenDartReader(api_key)
                            fs = dart.finstate(saved_corp, year, code)
                            if fs is not None:
                                fs['귀속년도']=year; fs['보고서']=name; all_financials.append(fs)
                            time.sleep(0.1)
                        except: pass
                    prog.progress((idx+1)/len(years))
                
                if all_financials:
                    merged = pd.concat(all_financials)
                    buf = io.BytesIO()
                    with pd.ExcelWriter(buf) as w: merged.to_excel(w, index=False)
                    
                    # [핵심] 파일명 지정: 회사명_기간_재무제표.xlsx
                    final_filename_xl = f"{saved_corp}_{saved_period}_재무제표.xlsx"
                    
                    st.download_button(
                        label=f"📥 {final_filename_xl} 다운로드",
                        data=buf.getvalue(),
                        file_name=final_filename_xl,
                        mime="application/vnd.ms-excel"
                    )
                else:
                    st.warning("데이터 없음")
