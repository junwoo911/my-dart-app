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
        padding-top: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("📱 DART 모바일 (Session Ver.)")

# --- [중요] 기억 장치 초기화 ---
# 앱이 새로고침 되어도 데이터를 기억할 변수들을 만듭니다.
if 'search_result' not in st.session_state:
    st.session_state.search_result = None # 조회 결과 저장소
if 'corp_name_mem' not in st.session_state:
    st.session_state.corp_name_mem = ""

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
        start_year = st.number_input("시작 연도", 2000, 2030, datetime.datetime.now().year - 1)
    with col2:
        end_year = st.number_input("종료 연도", 2000, 2030, datetime.datetime.now().year)

    target_reports = st.multiselect(
        "보고서 종류",
        ["사업보고서", "반기보고서", "분기보고서"],
        default=["사업보고서", "반기보고서", "분기보고서"]
    )

    # 이 버튼을 누르면 'session_state'에 결과를 저장합니다.
    submit_button = st.form_submit_button(label="🔍 조회 하기")

# --- 메인 로직 ---
if submit_button:
    if not api_key:
        st.error("API 키가 없습니다.")
    elif not corp_name:
        st.warning("회사명을 입력해주세요.")
    else:
        try:
            dart = OpenDartReader(api_key)
            with st.spinner(f"'{corp_name}' 검색 중..."):
                start_date = str(start_year) + "0101"
                end_date = str(end_year) + "1231"
                report_list = dart.list(corp_name, start=start_date, end=end_date, kind='A')
                
                if report_list is None or len(report_list) == 0:
                    st.error("보고서가 없습니다.")
                    st.session_state.search_result = None
                else:
                    # 필터링 및 결과 저장
                    filter_condition = report_list['report_nm'].str.contains('|'.join(target_reports))
                    filtered_list = report_list[filter_condition]
                    
                    if len(filtered_list) == 0:
                        st.warning("선택한 보고서가 없습니다.")
                        st.session_state.search_result = None
                    else:
                        # [핵심] 결과를 기억장치에 저장!
                        st.session_state.search_result = filtered_list
                        st.session_state.corp_name_mem = corp_name
                        st.success(f"조회 완료! (총 {len(filtered_list)}건)")
        except Exception as e:
            st.error(f"에러 발생: {e}")

# --- 결과 화면 (저장된 데이터가 있을 때만 표시) ---
if st.session_state.search_result is not None:
    df = st.session_state.search_result
    corp = st.session_state.corp_name_mem
    
    st.divider()
    st.subheader(f"📂 {corp} 분석 결과")
    st.write(f"검색된 보고서: {len(df)}건")

    tab1, tab2 = st.tabs(["📑 본문 다운로드", "💰 재무제표"])

    # [TAB 1] XML 다운로드
    with tab1:
        st.info("아래 버튼을 누르면 다운로드가 시작됩니다.")
        
        # 버튼 하나로 생성 및 다운로드
        if st.button("🚀 XML 파일 생성 및 다운로드"):
            zip_buffer = io.BytesIO()
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            success_cnt = 0
            count = len(df)
            
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as master_zip:
                for i, row in df.iterrows():
                    rcept_no = row['rcept_no']
                    report_nm = re.sub(r'[\\/*?:"<>|]', "_", row['report_nm'])
                    rcept_dt = row['rcept_dt']
                    
                    status_text.text(f"다운로드 중.. {report_nm}")
                    
                    try:
                        url = f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={api_key}&rcept_no={rcept_no}"
                        res = requests.get(url)
                        
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
                    except:
                        pass
                    
                    time.sleep(0.1)
                    progress_bar.progress((i + 1) / count)
            
            if success_cnt > 0:
                st.success(f"{success_cnt}개 파일 준비 완료!")
                st.download_button(
                    label="📥 지금 다운로드 클릭!",
                    data=zip_buffer.getvalue(),
                    file_name=f"{corp}_본문모음.zip",
                    mime="application/zip"
                )
            else:
                st.error("파일 생성 실패 (API 한도 초과 등)")

    # [TAB 2] 재무제표 엑셀
    with tab2:
        if st.button("📊 재무제표 엑셀 생성"):
            bar2 = st.progress(0)
            status2 = st.empty()
            all_financials = []
            
            # 연도 목록 추출
            years = sorted(list(set(df['rcept_dt'].str[:4])))
            total_steps = len(years) * 4 # 대략적인 스텝 수
            current_step = 0

            # 보고서 종류별 코드
            codes_map = {
                '사업보고서': '11011',
                '반기보고서': '11012',
                '분기보고서': ['11013', '11014']
            }
            
            for year in years:
                status2.text(f"{year}년도 데이터 조회 중...")
                
                # 사용자가 검색했던 보고서 종류(target_reports)를 기반으로 조회할 필요가 없음
                # 이미 필터링된 df가 있지만, 재무제표는 finstate API를 따로 써야 함.
                # 편의상 검색된 연도에 대해 모든 코드를 시도합니다.
                
                try:
                    dart = OpenDartReader(api_key)
                    # 1분기
                    f1 = dart.finstate(corp, year, '11013')
                    if f1 is not None: 
                        f1['귀속년도']=year; f1['보고서']='1분기'; all_financials.append(f1)
                    
                    # 반기
                    f2 = dart.finstate(corp, year, '11012')
                    if f2 is not None: 
                        f2['귀속년도']=year; f2['보고서']='반기'; all_financials.append(f2)
                        
                    # 3분기
                    f3 = dart.finstate(corp, year, '11014')
                    if f3 is not None: 
                        f3['귀속년도']=year; f3['보고서']='3분기'; all_financials.append(f3)
                    
                    # 사업
                    f4 = dart.finstate(corp, year, '11011')
                    if f4 is not None: 
                        f4['귀속년도']=year; f4['보고서']='사업보고서'; all_financials.append(f4)
                        
                except: pass
                
                bar2.progress((years.index(year) + 1) / len(years))
                time.sleep(0.2)

            if all_financials:
                merged_df = pd.concat(all_financials, ignore_index=True)
                buffer_fs = io.BytesIO()
                with pd.ExcelWriter(buffer_fs, engine='xlsxwriter') as writer:
                    merged_df.to_excel(writer, index=False, sheet_name='통합재무제표')
                
                st.success("생성 완료!")
                st.download_button(
                    label="📥 엑셀 다운로드",
                    data=buffer_fs,
                    file_name=f"{corp}_재무제표.xlsx",
                    mime="application/vnd.ms-excel"
                )
            else:
                st.warning("재무 데이터를 찾을 수 없습니다.")

