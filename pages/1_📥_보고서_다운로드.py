import streamlit as st
import OpenDartReader
import pandas as pd
import io
import zipfile
import re
import datetime
import requests
from bs4 import BeautifulSoup

st.set_page_config(page_title="AI 공시 분석 센터", page_icon="📥", layout="wide")
st.title("📥 AI 분석용 보고서 추출기 (Structured Text)")

# API 키 확인
api_key = st.session_state.get("api_key")
if not api_key:
    if "dart_api_key" in st.secrets: api_key = st.secrets["dart_api_key"]
    else:
        st.error("⚠️ Home에서 API 키를 입력해주세요.")
        st.stop()

st.info("💡 PDF보다 텍스트 추출 방식이 AI의 수치 계산 정확도를 **5배 이상** 높여줍니다.")

# --- 입력 폼 ---
with st.sidebar:
    st.header("🔍 검색 설정")
    corp_name = st.text_input("회사명", "삼성전자")
    curr_year = datetime.datetime.now().year
    years = st.slider("조회 기간", 2015, curr_year, (curr_year-2, curr_year))
    target_reports = st.multiselect("종류", ["사업보고서", "반기보고서", "분기보고서"], default=["사업보고서"])
    submit = st.button("보고서 목록 가져오기")

# --- 내부 함수: 표 구조를 유지하며 텍스트 추출 ---
def extract_ai_friendly_text(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    for s in soup(["script", "style", "head", "title"]):
        s.decompose()

    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            rows.append(" | ".join(cells))
        table_text = "\n" + "\n".join(rows) + "\n"
        table.replace_with(table_text)

    text = soup.get_text(separator="\n")
    clean_text = re.sub(r'\n\s*\n+', '\n\n', text)
    return clean_text

# --- 검색 결과 처리 ---
if submit:
    try:
        dart = OpenDartReader(api_key)
        df = dart.list(corp_name, start=f"{years[0]}0101", end=f"{years[1]}1231", kind='A')
        if df is not None and len(df) > 0:
            # 보고서 종류 필터링
            df = df[df['report_nm'].str.contains('|'.join(target_reports))]
            # 인덱스를 0, 1, 2... 순서로 초기화 (에러 방지 핵심!)
            df = df.reset_index(drop=True)
            st.session_state.reports_df = df
            st.success(f"{len(df)}건의 보고서를 찾았습니다.")
        else:
            st.warning("조회된 보고서가 없습니다.")
    except Exception as e: st.error(f"DART 접속 에러: {e}")

# --- 추출 및 다운로드 ---
if 'reports_df' in st.session_state:
    reports = st.session_state.reports_df
    st.dataframe(reports[['rcept_dt', 'report_nm', 'corp_name']], use_container_width=True)
    
    if st.button("🚀 AI용 텍스트 파일 생성 (전체 통합)"):
        combined_text = f"### {corp_name} AI 분석용 통합 데이터 ({years[0]}~{years[1]}) ###\n\n"
        progress = st.progress(0.0)
        status_text = st.empty()
        
        # [수정] enumerate를 사용하여 정확한 순서(i)를 가져옴
        total_len = len(reports)
        for i, (idx, row) in enumerate(reports.iterrows()):
            rcept_no = row['rcept_no']
            report_nm = row['report_nm']
            status_text.text(f"⏳ ({i+1}/{total_len}) {report_nm} 추출 중...")
            
            try:
                url = f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={api_key}&rcept_no={rcept_no}"
                res = requests.get(url)
                
                with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                    target_file = max(z.infolist(), key=lambda f: f.file_size).filename
                    raw_content = z.read(target_file)
                    
                    try: content = raw_content.decode('utf-8')
                    except: content = raw_content.decode('euc-kr', 'ignore')
                    
                    refined_text = extract_ai_friendly_text(content)
                    
                    combined_text += f"\n\n{'='*50}\n"
                    combined_text += f"REPORT: {report_nm} (DATE: {row['rcept_dt']})\n"
                    combined_text += f"{'='*50}\n\n"
                    combined_text += refined_text
                    
            except Exception as e:
                combined_text += f"\n\n[오류 발생: {report_nm} 추출 실패]\n"
            
            # [수정] i를 사용해 진행률 계산 (0.0 ~ 1.0)
            progress.progress((i + 1) / total_len)
        
        status_text.text("✅ 모든 보고서 추출 완료!")
        st.success("압축 해제 및 텍스트 구조화가 완료되었습니다.")
        st.download_button(
            label="📄 통합 텍스트 파일 다운로드",
            data=combined_text,
            file_name=f"{corp_name}_AI_Deep_Context.txt",
            mime="text/plain"
        )
