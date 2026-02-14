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
    page_title="기업 보고서 원클릭", 
    page_icon="⚡", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.title("⚡ 기업 보고서 원클릭 다운로드")

# --- 1. API 키 설정 ---
if 'api_key' not in st.session_state:
    if "dart_api_key" in st.secrets:
        st.session_state.api_key = st.secrets["dart_api_key"]
    else:
        st.error("API 키가 없습니다. secrets.toml을 확인해주세요.")
        st.stop()

api_key = st.session_state.api_key

# --- 2. DART 직접 접속 함수 ---
@st.cache_data(ttl=600)
def fetch_report_list_direct(corp_name, start_date, end_date):
    try:
        dart = OpenDartReader(api_key)
        corp_code = dart.find_corp_code(corp_name)
        if not corp_code:
            return None
    except:
        return None

    url = "https://opendart.fss.or.kr/api/list.json"
    params = {
        'crtfc_key': api_key,
        'corp_code': corp_code,
        'bgn_de': start_date,
        'end_de': end_date,
        'pblntf_ty': 'A',
        'page_count': 100
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://dart.fss.or.kr/',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Connection': 'keep-alive'
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        data = resp.json()
        
        if data.get('status') == '000':
            df = pd.DataFrame(data['list'])
            return df
        else:
            return pd.DataFrame() 
    except Exception as e:
        raise Exception(f"접속 실패: {str(e)}")

# --- 3. 분류 및 필터링 로직 ---
def classify_and_filter(df, selected_types):
    if df is None or len(df) == 0:
        return df

    df = df.copy()
    df = df.sort_values(by='rcept_dt', ascending=False).reset_index(drop=True)

    smart_types = []
    for idx, row in df.iterrows():
        nm = row['report_nm']
        dt = row['rcept_dt']
        month = int(dt[4:6]) 
        
        r_type = "기타"
        if "사업보고서" in nm: r_type = "사업보고서"
        elif "반기보고서" in nm: r_type = "반기보고서"
        elif "분기보고서" in nm:
            if "1분기" in nm: r_type = "1분기보고서"
            elif "3분기" in nm: r_type = "3분기보고서"
            elif 4 <= month <= 6: r_type = "1분기보고서"
            elif 9 <= month <= 12: r_type = "3분기보고서"
            else: r_type = "분기보고서(기타)"
        smart_types.append(r_type)

    df['smart_type'] = smart_types
    
    filtered_df = df[df['smart_type'].isin(selected_types)].copy()
    
    if not filtered_df.empty:
        filtered_df['year_key'] = filtered_df['rcept_dt'].str[:4]
        final_df = filtered_df.drop_duplicates(subset=['smart_type', 'year_key'], keep='first')
        return final_df.drop(columns=['year_key'])
    else:
        return filtered_df

# --- 4. 텍스트 변환 함수 ---
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

# --- 5. UI 구성 ---
with st.container(border=True):
    col_input, col_btn = st.columns([4, 1])
    with col_input:
        corp_name = st.text_input("회사명 입력", placeholder="예: 삼성전자", label_visibility="collapsed")
    with col_btn:
        # [수정] 버튼 이름을 심플하게 '검색'으로 변경
        btn_start = st.button("검색", type="primary", use_container_width=True)

    with st.expander("📅 설정", expanded=True):
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            start_year = st.number_input("시작", 2000, 2030, 2024)
        with col2:
            end_year = st.number_input("종료", 2000, 2030, 2025)
        with col3:
            report_options = ["1분기보고서", "반기보고서", "3분기보고서", "사업보고서"]
            selected_types = st.multiselect("종류", report_options, default=["사업보고서"])

# --- 6. 실행 로직 ---
if btn_start:
    if not corp_name:
        st.warning("회사명을 입력해주세요.")
        st.stop()
    
    start_date = f"{start_year}0101"
    end_date = f"{end_year}1231"
    
    with st.spinner(f"📡 '{corp_name}' 공시 목록을 가져오고 있습니다..."):
        try:
            raw_df = fetch_report_list_direct(corp_name, start_date, end_date)
            
            if raw_df is not None and len(raw_df) > 0:
                df = classify_and_filter(raw_df, selected_types)
                
                if not df.empty:
                    st.success(f"✅ 총 {len(df)}건 검색! 즉시 다운로드를 시작합니다.")
                    st.dataframe(df[['rcept_dt', 'report_nm', 'smart_type']], use_container_width=True, hide_index=True)
                    
                    with st.status("🚀 텍스트 변환 및 ZIP 생성 중...", expanded=True) as status:
                        zip_buffer = io.BytesIO()
                        headers_download = {'User-Agent': 'Mozilla/5.0'}
                        total = len(df)

                        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                            for i, (idx, row) in enumerate(df.iterrows()):
                                
                                # [파일명] DART 원본 제목 유지 (특수문자만 제거)
                                rpt_name = row['report_nm']
                                fname = re.sub(r'[\\/*?:"<>|]', "", f"{corp_name}_{rpt_name}.txt")
                                
                                status.write(f"📥 ({i+1}/{total}) 저장: {fname}")
                                
                                try:
                                    d_url = f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={api_key}&rcept_no={row['rcept_no']}"
                                    res = requests.get(d_url, headers=headers_download, timeout=15)
                                    with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                                        t_file = max(z.infolist(), key=lambda f: f.file_size).filename
                                        content = z.read(t_file).decode('utf-8', 'ignore')
                                        final_txt = extract_ai_friendly_text(content)
                                        
                                        header_info = f"### {corp_name} {rpt_name} ###\n"
                                        header_info += f"접수일: {row['rcept_dt']}\n"
                                        header_info += f"분류: {row['smart_type']}\n\n"
                                        
                                        zip_file.writestr(fname, header_info + final_txt)
                                except Exception as e:
                                    status.write(f"⚠️ 실패: {fname}")
                        
                        status.update(label="🎉 생성 완료! 아래 버튼을 누르세요.", state="complete", expanded=False)
                    
                    # [압축파일명] '보고서_모음.zip'으로 깔끔하게
                    st.download_button(
                        label="💾 보고서 모음(ZIP) 저장",
                        data=zip_buffer.getvalue(),
                        file_name=f"{corp_name}_보고서_모음.zip",
                        mime="application/zip",
                        type="primary",
                        use_container_width=True
                    )
                    
                else:
                    st.warning("조건에 맞는 보고서가 없습니다.")
            else:
                st.error("❌ 검색된 공시가 없습니다.")
        except Exception as e:
            st.error(f"오류 발생: {e}")
