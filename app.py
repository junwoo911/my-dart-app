import streamlit as st
import OpenDartReader
import pandas as pd
import io
import zipfile
import re
import requests
import json
from bs4 import BeautifulSoup

# --- 페이지 설정 ---
st.set_page_config(
    page_title="보고서 다운로드", 
    page_icon="📥", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.title("📥 기업 보고서 즉시 다운로드 (Direct Mode)")

# --- 1. API 키 설정 ---
if 'api_key' not in st.session_state:
    if "dart_api_key" in st.secrets:
        st.session_state.api_key = st.secrets["dart_api_key"]
    else:
        st.error("API 키가 없습니다. secrets.toml을 확인해주세요.")
        st.stop()

api_key = st.session_state.api_key

# --- 2. [핵심] DART 직접 접속 함수 (라이브러리 미사용) ---
# 라이브러리를 거치지 않고 직접 브라우저인 척 통신합니다.
@st.cache_data(ttl=600)
def fetch_report_list_direct(corp_name, start_date, end_date):
    # 1. 고유번호(corp_code)를 알아내기 위해 OpenDartReader를 잠시 씁니다.
    # (이건 XML 파일을 받아오는 거라 차단이 덜합니다)
    try:
        dart = OpenDartReader(api_key)
        corp_code = dart.find_corp_code(corp_name)
        if not corp_code:
            return None
    except:
        return None

    # 2. 실제 공시 목록 요청 (여기가 차단되는 구간입니다)
    url = "https://opendart.fss.or.kr/api/list.json"
    params = {
        'crtfc_key': api_key,
        'corp_code': corp_code,
        'bgn_de': start_date,
        'end_de': end_date,
        'pblntf_detail_ty': 'A001', # A001: 정기공시 (사업,반기,분기)
        'page_count': 100
    }
    
    # 강력한 위장 헤더
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://dart.fss.or.kr/',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Connection': 'keep-alive'
    }

    try:
        # 타임아웃 10초 설정 (무한 로딩 방지)
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        data = resp.json()
        
        if data.get('status') == '000':
            df = pd.DataFrame(data['list'])
            return df
        else:
            return None
    except Exception as e:
        # 에러 내용을 반환해서 화면에 찍어줍니다
        raise Exception(f"접속 실패: {str(e)}")

# --- 3. 텍스트 변환 함수 ---
def extract_ai_friendly_text(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    for s in soup(["script", "style", "head", "svg", "img"]):
        s.decompose()
    for table in soup.find_all("table"):
        rows = []
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if headers:
            rows.append("| " + " | ".join(headers) + " |")
            rows.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            if cells:
                rows.append("| " + " | ".join(cells) + " |")
        table_md = "\n" + "\n".join(rows) + "\n"
        table.replace_with(table_md)
    text = soup.get_text(separator="\n")
    return re.sub(r'\n\s*\n+', '\n\n', text).strip()

# --- 4. UI 구성 ---
with st.container(border=True):
    col_input, col_btn = st.columns([4, 1])
    with col_input:
        corp_name = st.text_input("회사명 입력", placeholder="예: 삼성전자", label_visibility="collapsed")
    with col_btn:
        btn_search = st.button("검색", type="primary", use_container_width=True)

    with st.expander("📅 설정", expanded=True):
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            start_year = st.number_input("시작", 2000, 2030, 2024)
        with col2:
            end_year = st.number_input("종료", 2000, 2030, 2025)
        with col3:
            report_options = ["1분기보고서", "반기보고서", "3분기보고서", "사업보고서"]
            selected_types = st.multiselect("종류", report_options, default=["사업보고서"])

# --- 5. 실행 로직 ---
if btn_search or ('target_df' in st.session_state and st.session_state.target_df is not None):
    if btn_search:
        if not corp_name:
            st.warning("회사명을 입력해주세요.")
            st.stop()
        
        start_date = f"{start_year}0101"
        end_date = f"{end_year}1231"
        
        with st.spinner(f"🚀 '{corp_name}' DART 서버 뚫는 중... (10초 타임아웃)"):
            try:
                # 직접 만든 함수 호출
                df = fetch_report_list_direct(corp_name, start_date, end_date)
                
                if df is not None and len(df) > 0:
                    conditions = []
                    # 필터링 로직
                    if "사업보고서" in selected_types: conditions.append(df['report_nm'].str.contains("사업보고서"))
                    if "반기보고서" in selected_types: conditions.append(df['report_nm'].str.contains("반기보고서"))
                    if "1분기보고서" in selected_types: conditions.append(df['report_nm'].str.contains(r"분기보고서.*[30]3월|[1]분기"))
                    if "3분기보고서" in selected_types: conditions.append(df['report_nm'].str.contains(r"분기보고서.*[0]9월|[3]분기"))

                    if conditions:
                        final_mask = pd.concat(conditions, axis=1).any(axis=1)
                        filtered_df = df[final_mask].copy().reset_index(drop=True)
                    else:
                        filtered_df = pd.DataFrame()

                    st.session_state.target_df = filtered_df
                    st.session_state.current_corp = corp_name
                else:
                    st.error("❌ 검색 결과가 없거나 차단되었습니다.")
                    st.session_state.target_df = None
            except Exception as e:
                st.error(f"⚠️ 연결 오류: {e}")
                st.caption("DART 서버가 해외(Streamlit) 접속을 차단했을 가능성이 높습니다.")

    # 결과 및 다운로드
    if 'target_df' in st.session_state and st.session_state.target_df is not None:
        df = st.session_state.target_df
        corp_name_fixed = st.session_state.get('current_corp', corp_name)
        
        st.divider()
        st.subheader(f"✅ 검색 결과 ({len(df)}건)")
        st.dataframe(df[['rcept_dt', 'report_nm']], use_container_width=True, hide_index=True)
        
        if len(df) > 0:
            if st.button("ZIP 다운로드 생성", type="primary"):
                zip_buffer = io.BytesIO()
                progress = st.progress(0)
                status = st.empty()
                
                headers_download = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }

                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for i, row in df.iterrows():
                        fname = re.sub(r'[\\/*?:"<>|]', "", f"{corp_name_fixed}_{row['report_nm']}.txt")
                        status.info(f"다운로드 중: {fname}")
                        try:
                            # 다운로드도 requests 직접 사용
                            d_url = f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={api_key}&rcept_no={row['rcept_no']}"
                            res = requests.get(d_url, headers=headers_download, timeout=15)
                            
                            with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                                t_file = max(z.infolist(), key=lambda f: f.file_size).filename
                                content = z.read(t_file).decode('utf-8', 'ignore')
                                final_txt = extract_ai_friendly_text(content)
                                zip_file.writestr(fname, final_txt)
                        except:
                            pass
                        progress.progress((i+1)/len(df))
                
                status.success("완료!")
                st.download_button("💾 파일 저장", zip_buffer.getvalue(), f"{corp_name_fixed}.zip", "application/zip")
