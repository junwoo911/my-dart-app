import streamlit as st
import OpenDartReader
import pandas as pd
import io
import time
import requests
import zipfile
import re

# 1. 페이지 설정
st.set_page_config(page_title="DART PDF 강력 다운로더", layout="wide")

st.title("📄 DART 보고서 PDF 싹슬이 (최종판)")
st.markdown("""
DART 서버의 차단을 피하기 위해 **브라우저로 위장**하여 PDF를 다운로드합니다.
(서버 부하 방지를 위해 속도가 조금 느릴 수 있습니다.)
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

# --- 내부 함수: DART PDF 주소 따오기 (강력한 위장술) ---
def get_pdf_link_strong(rcept_no):
    try:
        # 가짜 헤더 (나는 로봇이 아니다!)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': f'http://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}',
            'Host': 'dart.fss.or.kr',
            'Connection': 'keep-alive'
        }
        
        # 1. 뷰어 페이지 접속
        url = f"http://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
        session = requests.Session()
        response = session.get(url, headers=headers, timeout=10)
        
        # 2. 숨겨진 dcmNo 찾기 (여러가지 패턴으로 시도)
        text = response.text
        
        # 패턴 1: Javascript viewDoc 함수 내부
        match = re.search(r"viewDoc\('(\d+)', '(\d+)', '(\d+)', '(\d+)', '(\d+)', '(\S+)'\);", text)
        if match:
            dcm_no = match.group(2) # 두 번째 숫자가 dcmNo
            return f"http://dart.fss.or.kr/pdf/download/pdf.do?rcp_no={rcept_no}&dcm_no={dcm_no}"
        
        # 패턴 2: 직접적인 변수 선언
        match2 = re.search(r'dcmNo"\s*:\s*"(\d+)"', text)
        if match2:
            dcm_no = match2.group(1)
            return f"http://dart.fss.or.kr/pdf/download/pdf.do?rcp_no={rcept_no}&dcm_no={dcm_no}"

        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

# 메인 로직
if api_key and corp_name:
    try:
        dart = OpenDartReader(api_key)
        
        col1, col2 = st.columns(2)
        
        # --- 기능 1: PDF 강제 다운로드 ---
        with col1:
            st.subheader("📑 1. 보고서 PDF 다운로드")
            st.info(f"{start_year}~{end_year}년 보고서를 '사람인 척' 접속해서 가져옵니다.")
            
            if st.button("PDF 싹 다 다운받기"):
                with st.spinner("보고서 목록 조회 중..."):
                    start_date = str(start_year) + "0101"
                    end_date = str(end_year) + "1231"
                    # 사업, 반기, 분기 보고서 검색
                    report_list = dart.list(corp_name, start=start_date, end=end_date, kind='A')
                
                if report_list is None or len(report_list) == 0:
                    st.error("해당 기간에 보고서가 없습니다.")
                else:
                    count = len(report_list)
                    st.write(f"총 {count}개의 보고서를 찾았습니다. 다운로드 시작! (시간이 좀 걸립니다)")
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    zip_buffer = io.BytesIO()
                    
                    success_count = 0
                    
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as master_zip:
                        for i, row in report_list.iterrows():
                            rcept_no = row['rcept_no']
                            report_nm = row['report_nm']
                            rcept_dt = row['rcept_dt']
                            
                            status_text.markdown(f"**[{i+1}/{count}]** `{report_nm}` 처리 중...")
                            
                            # 강력한 함수로 PDF 주소 따오기
                            pdf_url = get_pdf_link_strong(rcept_no)
                            
                            if pdf_url:
                                try:
                                    # PDF 다운로드 (여기도 위장 헤더 사용)
                                    headers = {
                                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                                    }
                                    pdf_res = requests.get(pdf_url, headers=headers, timeout=15)
                                    
                                    if pdf_res.status_code == 200 and len(pdf_res.content) > 1000:
                                        clean_name = f"{rcept_dt}_{report_nm}.pdf"
                                        master_zip.writestr(clean_name, pdf_res.content)
                                        success_count += 1
                                    else:
                                        print(f"다운로드 실패: {report_nm}")
                                except:
                                    pass
                            else:
                                print(f"문서번호 추출 실패: {report_nm}")
                            
                            # DART 서버가 눈치채지 못하게 1초 쉬기 (중요!)
                            time.sleep(1) 
                            progress_bar.progress((i + 1) / count)
                    
                    if success_count > 0:
                        st.success(f"🎉 성공! 총 {success_count}개의 PDF를 확보했습니다.")
                        st.download_button(
                            label="📦 PDF 모음(ZIP) 다운로드",
                            data=zip_buffer.getvalue(),
                            file_name=f"{corp_name}_{start_year}-{end_year}_PDF보고서.zip",
                            mime="application/zip"
                        )
                    else:
                        st.error("😢 PDF를 가져오지 못했습니다. (서버 보안이 너무 강력하여 클라우드 접속을 차단했을 수 있습니다.)")

        # --- 기능 2: 재무제표 통합 엑셀 (기존 유지) ---
        with col2:
            st.subheader("💰 2. 재무제표 통합 엑셀")
            st.info("재무데이터는 문제없이 잘 작동합니다!")
            
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
