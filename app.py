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
    
    # 1. 수출신고번호 (보통 상단에 위치)
    match_sin_go = re.search(r'\b(\d{5}-\d{2}-\d{6}[A-Z])\b', text)
    data['수출신고번호'] = match_sin_go.group(1) if match_sin_go else "미확인"
    
    # 2. 거래구분 (필증 어딘가에 있는 '거래구분 : 11' 형식 추출)
    match_trade = re.search(r'거래구분\s*[:：]?\s*(\d{2})', text)
    trade_code = match_trade.group(1) if match_trade else ""
    data['거래구분'] = trade_code
    
    # 3. 모델·규격 (㉚ 항목)
    # ㉚ 기호부터 다음 주요 항목 번호(㉛, ㉜, ㉝ 등) 전까지 추출
    # 이미지 샘플을 기반으로 (FREE OF CHARGE) 문구를 여기서 찾습니다.
    match_model = re.search(r'㉚?\s*모델\s*·?\s*규격\s*(.*?)(?=㉛|㉜|㉝|세번부호|㊱)', text, re.S)
    model_text = match_model.group(1).strip() if match_model else ""
    data['모델ㆍ규격'] = model_text.replace('\n', ' ')[:150] # 넉넉하게 150자

    # 4. 수량(단위) (㉜ 항목)
    # 숫자가 먼저 나오고 뒤에 (BO), (SET) 등이 붙는 패턴
    match_qty = re.search(r'㉜?\s*수량\(단위\)\s*([\d,.]+)\s*(\([A-Z]+\))', text)
    if not match_qty: # 항목명 없이 숫자와 단위만 있는 경우 대비
        match_qty = re.search(r'([\d,.]+)\s*(\([A-Z]{2,3}\))', text)
    data['수량(단위)'] = f"{match_qty.group(1)} {match_qty.group(2)}" if match_qty else "미확인"

    # 5. 순중량 (㊱ 항목)
    match_net = re.search(r'㊱?\s*순중량\s*([\d,.]+)\s*\(KG\)', text, re.I)
    data['순중량'] = f"{match_net.group(1)} KG" if match_net else "미확인"

    # 6. 신고가격(FOB) (㊳ 항목)
    # 이미지처럼 달러 표시($)나 숫자가 여러 줄로 나올 수 있음
    match_fob = re.search(r'㊳?\s*신고가격\(FOB\)\s*([\$A-Z]*)\s*([\d,.]+)', text, re.I)
    data['신고가격(FOB)'] = f"{match_fob.group(1)} {match_fob.group(2)}" if match_fob else "미확인"

    # 7. FOC 판별 로직
    is_foc = False
    foc_keywords = ['FREE OF CHARGE', 'F.O.C', 'NO CHARGE', 'FOC', '무상']
    exclude_keywords = ['CANISTER', 'DRUM', 'RE-IMPORT']

    # 거래구분이 11이고, 모델·규격 텍스트 내에 FOC 키워드가 있으면 True
    if trade_code == "11" or trade_code == "": # 거래구분 인식 실패 대비해 일단 키워드 위주로
        upper_model = model_text.upper()
        if any(key in upper_model for key in foc_keywords):
            if not any(ex in upper_model for ex in exclude_keywords):
                is_foc = True
                
    data['FOC여부'] = is_foc
    return data

def main():
    st.title('📦 수출신고필증 FOC(무상) 항목 추출기')
    st.markdown("### 샘플 이미지의 ㉚모델·규격 및 ㊳신고가격 정보를 정밀 분석합니다.")

    with st.sidebar:
        st.header("파일 업로드")
        uploaded_files = st.file_uploader("파일을 업로드하세요", type=['png', 'jpg', 'jpeg', 'pdf'], accept_multiple_files=True)

    if uploaded_files:
        all_results = []
        with st.spinner("이미지 텍스트 판독 중..."):
            for uploaded_file in uploaded_files:
                text = extract_text_from_file(uploaded_file)
                if text:
                    all_results.append(parse_export_data(text, uploaded_file.name))
        
        if all_results:
            df_all = pd.DataFrame(all_results)
            df_foc = df_all[df_all['FOC여부'] == True].copy()

            st.subheader("✅ FOC 추출 결과")
            if not df_foc.empty:
                cols = ['파일명', '수출신고번호', '거래구분', '모델ㆍ규격', '수량(단위)', '순중량', '신고가격(FOB)']
                st.dataframe(df_foc[cols], use_container_width=True, hide_index=True)
                
                # 엑셀 다운로드
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_foc[cols].to_excel(writer, index=False)
                st.download_button("엑셀 파일 다운로드", output.getvalue(), "FOC_Analysis.xlsx")
            else:
                st.warning("FOC 건을 찾지 못했습니다. [전체 데이터 보기]를 통해 인식 내용을 확인하세요.")

            with st.expander("🔍 전체 데이터 분석 결과 (인식 오류 확인용)"):
                st.dataframe(df_all)
    else:
        st.info("왼쪽 사이드바에서 분석할 필증 이미지를 업로드해 주세요.")

if __name__ == '__main__':
    main()
