import streamlit as st
import OpenDartReader
import pandas as pd
import io
import time
import requests
import zipfile
import re

# 1. 페이지 설정
st.set_page_config(page_title="DART 맞춤형 다운로더", layout="wide")

st.title("🎯 DART 보고서 골라담기")
st.markdown("""
원하는 **회사**, 원하는 **기간**, 원하는 **보고서 종류**만 쏙쏙 골라서 다운로드하세요.
(본문 추출 기능 & 재무제표 통합 기능 포함)
""")

# 2. 사이드바 설정 (여기가 많이 바뀝니다!)
with st.sidebar:
    st.header("🔎 검색 조건 설정")
    
    # (1) API 키
    if "dart_api_key" in st.secrets:
        api_key = st.secrets["dart_api_key"]
        st.success("API Key 로드 완료! 🔐")
    else:
        api_key = st.text_input("OpenDART API Key", type="password")

    # (2) 회사명 (기본값 공란 처리)
    corp_name = st.text_input("회사명", "", placeholder="예: 삼성전자, 현대자동차")
    
    st.markdown("---")
    
    # (3) 기간 선택
    st.subheader("📅 기간 선택")
    period_option = st.radio(
        "기간 단위",
        ("2021~2025", "2016~2020", "2011~2015", "직접입력")
    )
    
    if period_option == "직접입력":
        col_y1, col_y2 = st.columns(2)
        with col_y1:
            start_year = st.number_input("시작", 2000, 2030, 2024)
        with col_y2:
            end_year = st.number_input("종료", 2000, 2030, 2024)
    else:
        start_year = int(period_option.split("~")[0])
        end_year = int(period_option.split("~")[1])

    st.markdown("---")

    # (4) [NEW] 보고서 종류 선택 (멀티 선택 기능)
    st.subheader("📑 문서 종류 선택")
    target_reports = st.multiselect(
        "다운로드할 보고서를 선택하세요",
        ["사업보고서", "반기보고서", "분기보고서"],
        default=["사업보고서", "반기보고서", "분기보고서"] # 기본은 전체 선택
    )
    
    st.caption("💡 '분기보고서'를 선택하면 1분기/3분기 보고서를 모두 포함합니다.")


# --- 파일명 정리 함수 ---
def clean_filename(text):
    return re.sub(r'[\\/*?:"<>|]', "_", text)

# 메인 로직
if api_key and corp_name: # 회사명이 입력되었을 때만 실행
    try:
        dart = OpenDartReader(api_key)
        
        col1, col2 = st.columns(2)
        
        # --- 기능 1: 본문만 쏙 뽑기 (필터 적용) ---
        with col1:
            st.subheader("📑 1. 보고서 본문(XML) 다운로드")
            
            # 선택한 보고서 종류 보여주기
            selected_str = ", ".join(target_reports)
            st.info(f"**{corp_name}**의 **{start_year}~{end_year}년** **[{selected_str}]** 본문을 추출합니다.")
            
            if st.button("선택한 보고서만 다운받기"):
                if not target_reports:
                    st.warning("⚠️ 보고서 종류를 최소 하나 이상 선택해주세요!")
                else:
                    with st.spinner("보고서 목록 조회 중..."):
                        start_date = str(start_year) + "0101"
                        end_date = str(end_year) + "1231"
                        
                        # 일단 전체 목록 가져오기
                        report_list = dart.list(corp_name, start=start_date, end=end_date, kind='A')
                    
                    if report_list is None or len(report_list) == 0:
                        st.error("해당 기간에 조회된 보고서가 없습니다.")
                    else:
                        # [핵심] 사용자가 선택한 종류만 남기기 (필터링)
                        # contains 로직: "사업보고서"가 있으면 사업보고서만, "반기"가 있으면 반기만...
                        filter_condition = report_list['report_nm'].str.contains('|'.join(target_reports))
                        filtered_list = report_list[filter_condition]
                        
                        count = len(filtered_list)
                        
                        if count == 0:
                            st.warning(f"검색 결과는 있지만, 선택하신 '{selected_str}'에 해당하는 보고서가 없습니다.")
                        else:
                            st.write(f"총 {count}개의 보고서를 찾았습니다. (전체 {len(report_list)}개 중 필터링됨)")
                            
                            progress_bar = st.progress(0)
                            status_text = st.empty()
                            zip_buffer = io.BytesIO()
                            
                            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as master_zip:
                                for i, row in filtered_list.iterrows():
                                    rcept_no = row['rcept_no']
                                    report_nm = clean_filename(row['report_nm'])
                                    rcept_dt = row['rcept_dt']
                                    
                                    status_text.text(f"[{i+1}/{count}] {report_nm} 본문 추출 중...")
                                    
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
                                    except:
                                        pass
                                    time.sleep(0.1)
                                    progress_bar.progress((i + 1) / count)
                            
                            st.success("다운로드 준비 완료!")
                            st.download_button(
                                label="📦 선택 보고서 모음(ZIP)",
                                data=zip_buffer.getvalue(),
                                file_name=f"{corp_name}_{start_year}-{end_year}_선택보고서.zip",
                                mime="application/zip"
                            )

        # --- 기능 2: 재무제표 통합 엑셀 (필터 적용) ---
        with col2:
            st.subheader("💰 2. 재무제표 통합 엑셀")
            st.info(f"선택하신 **[{selected_str}]**의 재무제표만 모아서 엑셀로 만듭니다.")
            
            if st.button("선택한 재무제표 수집 시작"):
                if not target_reports:
                    st.warning("⚠️ 보고서 종류를 최소 하나 이상 선택해주세요!")
                else:
                    progress_bar2 = st.progress(0)
                    status_text2 = st.empty()
                    
                    all_financials = []
                    years = list(range(start_year, end_year + 1))
                    
                    # [핵심] 사용자가 선택한 것만 코드 리스트에 담기
                    codes_to_fetch = []
                    if "사업보고서" in target_reports:
                        codes_to_fetch.append(('11011', '사업보고서'))
                    if "반기보고서" in target_reports:
                        codes_to_fetch.append(('11012', '반기보고서'))
                    if "분기보고서" in target_reports:
                        codes_to_fetch.append(('11013', '1분기보고서'))
                        codes_to_fetch.append(('11014', '3분기보고서'))
                    
                    total_steps = len(years)

                    for i, year in enumerate(years):
                        status_text2.text(f"{year}년도 데이터 수집 중...")
                        progress_bar2.progress((i + 1) / total_steps)
                        
                        for code, code_name in codes_to_fetch:
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
                            file_name=f"{corp_name}_{start_year}-{end_year}_선택재무제표.xlsx",
                            mime="application/vnd.ms-excel"
                        )
                    else:
                        st.warning("수집된 데이터가 없습니다. (해당 기간에 보고서가 없거나 API 제한일 수 있습니다)")

    except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")

elif not corp_name and api_key:
    st.info("👈 왼쪽 사이드바에 '회사명'을 입력하면 분석 도구가 나타납니다.")
else:
    st.info("👈 API 키와 회사명을 입력해주세요.")
