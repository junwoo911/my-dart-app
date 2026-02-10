import streamlit as st
import OpenDartReader
import pandas as pd
import io
import time
import requests
import zipfile
import re

# 1. 페이지 설정
st.set_page_config(page_title="DART XML 알맹이 추출기", layout="wide")

st.title("📂 DART 보고서 XML 껍질 까서 주기")
st.markdown("""
**이중 압축 풀기 귀찮으시죠?** 개별 보고서 압축을 자동으로 풀어서, **XML/HTML 알맹이만 모아** 드립니다.
다운로드 후 압축만 한 번 풀면 바로 분석 준비 끝!
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

# --- 특수 문자 제거 함수 (파일명 생성용) ---
def clean_filename(text):
    return re.sub(r'[\\/*?:"<>|]', "", text)

# 메인 로직
if api_key and corp_name:
    try:
        dart = OpenDartReader(api_key)
        
        col1, col2 = st.columns(2)
        
        # --- 기능 1: XML 알맹이 추출 다운로드 ---
        with col1:
            st.subheader("📑 1. 공시 원본(XML) 알맹이만")
            st.info(f"개별 보고서 압축을 미리 풀어서 **파일 하나로** 묶어드립니다.")
            
            if st.button("알맹이만 쏙 뽑아 다운받기"):
                with st.spinner("보고서 목록 조회 중..."):
                    start_date = str(start_year) + "0101"
                    end_date = str(end_year) + "1231"
                    report_list = dart.list(corp_name, start=start_date, end=end_date, kind='A')
                
                if report_list is None or len(report_list) == 0:
                    st.error("해당 기간에 보고서가 없습니다.")
                else:
                    count = len(report_list)
                    st.write(f"총 {count}개의 보고서를 찾았습니다. 포장 뜯는 중... (잠시만 기다려주세요)")
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    zip_buffer = io.BytesIO()
                    
                    # 최종 ZIP 파일 생성
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as master_zip:
                        for i, row in report_list.iterrows():
                            rcept_no = row['rcept_no']
                            report_nm = clean_filename(row['report_nm'])
                            rcept_dt = row['rcept_dt']
                            
                            status_text.text(f"[{i+1}/{count}] {report_nm} 압축 해제 및 병합 중...")
                            
                            try:
                                # 1. DART API에서 개별 보고서(ZIP) 다운로드
                                url = f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={api_key}&rcept_no={rcept_no}"
                                res = requests.get(url)
                                
                                if res.status_code == 200:
                                    # 2. 메모리 상에서 압축 풀기 (파일로 저장 안 하고 바로 뜯음)
                                    with zipfile.ZipFile(io.BytesIO(res.content)) as inner_zip:
                                        # 압축 파일 안에 있는 내용물 확인
                                        for file_name in inner_zip.namelist():
                                            # XML, DSD(다트표준), HTML 파일만 골라냄
                                            if file_name.lower().endswith(('.xml', '.dsd', '.html', '.xhtml')):
                                                source_data = inner_zip.read(file_name)
                                                
                                                # 3. 이름 예쁘게 바꿔서 마스터 ZIP에 넣기
                                                # 예: 20240321_사업보고서_본문.xml
                                                ext = file_name.split('.')[-1]
                                                new_name = f"{rcept_dt}_{report_nm}_{rcept_no}.{ext}"
                                                
                                                master_zip.writestr(new_name, source_data)
                            except Exception as e:
                                print(f"Error processing {report_nm}: {e}")
                                
                            time.sleep(0.1)
                            progress_bar.progress((i + 1) / count)
                    
                    st.success("작업 완료! 압축 한 번만 풀면 됩니다.")
                    st.download_button(
                        label="📦 XML 모음(ZIP) 다운로드",
                        data=zip_buffer.getvalue(),
                        file_name=f"{corp_name}_{start_year}-{end_year}_XML모음.zip",
                        mime="application/zip"
                    )

        # --- 기능 2: 재무제표 통합 엑셀 (기존 유지) ---
        with col2:
            st.subheader("💰 2. 재무제표 통합 엑셀")
            st.info(f"{start_year}~{end_year}년 재무제표를 엑셀 하나로 합쳐줍니다.")
            
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
        st.error(f"오류: {e}")
else:
    st.info("👈 API 키와 회사명을 입력해주세요.")
