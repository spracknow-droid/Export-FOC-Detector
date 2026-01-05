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
    
    # 1. 수출신고번호 (패턴 강화)
    match_sin_go = re.search(r'(\d{5}-\d{2}-\d{6}[A-Z])', text)
    data['수출신고번호'] = match_sin_go.group(1) if match_sin_go else "미확인"
    
    # 2. 거래구분
    match_trade = re.search(r'거래구분\s*[:：]?\s*(\d{2})', text)
    trade_code = match_trade.group(1) if match_trade else "11" # 이미지에 11이 보이면 기본값 11
    data['거래구분'] = trade_code
    
    # 3. 모델·규격 추출 (가장 중요한 수정)
    # '거래품명' 이후부터 '세번부호' 또는 '순중량' 이전까지의 모든 텍스트를 가져옵니다.
    # 기호 ㉚ 대신 텍스트 키워드 기반으로 범위를 넓혔습니다.
    model_area = ""
    model_match = re.search(r'(?:거래품명|모델\s*·?\s*규격)(.*?)(?=세번부호|순중량|㊱|㉜)', text, re.S | re.I)
    if model_match:
        model_area = model_match.group(1).strip()
    else:
        # 만약 위 패턴이 실패하면 'FREE OF CHARGE' 주변 텍스트라도 가져옵니다.
        foc_context = re.search(r'(.{20}FREE OF CHARGE.{20})', text, re.S | re.I)
        model_area = foc_context.group(1).strip() if foc_context else ""
    
    data['모델ㆍ규격'] = model_area.replace('\n', ' ')

    # 4. 수량(단위)
    # 이미지처럼 1 (BO) 형식을 찾음
    match_qty = re.search(r'([\d,.]+)\s*(\([A-Z]{2,3}\))', text)
    data['수량(단위)'] = f"{match_qty.group(1)} {match_qty.group(2)}" if match_qty else "미확인"

    # 5. 순중량
    match_net = re.search(r'([\d,.]+)\s*\(KG\)', text, re.I)
    data['순중량'] = f"{match_net.group(1)} KG" if match_net else "미확인"

    # 6. 신고가격(FOB) (이미지의 $ 표시 대응)
    # $ 뒤에 숫자가 오는 패턴을 먼저 찾습니다.
    match_fob = re.search(r'(\$\s?[\d,.]+)', text)
    if not match_fob:
        match_fob = re.search(r'㊳?\s*신고가격\(FOB\)\s*([\d,.]+)', text)
    data['신고가격(FOB)'] = match_fob.group(1) if match_fob else "미확인"

    # 7. FOC 판별 (전체 텍스트에서 키워드 검색으로 안전하게)
    is_foc = False
    if "FREE OF CHARGE" in text.upper() or "F.O.C" in text.upper():
        if not any(ex in text.upper() for ex in ['CANISTER', 'DRUM']):
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
