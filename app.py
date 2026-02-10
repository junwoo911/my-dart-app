import streamlit as st
import OpenDartReader
import pandas as pd
import io

# 1. 페이지 설정 (스마트폰 화면에 맞게)
st.set_page_config(page_title="내 손안의 공시 다운로더", layout="centered")

st.title("📊 DART 재무제표 다운로더")
st.write("스마트폰에서 간편하게 공시 데이터를 받아보세요.")

# 2. 서버 금고에서 API 키 가져오기 (자동 입력)
if "dart_api_key" in st.secrets:
    api_key = st.secrets["dart_api_key"]
else:
    # 혹시 금고 설정이 안 되어 있을 때를 대비해 입력창 남겨두기
    api_key = st.text_input("OpenDART API Key를 입력하세요", type="password")
    
if api_key:
    try:
        # DART 객체 생성
        dart = OpenDartReader(api_key)
        
        # 3. 검색 조건 입력
        corp_name = st.text_input("회사명 (예: 삼성전자)", "삼성전자")
        year = st.selectbox("연도 선택", ["2026", "2025", "2024", "2023", "2022", "2021"])
        report_code = st.selectbox("보고서 종류", [
            ("11011", "사업보고서 (연간)"),
            ("11012", "반기보고서"),
            ("11013", "1분기보고서"),
            ("11014", "3분기보고서")
        ], format_func=lambda x: x[1])
        
        if st.button("데이터 조회하기"):
            with st.spinner('DART 서버에서 데이터를 가져오는 중...'):
                # 재무제표 가져오기
                fs = dart.finstate(corp_name, int(year), report_code[0])
                
                if fs is None:
                    st.error("데이터를 찾을 수 없습니다. 회사명이나 연도를 확인해주세요.")
                else:
                    st.success(f"{corp_name} {year}년 데이터 조회 성공!")
                    
                    # 미리보기 보여주기
                    st.dataframe(fs.head())
                    
                    # 4. 엑셀 다운로드 버튼
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                        fs.to_excel(writer, index=False, sheet_name='Sheet1')
                        
                    st.download_button(
                        label="📥 엑셀 파일로 다운로드",
                        data=buffer,
                        file_name=f"{corp_name}_{year}_재무제표.xlsx",
                        mime="application/vnd.ms-excel"
                    )
                    
    except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")
        st.info("API 키가 정확한지 확인해주세요.")
else:

    st.info("👆 먼저 API Key를 입력해주세요.")

