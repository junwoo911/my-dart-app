import streamlit as st
import OpenDartReader
import pandas as pd
import io
import time
import requests
import zipfile
import re
import datetime

st.set_page_config(page_title="보고서 다운로드", page_icon="📥")
st.title("📥 DART 보고서 원클릭")

# Home에서 설정한 API 키 가져오기
api_key = st.session_state.get("api_key")

if not api_key:
    st.error("⚠️ 메인 화면(Home)에서 API 키를 먼저 입력해주세요.")
    st.stop()

# --- (이하 아까 만든 '안정판' 로직 그대로) ---
# 기존 코드의 `st.set_page_config` 줄만 빼고 복사해 넣으시면 됩니다.
# 편의를 위해 핵심 로직만 요약해 드립니다. (아까 코드 그대로 쓰시면 됩니다!)

with st.form(key='search_form'):
    corp_name = st.text_input("회사명", placeholder="예: 삼성전자")
    col1, col2 = st.columns(2)
    with col1: start_year = st.number_input("시작", 2000, 2030, datetime.datetime.now().year - 1)
    with col2: end_year = st.number_input("종료", 2000, 2030, datetime.datetime.now().year)
    target_reports = st.multiselect("보고서 종류", ["사업보고서", "반기보고서", "분기보고서"], default=["사업보고서", "반기보고서", "분기보고서"])
    submit_button = st.form_submit_button(label="🔍 조회하기")

def clean_filename(text): return re.sub(r'[\\/*?:"<>|]', "_", text)

if submit_button:
    try:
        dart = OpenDartReader(api_key)
        start_date = str(start_year) + "0101"
        end_date = str(end_year) + "1231"
        report_list = dart.list(corp_name, start=start_date, end=end_date, kind='A')
        
        if report_list is None or len(report_list) == 0:
            st.error("보고서가 없습니다.")
        else:
            filter_condition = report_list['report_nm'].str.contains('|'.join(target_reports))
            filtered_list = report_list[filter_condition]
            
            if len(filtered_list) == 0: st.warning("선택한 보고서가 없습니다.")
            else:
                st.session_state.search_result = filtered_list
                st.session_state.period_str = f"{start_year}-{end_year}"
                st.session_state.search_corp = corp_name
                st.success(f"조회 성공! ({len(filtered_list)}건)")
    except Exception as e: st.error(f"에러: {e}")

if 'search_result' in st.session_state and st.session_state.search_result is not None:
    df = st.session_state.search_result
    corp = st.session_state.search_corp
    period = st.session_state.period_str
    
    st.divider()
    st.subheader(f"📂 {corp} 다운로드 센터")
    
    tab1, tab2 = st.tabs(["XML 파일", "재무제표 엑셀"])
    
    with tab1:
        if st.button("📥 XML 생성 및 다운로드"):
            zip_buffer = io.BytesIO()
            prog = st.progress(0)
            cnt = 0
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
                for i, row in df.iterrows():
                    try:
                        url = f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={api_key}&rcept_no={row['rcept_no']}"
                        res = requests.get(url, timeout=10)
                        if not res.content.startswith(b'{'):
                            with zipfile.ZipFile(io.BytesIO(res.content)) as iz:
                                for info in iz.infolist():
                                    if info.filename.lower().endswith('.xml'): # 간단화
                                        z.writestr(f"{row['rcept_dt']}_{clean_filename(row['report_nm'])}.xml", iz.read(info.filename))
                                        cnt+=1; break
                    except: pass
                    prog.progress((i+1)/len(df))
            if cnt>0: st.download_button("💾 ZIP 다운로드", zip_buffer.getvalue(), f"{corp}_{period}_보고서.zip", "application/zip")
            else: st.error("실패")

    with tab2:
        if st.button("📊 엑셀 변환"):
            st.info("재무제표 로직은 동일합니다. (생략)")
            # (이전 코드의 재무제표 로직 그대로 사용)
