import streamlit as st
import OpenDartReader
import pandas as pd
import io
import time
import requests
import zipfile

# 1. 페이지 설정
st.set_page_config(page_title="DART PDF 일괄 다운로더", layout="wide")

st.title("📄 DART 보고서 PDF 싹슬이")
st.markdown("""
보고서에 **첨부된 PDF 파일**만 골라서 다운로드합니다.
(주의: 회사가 PDF를 첨부하지 않은 경우에는 다운로드되지 않을 수 있습니다.)
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
        
        # --- 기능 1: PDF 일괄 다운로드 ---
        with col1:
            st.subheader("📑 1. 보고서 PDF 다운로드")
            st.info(f"{start_year}~{end_year}년 보고서의 PDF 버전을 찾아서 모읍니다.")
            
            if st.button("PDF 싹 다 다운받기"):
                with st.spinner("보고서 목록을 검색 중..."):
                    start_date = str(start_year) + "0101"
                    end_date = str(end_year) + "1231"
                    # 사업, 반기, 분기 보고서 검색
                    report_list = dart.list(corp_name, start=start_date, end=end_date, kind='A')
                
                if report_list is None or len(report_list) == 0:
                    st.error("해당 기간에 보고서가 없습니다.")
                else:
                    count = len(report_list)
                    st.write(f"총 {count}개의 보고서를 찾았습니다. PDF 탐색을 시작합니다!")
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    zip_buffer = io.BytesIO()
                    
                    success_count = 0
                    
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as master_zip:
                        for i, row in report_list.iterrows():
                            rcept_no = row['rcept_no']
                            report_nm = row['report_nm']
                            rcept_dt = row['rcept_dt']
                            
                            status_text.text(f"[{i+1}/{count}] {report_nm}의 PDF를 찾는 중...")
                            
                            try:
                                # 해당 보고서의 첨부파일 목록 조회
                                attaches = dart.attach(rcept_no)
                                
                                pdf_url = None
                                pdf_name = None
                                
                                # 첨부파일 중 .pdf로 끝나는 것 찾기
                                if attaches:
                                    for title, url in attaches.items():
                                        if title.lower().endswith(".pdf"):
                                            pdf_url = url
                                            pdf_name = title
                                            break # PDF 하나 찾으면 바로 중단 (보통 첫번째가 메인)
                                
                                if pdf_url:
                                    # PDF 다운로드
                                    response = requests.get(pdf_url)
                                    if response.status_code == 200:
                                        # 파일명 보기 좋게 정리 (날짜_보고서명.pdf)
                                        clean_name = f"{rcept_dt}_{report_nm}.pdf"
                                        master_zip.writestr(clean_name, response.content)
                                        success_count += 1
                                    else:
                                        pass
                                else:
                                    # PDF가 없는 경우 (XML만 있는 경우)
                                    pass
                                    
                            except Exception as e:
                                pass # 에러나도 다음 파일로 계속 진행
                            
                            time.sleep(0.2) # 서버 부하 방지
                            progress_bar.progress((i + 1) / count)
                    
                    if success_count > 0:
                        st.success(f"완료! 총 {success_count}개의 PDF 파일을 찾았습니다.")
                        st.download_button(
                            label="📦 PDF 모음(ZIP) 다운로드",
                            data=zip_buffer.getvalue(),
                            file_name=f"{corp_name}_{start_year}-{end_year}_PDF보고서.zip",
                            mime="application/zip"
                        )
                    else:
                        st.warning("이 회사는 해당 기간에 PDF 첨부 파일을 제공하지 않습니다. (XML 다운로드를 이용하세요)")

        # --- 기능 2: 재무제표 통합 엑셀 (기존 유지) ---
        with col2:
            st.subheader("💰 2. 재무제표 통합 엑셀")
            st.info("재무데이터는 엑셀로 받는 게 국룰입니다.")
            
            if st.button("재무제표 일괄 수집 시작"):
                progress_bar2 = st.progress(0)
                status_text2 = st.empty()
                
                all_financials = []
                years = list(range(start_year, end_year + 1))
                report_codes = [('11013', '1분기'), ('11012', '반기'), ('11014', '3분기'), ('11011', '사업보고서')]
                total_steps = len(years)

                for i, year in enumerate(years):
                    status_text2.text(f"{year}년도 데이터 수집 중...")
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
        st.error(f"오류가 발생했습니다: {e}")
else:
    st.info("👈 API 키와 회사명을 입력해주세요.")
