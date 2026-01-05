import streamlit as st
import pytesseract
from PIL import Image
import pandas as pd
import pdfplumber
import io
import re

st.set_page_config(layout="wide", page_title="수출신고필증 FOC 추출기")

def extract_text_from_file(uploaded_file):
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
    data = {"파일명": filename}
    
    # 1. 신고번호 추출
    match_sin_go = re.search(r'\b(\d{5}-\d{2}-\d{6}[A-Z])\b', text)
    data['신고번호'] = match_sin_go.group(1) if match_sin_go else "미확인"
    
    # 2. 거래구분 추출
    match_trade = re.search(r'거래구분\s*[:：]?\s*(\d{2})', text)
    trade_code = match_trade.group(1) if match_trade else ""
    data['거래구분'] = trade_code
    
    # 3. 분석 구역 설정 (품명/모델/규격 주변)
    # 결제금액이나 세액 정보가 나오기 전까지를 '품명/규격' 구역으로 간주
    search_area_match = re.search(r'(?:품\s*명|모델\s*규격|거래품명).*?(?=결제금액|세액|란분할)', text, re.S | re.I)
    search_area = search_area_match.group(0) if search_area_match else text
    
    # 에러 방지용: '품명' 컬럼을 반드시 생성
    data['품명'] = search_area[:100].replace('\n', ' ').strip() # 앞부분 100자만 저장
    
    # 4. FOC 여부 판별
    is_foc = False
    foc_keywords = ['FREE OF CHARGE', 'F.O.C', 'NO CHARGE', 'FOC', '무상']
    exclude_keywords = ['CANISTER', 'DRUM', 'RE-IMPORT', '재수입']

    if trade_code == "11":
        # 대문자로 변환하여 비교 (인인식률 향상)
        area_upper = search_area.upper()
        if any(key in area_upper for key in foc_keywords):
            if not any(ex in area_upper for ex in exclude_keywords):
                is_foc = True
                
    data['FOC여부'] = is_foc
    return data

def main():
    st.title('📦 수출신고필증 FOC(무상) 항목 추출기')
    st.info("거래구분이 '11'이면서 모델/규격 란에 FOC가 포함된 항목을 추출합니다.")

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
        
        if all_results:
            df_all = pd.DataFrame(all_results)
            
            # FOC 데이터 필터링
            df_foc = df_all[df_all['FOC여부'] == True].copy()

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("✅ 추출된 FOC 리스트")
                if not df_foc.empty:
                    # [주의] parse_export_data에서 정의한 키값과 정확히 일치해야 함
                    st.dataframe(df_foc[['파일명', '신고번호', '거래구분', '품명']], use_container_width=True)
                    
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df_foc.to_excel(writer, index=False)
                    st.download_button(label="FOC 리스트 다운로드 (Excel)", data=output.getvalue(), 
                                       file_name="FOC_Extract_List.xlsx")
                else:
                    st.write("조건에 맞는 FOC 항목이 없습니다.")

            with col2:
                st.subheader("📊 전체 분석 결과")
                st.write(f"분석된 파일 수: {len(df_all)}")
                st.dataframe(df_all) # 전체 데이터 확인용
    else:
        st.info("왼쪽 사이드바에서 파일을 업로드해 주세요.")

if __name__ == '__main__':
    main()
