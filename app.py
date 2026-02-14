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

st.title("📥 기업 보고서 즉시 다운로드 (Date Logic)")

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

    # 모든 정기공시(A001) 가져오기
    url = "https://opendart.fss.or.kr/api/list.json"
    params = {
        'crtfc_key': api_key,
        'corp_code': corp_code,
        'bgn_de': start_date,
        'end_de': end_date,
        'pblntf_detail_ty': 'A001', 
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
            return pd.DataFrame() # 결과 없으면 빈 표 반환
    except Exception as e:
        raise Exception(f"접속 실패: {str(e)}")

# --- [핵심 수정] 날짜 기반 강력 분류 함수 ---
def classify_and_filter(df, selected_types):
    if df is None or len(df) == 0:
        return df

    # 1. 날짜 기준 정렬 (최신순)
    df = df.sort_values(by='rcept_dt', ascending=False).reset_index(drop=True)

    # 2. 분류 로직 (이름 + 제출월)
    def get_smart_type(row):
        nm = row['report_nm']
        dt = row['rcept_dt'] # YYYYMMDD
        month = int(dt[4:6]) # 월 추출
        
        if "사업보고서" in nm:
            return "사업보고서"
        elif "반기보고서" in nm:
            return "반기보고서"
        elif "분기보고서" in nm:
            # 이름에 명확히 1분기/3분기가 있으면 그걸 따름
            if "1분기" in nm: return "1분기보고서"
            if "3분기" in nm: return "3분기보고서"
            
            # 이름에 없으면 '제출 월'로 판단 (가장 확실함)
            # 1분기보고서: 보통 5월 제출 (4,5,6월 허용)
            if 4 <= month <= 6:
                return "1분기보고서"
            # 3분기보고서: 보통 11월 제출 (10,11,12월 허용)
            elif 10 <= month <= 12:
                return "3분기보고서"
            else:
                return "분기보고서(기타)"
        else:
            return "기타"

    df['smart_type'] = df.apply(get_smart_type, axis=1)
    
    # 3. 사용자 선택 필터링
    filtered_df = df[df['smart_type'].isin(selected_types)].copy()
    
    # 4. 최종본만 남기기 (중복 제거)
    # 같은 종류(smart_type)이고, 같은 접수년도(year)라면 최신 것만 남김
    # 단, 기재정정 등이 있을 수 있으므로 '제목'에서 기간을 추출해서 그룹핑
    
    def get_period_key(row):
        # (2024.03) 같은 날짜 패턴 추출
        match = re.search(r'\((\d{4}\.\d{2})\)', row['report_nm'])
        if match:
            return match.group(1)
        # 없으면 접수일 기준으로 대강 만듦 (YYYY + 상반기/하반기 등)
        return row['rcept_dt'][:6] 

    filtered_df['period_key'] = filtered_df.apply(get_period_key, axis=1)
    
    # 같은 보고서 종류 + 같은 기간 키를 가진 것 중 '가장 위(최신)'만 남김
    final_df = filtered_df.drop_duplicates(subset=['smart_type', 'period_key'], keep='first')
    
    return final_df.drop(columns=['period_key'])

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
        corp_name = st.text_input("회사명 입력", placeholder="예: 삼성전자, 파라다이스", label_visibility="collapsed")
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
        
        with st.spinner(f"🚀 '{corp_name}' 보고서 수집 중..."):
            try:
                # 1. 일단 다 가져옴
                raw_df = fetch_report_list_direct(corp_name, start_date, end_date)
                
                if raw_df is not None and len(raw_df) > 0:
                    st.session_state.raw_df = raw_df # 디버깅용 저장
                    
                    # 2. 분류 및 필터링 적용
                    clean_df = classify_and_filter(raw_df, selected_types)
                    
                    st.session_state.target_df = clean_df
                    st.session_state.current_corp = corp_name
                else:
                    st.error("❌ DART에서 조회된 공시가 없습니다.")
                    st.session_state.target_df = None
                    st.session_state.raw_df = None
            except Exception as e:
                st.error(f"⚠️ 오류: {e}")

    # 결과 및 다운로드
    if 'target_df' in st.session_state:
        df = st.session_state.target_df
        raw_df = st.session_state.get('raw_df', pd.DataFrame())
        corp_name_fixed = st.session_state.get('current_corp', corp_name)
        
        if df is not None and len(df) > 0:
            st.divider()
            st.subheader(f"✅ 검색 결과 ({len(df)}건)")
            st.dataframe(df[['rcept_dt', 'report_nm', 'smart_type']], use_container_width=True, hide_index=True)
            
            if st.button("ZIP 다운로드 생성", type="primary"):
                zip_buffer = io.BytesIO()
                progress = st.progress(0)
                status = st.empty()
                headers_download = {'User-Agent': 'Mozilla/5.0'}

                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for i, row in df.iterrows():
                        rpt_name = row['report_nm']
                        fname = re.sub(r'[\\/*?:"<>|]', "", f"{corp_name_fixed}_{rpt_name}.txt")
                        status.info(f"다운로드 중: {fname}")
                        try:
                            d_url = f"https://opendart.fss.or.kr/api/document.xml?crtfc_key={api_key}&rcept_no={row['rcept_no']}"
                            res = requests.get(d_url, headers=headers_download, timeout=15)
                            with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                                t_file = max(z.infolist(), key=lambda f: f.file_size).filename
                                content = z.read(t_file).decode('utf-8', 'ignore')
                                final_txt = extract_ai_friendly_text(content)
                                header_info = f"### {corp_name_fixed} {rpt_name} ###\n접수일: {row['rcept_dt']}\n분류: {row['smart_type']}\n\n"
                                zip_file.writestr(fname, header_info + final_txt)
                        except: pass
                        progress.progress((i+1)/len(df))
                
                status.success("완료!")
                st.download_button("💾 파일 저장", zip_buffer.getvalue(), f"{corp_name_fixed}_Final.zip", "application/zip")
        
        # [안전장치] 필터링 결과는 0건인데, 실제 원본 데이터는 있는 경우
        elif raw_df is not None and len(raw_df) > 0:
            st.warning("⚠️ 필터링 결과가 없습니다. (하지만 원본 공시는 존재합니다)")
            with st.expander("🔍 전체 공시 목록 확인하기 (클릭)"):
                st.dataframe(raw_df[['rcept_dt', 'report_nm']], use_container_width=True)
                st.info("원하는 보고서가 목록에 있는데 안 보인다면, '보고서 종류' 선택을 확인해주세요.")
