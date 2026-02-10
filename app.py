import streamlit as st
import OpenDartReader
import pandas as pd
import io
import time
import requests
import zipfile

# 1. 페이지 설정
st.set_page_config(page_title="DART 실전 다운로더", layout="wide")

st.title("📊 DART 데이터 수집기 (클라우드용)")
st.markdown("""
**주의:** 서버 보안 문제로 'PDF 파일'은 다운로드할 수 없습니다. 
대신 **공시 원본(XML)**과 **재무제표(Excel)** 다운로드를 지원합니다.
""")

# 2. 사이드바 설정
with st.sidebar:
    st.header("🔎 검색 조건")
    
    if "dart_api_key" in st.secrets:
        api_key = st.secrets["dart_api_key"]
        st.success("API Key 로드 완료! 🔐")
    else:
        api_key = st.text_input("OpenDART API Key", type="password")

    corp_name = st.text_input("회사명", "삼성전자")
    
    period_option = st.radio(
        "기간 선택 (5년 단위)",
        ("2021~2025", "2016~2020", "2011~2015", "직접입력")
    )
    
    if period_option == "직접입력":
        start_year = st.number_input("시작 연도", 2000, 2030, 2024)
        end_year = st.number_input("종료 연도", 2000, 2030, 2024)
    else:
        start_year = int(period_option.split("~")[0])
        end_year = int(period_option.split("~")[1])

# 메인 로직
if api_key and corp_name:
    try:
        dart = OpenDartReader(api_key)
        
        col1, col2 = st.columns(2)
        
        # --- 기능 1: 원본 파일(XML) 다운로드 (대안) ---
        with col1:
            st.subheader("📑 1. 공시 원본(XML) 다운로드")
            st.info(f"PDF 대신, DART에 제출된 **원본 파일(HTML/XML)**을 다운로드합니다.\n(압축을 풀고 파일을 열면 인터넷 창에서 내용 확인이 가능합니다.)")
            
            if st.button("원본 파일 싹 다 받기"):
                with st.spinner("목록 조회 중..."):
                    start_date = str(start_year) + "0101"
                    end_date = str(end_year) + "1231"
                    report_list = dart.list(corp_name, start=start_date, end=end_date, kind='A')
                
                if report_list is None or len(report_list) == 0:
                    st.error("해당 기간에 보고서가 없습니다.")
                else:
                    count = len(report_list)
                    st.write(f"총 {count}개의 보고서 원본을 다운로드합니다.")
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    zip_buffer = io.BytesIO()
                    
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as master_zip:
                        for i, row in report_list.iterrows():
                            rcept_no = row['rcept_no']
                            report_nm = row['report_nm']
                            rcept_dt = row['rcept_dt']
                            
                            status_text.text(f"[{i+1}/{count}] {report_nm} 다운로드 중...")
                            
                            # 공식 API를 통한 원본 다운로드 (이건 100% 됩니다)
                            try:
                                url = f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={api_key}&rcept_no={rcept_no}"
                                res = requests.get(url)
                                
                                if res.status_code == 200:
                                    # 파일명: 20240321_사업보고서.zip
                                    file_name = f"{rcept_dt}_{report_nm}.zip"
                                    master_zip.writestr(file_name, res.content)
                                else:
                                    pass
                            except:
                                pass
                                
                            time.sleep(0.1)
                            progress_bar.progress((i + 1) / count)
                    
                    st.success("다운로드 완료!")
                    st.download_button(
                        label="📦 원본 모음(ZIP) 다운로드",
                        data=zip_buffer.getvalue(),
                        file_name=f"{corp_name}_{start_year}-{end_year}_원본보고서.zip",
                        mime="application/zip"
                    )

        # --- 기능 2: 재무제표 통합 엑셀 (성공 기능) ---
        with col2:
            st.subheader("💰 2. 재무제표 통합 엑셀")
            st.info(f"{start_year}~{end_year}년 재무제표를 엑셀 하나로 합쳐줍니다. (이건 잘 됩니다!)")
            
            if st.button("재무제표 일괄 수집 시작"):
                progress_bar2 = st.progress(0)
                status_text2 = st.empty()
                
                all_financials = []
                years = list(range(start_year, end_year + 1))
                report_codes = [('11013', '1분기'), ('11012', '반기'), ('11014', '3분기'), ('11011', '사업보고서')]
                total_steps = len(years)

                for i, year in enumerate(years):
                    status_text2.text(f"{year}년도 데이터 긁어오는 중...")
                    progress_bar2.progress((i + 1) / total_steps)
                    
                    for code, code_name in report_codes:
                        try:
                            fs = dart.finstate(corp_name, year, code)
                            if fs is not None:
                                fs['귀속년도'] = year
                                fs['보고서종류'] = code_name
                                all_financials.append(fs)
                            time.sleep(0.2)
                        except:
                            pass

                if all_financials:
                    merged_df = pd.concat(all_financials, ignore_index=True)
                    st.success("수집 완료!")
                    
                    buffer_fs = io.BytesIO()
                    with pd.ExcelWriter(buffer_fs, engine='xlsxwriter') as writer:
                        merged_df.to_excel(writer, index=False, sheet_name='통합재무제표')
                        
                    st.download_button(
                        label="📥 재무제표 엑셀 다운로드",
                        data=buffer_fs,
                        file_name=f"{corp_name}_{start_year}-{end_year}_재무제표.xlsx",
                        mime="application/vnd.ms-excel"
                    )
                else:
                    st.warning("데이터가 없습니다.")

    except Exception as e:
        st.error(f"오류: {e}")
else:
    st.info("👈 API 키와 회사명을 입력해주세요.")
