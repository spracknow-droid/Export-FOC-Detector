import streamlit as st
import pytesseract
from PIL import Image
import pandas as pd
import pdfplumber
import io
import re

st.set_page_config(layout="wide", page_title="수출신고필증 FOC 추출기")

def extract_text_from_file(uploaded_file):
    """파일 유형에 따라 텍스트 추출"""
    try:
        if uploaded_file.type in ['image/png', 'image/jpeg']:
            image = Image.open(uploaded_file)
            return pytesseract.image_to_string(image, lang='kor+eng')
        elif uploaded_file.type == 'application/pdf':
            full_text = ""
            with pdfplumber.open(uploaded_file) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text: full_text += text + "\n"
            return full_text
    except Exception as e:
        st.error(f"{uploaded_file.name} 처리 중 오류: {e}")
        return ""

def parse_export_data(text, filename):
    """텍스트에서 필요한 정보 추출 및 FOC 판별"""
    data = {"파일명": filename}
    
    # 전체 텍스트를 대문자로 변환 (비교를 쉽게 하기 위함)
    upper_text = text.upper()
    
    # 1. 신고번호 추출
    match_sin_go = re.search(r'\b(\d{5}-\d{2}-\d{6}[A-Z])\b', text)
    data['신고번호'] = match_sin_go.group(1) if match_sin_go else "미확인"
    
    # 2. 거래구분 추출 (숫자 2자리)
    match_trade = re.search(r'거래구분\s*[:：]?\s*(\d{2})', text)
    trade_code = match_trade.group(1) if match_trade else ""
    data['거래구분'] = trade_code
    
    # 3. 품명 및 규격 추출 (범위를 더 넓게 잡음)
    # 품명(28번)부터 검사사항(30번) 이전까지의 내용을 최대한 긁어옴
    match_item = re.search(r'품\s*명\s*[:：]?\s*(.*?)\s*(?:29|30|검사사항)', text, re.S | re.I)
    item_content = match_item.group(1).strip() if match_item else ""
    data['품명'] = item_content

    # 4. FOC 여부 판별 로직 (강화됨)
    is_foc = False
    
    # 무상 키워드 리스트 (인식 오차를 대비해 핵심 단어 위주로 구성)
    foc_keywords = ['FREE OF CHARGE', 'F.O.C', 'NO CHARGE', 'FOC', '무상']
    exclude_keywords = ['CANISTER', 'DRUM', 'RE-IMPORT', '재수입']

    if trade_code == "11":
        # 방법 1: 품명 섹션 안에서 찾기
        found_in_item = any(key in item_content.upper() for key in foc_keywords)
        
        # 방법 2: 품명에서 못 찾았다면 문서 전체에서 다시 한 번 확인 (더 확실함)
        found_in_full_text = any(key in upper_text for key in foc_keywords)
        
        if found_in_item or found_in_full_text:
            # 제외 키워드가 포함되어 있는지 확인 (전체 텍스트 기준)
            if not any(ex in upper_text for ex in exclude_keywords):
                is_foc = True
    
    data['FOC여부'] = is_foc
    return data

def main():
    st.title('📦 수출신고필증 FOC(무상) 항목 추출기')
    st.info("거래구분이 '11'이면서 품명에 FOC가 포함된 항목을 추출합니다. (Canister, Drum 제외)")

    with st.sidebar:
        st.header("파일 업로드")
        uploaded_files = st.file_uploader("여러 파일을 선택할 수 있습니다.", 
                                         type=['png', 'jpg', 'jpeg', 'pdf'], 
                                         accept_multiple_files=True)

    if uploaded_files:
        all_results = []
        
        with st.spinner(f"{len(uploaded_files)}개의 파일을 분석 중입니다..."):
            for uploaded_file in uploaded_files:
                text = extract_text_from_file(uploaded_file)
                if text:
                    parsed_result = parse_export_data(text, uploaded_file.name)
                    all_results.append(parsed_result)
        
        # 데이터프레임 생성
        df_all = pd.DataFrame(all_results)
        
        # FOC인 건만 필터링
        df_foc = df_all[df_all['FOC여부'] == True].copy()

        # 화면 결과 출력
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("✅ 추출된 FOC 리스트")
            if not df_foc.empty:
                st.dataframe(df_foc[['파일명', '신고번호', '거래구분', '품명']], use_container_width=True)
                
                # 엑셀 다운로드
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_foc.to_excel(writer, index=False)
                st.download_button(label="FOC 리스트 다운로드 (Excel)", data=output.getvalue(), 
                                   file_name="FOC_Extract_List.xlsx")
            else:
                st.write("조건에 맞는 FOC 항목이 없습니다.")

        with col2:
            st.subheader("📊 전체 분석 통계")
            st.write(f"전체 분석 파일: {len(df_all)}개")
            st.write(f"추출된 FOC 건수: {len(df_foc)}개")
            if st.checkbox("전체 데이터 보기"):
                st.dataframe(df_all)

    else:
        st.info("왼쪽 사이드바에서 분석할 파일들을 업로드해 주세요.")

if __name__ == '__main__':
    main()
