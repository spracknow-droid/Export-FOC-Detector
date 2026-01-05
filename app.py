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
    upper_text = text.upper()
    
    # 1. 수출신고번호
    match_sin_go = re.search(r'\b(\d{5}-\d{2}-\d{6}[A-Z])\b', text)
    data['수출신고번호'] = match_sin_go.group(1) if match_sin_go else "미확인"
    
    # 2. 거래구분
    match_trade = re.search(r'거래구분\s*[:：]?\s*(\d{2})', text)
    trade_code = match_trade.group(1) if match_trade else ""
    data['거래구분'] = trade_code
    
    # 3. 모델·규격 구역 추출 (FOC 여부 판단의 핵심)
    # 품명/모델규격부터 결제금액/세액 전까지를 긁어옵니다.
    search_area_match = re.search(r'(?:품\s*명|모델\s*규격|거래품명).*?(?=결제금액|세액|란분할)', text, re.S | re.I)
    search_area = search_area_match.group(0) if search_area_match else ""
    data['모델ㆍ규격'] = search_area.replace('\n', ' ').strip()[:100] # 가독성을 위해 100자 제한

    # 4. 수량(단위) 추출
    # 숫자 뒤에 (SET), (PCE), (KG) 등이 오는 패턴
    match_qty = re.search(r'(\d[\d,.]*)\s*(\([A-Z]{2,3}\))', text)
    data['수량(단위)'] = f"{match_qty.group(1)} {match_qty.group(2)}" if match_qty else "미확인"

    # 5. 순중량 추출
    match_net_weight = re.search(r'순중량\s*[:：]?\s*([\d,.]+\s*KG)', text, re.I)
    data['순중량'] = match_net_weight.group(1).strip() if match_net_weight else "미확인"

    # 6. 신고가격(FOB) 추출
    # '결제금액' 항목 주변에서 'USD' 또는 'KRW'와 함께 나오는 숫자 추출
    match_fob = re.search(r'(?:결제금액|신고가격|FOB).*?([A-Z]{3})\s*([\d,.]+\.\d{2})', text, re.I)
    data['신고가격(FOB)'] = f"{match_fob.group(1)} {match_fob.group(2)}" if match_fob else "미확인"

    # 7. FOC 판별 로직
    is_foc = False
    foc_keywords = ['FREE OF CHARGE', 'F.O.C', 'NO CHARGE', 'FOC', '무상']
    exclude_keywords = ['CANISTER', 'DRUM', 'RE-IMPORT']

    if trade_code == "11":
        area_upper = search_area.upper()
        if any(key in area_upper for key in foc_keywords):
            if not any(ex in area_upper for ex in exclude_keywords):
                is_foc = True
                
    data['FOC여부'] = is_foc
    return data

def main():
    st.title('📦 수출신고필증 FOC(무상) 항목 추출기')
    st.info("거래구분 '11' 중 모델/규격에 FOC가 포함된 건을 추출합니다. (Canister/Drum 제외)")

    with st.sidebar:
        st.header("파일 업로드")
        uploaded_files = st.file_uploader("수출신고필증 업로드 (다중 선택 가능)", 
                                         type=['png', 'jpg', 'jpeg', 'pdf'], 
                                         accept_multiple_files=True)

    if uploaded_files:
        all_results = []
        with st.spinner("데이터 분석 중..."):
            for uploaded_file in uploaded_files:
                text = extract_text_from_file(uploaded_file)
                if text:
                    all_results.append(parse_export_data(text, uploaded_file.name))
        
        if all_results:
            df_all = pd.DataFrame(all_results)
            df_foc = df_all[df_all['FOC여부'] == True].copy()

            col1, col2 = st.columns([3, 1])
            with col1:
                st.subheader("✅ 추출된 FOC 리스트")
                if not df_foc.empty:
                    # 요청하신 순서대로 컬럼 정렬하여 표시
                    target_columns = ['파일명', '수출신고번호', '거래구분', '모델ㆍ규격', '수량(단위)', '순중량', '신고가격(FOB)']
                    st.dataframe(df_foc[target_columns], use_container_width=True, hide_index=True)
                    
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df_foc[target_columns].to_excel(writer, index=False)
                    st.download_button(label="엑셀 다운로드", data=output.getvalue(), 
                                       file_name="FOC_List.xlsx", mime="application/vnd.ms-excel")
                else:
                    st.warning("조건에 부합하는 FOC 항목이 없습니다.")

            with col2:
                st.subheader("📊 통계")
                st.metric("총 분석 파일", len(df_all))
                st.metric("검출된 FOC", len(df_foc))
    else:
        st.info("파일을 업로드하면 분석이 시작됩니다.")

if __name__ == '__main__':
    main()
