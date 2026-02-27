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

st.title("⚡ 기업 보고서 원클릭 다운로드 (AI 최적화 버전)")

# --- 1. API 키 설정 ---
if 'api_key' not in st.session_state:
    if "dart_api_key" in st.secrets:
        st.session_state.api_key = st.secrets["dart_api_key"]
    else:
        st.error("API 키가 없습니다. secrets.toml을 확인해주세요.")
        st.stop()

api_key = st.session_state.api_key

# --- 2. DART 직접 접속 함수 (6자리 종목코드 지원 업그레이드) ---
@st.cache_data(ttl=600)
def fetch_report_list_direct(corp_query, start_date, end_date):
    try:
        dart = OpenDartReader(api_key)
        
        # 입력값이 6자리 숫자인지 판단
        if corp_query.isdigit() and len(corp_query) == 6:
            corp_list = dart.corp_codes
            target_row = corp_list[corp_list['stock_code'] == corp_query]
            if target_row.empty:
                return None, corp_query
            corp_code = target_row.iloc[0]['corp_code']
            actual_corp_name = target_row.iloc[0]['corp_name']
        else:
            corp_code = dart.find_corp_code(corp_query)
            actual_corp_name = corp_query
            
        if not corp_code:
            return None, corp_query
    except:
        return None, corp_query

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
            return df, actual_corp_name
        else:
            return pd.DataFrame(), actual_corp_name 
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

# --- 4. 텍스트 변환 함수 (토큰 절약 로직 이식 완료) ---
def extract_ai_friendly_text(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    for s in soup(["script", "style", "head", "svg", "img"]):
        s.decompose()
        
    for nav in soup.find_all(text=re.compile(r"본문\s*위치로\s*이동|목차|TOP")):
        nav.extract()

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
        if rows:
            table_md = "\n" + "\n".join(rows) + "\n"
            table.replace_with(table_md)
            
    raw_text = soup.get_text(separator="\n")
    lines = raw_text.split('\n')
    
    # [블랙리스트 필터링 - AI 분석용 토큰 절약]
    blacklist = ["V. 회계감사인", "VI. 이사회", "X. 대주주", "XII. 상세표"]
    all_markers = [
        "I. 회사의 개요", "II. 사업의 내용", "III. 재무에 관한 사항",
        "IV. 이사의 진단", "V. 회계감사인", "VI. 이사회", "VII. 주주에 관한 사항",
        "VIII. 임원 및 직원", "IX. 계열회사", "X. 대주주", "XI. 그 밖에 투자자 보호",
        "XII. 상세표", "【", "첨부서류"
    ]

    extracted_lines = []
    skip_mode = False
    for line in lines:
        clean_line = line.strip()
        if any(clean_line.startswith(m) for m in all_markers):
            skip_mode = any(clean_line.startswith(b) for b in blacklist)
                
        if not skip_mode: 
            extracted_lines.append(line)
            
    filtered_text = "\n".join(extracted_lines)
    filtered_text = re.sub(r' +', ' ', filtered_text)
    filtered_text = re.sub(r'\n\s*\n+', '\n\n', filtered_text)
    filtered_text = re.sub(r'[-=+#]{5,}', '', filtered_text)
    return filtered_text.strip()

# --- 5. UI 구성 ---
with st.container(border=True):
    col_input, col_btn = st.columns([4, 1])
    with col_input:
        corp_name_input = st.text_input("회사명 또는 6자리 종목코드 입력", placeholder="예: 삼성전자 또는 005930", label_visibility="collapsed")
    with col_btn:
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
    if not corp_name_input:
        st.warning("회사명 또는 6자리 종목코드를 입력해주세요.")
        st.stop()
    
    start_date = f"{start_year}0101"
    end_date = f"{end_year}1231"
    
    with st.spinner(f"📡 '{corp_name_input}' 공시 목록을 가져오고 있습니다..."):
        try:
            result = fetch_report_list_direct(corp_name_input.strip(), start_date, end_date)
            
            if result is not None:
                raw_df, actual_corp_name = result
            else:
                raw_df, actual_corp_name = None, corp_name_input

            if raw_df is not None and len(raw_df) > 0:
                df = classify_and_filter(raw_df, selected_types)
                
                if not df.empty:
                    st.success(f"✅ 총 {len(df)}건 검색! 즉시 다운로드를 시작합니다. (기업명: {actual_corp_name})")
                    st.dataframe(df[['rcept_dt', 'report_nm', 'smart_type']], use_container_width=True, hide_index=True)
                    
                    with st.status("🚀 텍스트 변환 및 ZIP 생성 중...", expanded=True) as status:
                        zip_buffer = io.BytesIO()
                        headers_download = {'User-Agent': 'Mozilla/5.0'}
                        total = len(df)

                        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                            for i, (idx, row) in enumerate(df.iterrows()):
                                
                                rpt_name = row['report_nm']
                                fname = re.sub(r'[\\/*?:"<>|]', "", f"{actual_corp_name}_{rpt_name}.txt")
                                
                                status.write(f"📥 ({i+1}/{total}) 저장: {fname}")
                                
                                try:
                                    d_url = f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={api_key}&rcept_no={row['rcept_no']}"
                                    res = requests.get(d_url, headers=headers_download, timeout=15)
                                    with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                                        t_file = max(z.infolist(), key=lambda f: f.file_size).filename
                                        content = z.read(t_file).decode('utf-8', 'ignore')
                                        final_txt = extract_ai_friendly_text(content)
                                        
                                        header_info = f"### {actual_corp_name} {rpt_name} ###\n"
                                        header_info += f"접수일: {row['rcept_dt']}\n"
                                        header_info += f"분류: {row['smart_type']}\n\n"
                                        
                                        zip_file.writestr(fname, header_info + final_txt)
                                except Exception as e:
                                    status.write(f"⚠️ 실패: {fname}")
                        
                        status.update(label="🎉 생성 완료! 아래 버튼을 누르세요.", state="complete", expanded=False)
                    
                    if start_year == end_year:
                        year_str = f"{start_year}"
                    else:
                        year_str = f"{start_year}-{end_year}"
                    
                    if len(selected_types) == 1:
                        type_str = selected_types[0]
                    elif len(selected_types) <= 2:
                        type_str = "+".join(selected_types)
                    else:
                        type_str = "다종보고서"

                    final_zip_name = f"{actual_corp_name}_{year_str}_{type_str}_모음.zip"

                    st.download_button(
                        label=f"💾 {final_zip_name} 저장",
                        data=zip_buffer.getvalue(),
                        file_name=final_zip_name,
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
