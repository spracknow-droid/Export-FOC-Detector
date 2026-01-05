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
            # --psm 6: 이미지 내 텍스트를 하나의 균일한 블록으로 간주하여 줄바꿈 인식률 향상
            custom_config = r'--oem 3 --psm 6'
            return pytesseract.image_to_string(image, lang='kor+eng', config=custom_config)
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
    
    # OCR 텍스트 전처리: 여러 개의 공백을 하나로 합침
    clean_text = " ".join(text.split())

    # 1. 수출신고번호
    match_sin_go = re.search(r'(\d{5}-\d{2}-\d{6}[A-Z])', clean_text)
    data['수출신고번호'] = match_sin_go.group(1) if match_sin_go else "미확인"
    
    # 2. 거래구분
    match_trade = re.search(r'거래구분\s*[:：]?\s*(\d{2})', clean_text)
    data['거래구분'] = match_trade.group(1) if match_trade else "11"

    # 3. 모델·규격 (헤더 및 노이즈 제거)
    # 이미지 샘플처럼 (NO.01)로 시작하고 FOC 문구로 끝나는 실제 값만 타겟팅
    model_match = re.search(r'(\(NO\.\d+\).*?FREE OF CHARGE.*?\))', clean_text, re.I)
    if model_match:
        data['모델ㆍ규격'] = model_match.group(1)
    else:
        # 패턴이 잡히지 않을 경우 'FREE OF CHARGE' 주변 60자 캡처
        foc_fallback = re.search(r'(.{0,40}FREE OF CHARGE.{0,40})', clean_text, re.I)
        data['모델ㆍ규격'] = foc_fallback.group(1).strip() if foc_fallback else "텍스트 확인 불가"

    # 4. 수량(단위) - ㉜항목
    match_qty = re.search(r'(\d+)\s*(\([A-Z]{2,3}\))', clean_text)
    data['수량(단위)'] = f"{match_qty.group(1)} {match_qty.group(2)}" if match_qty else "미확인"

    # 5. 순중량 - ㊱항목
    match_net = re.search(r'([\d,.]+)\s*\(KG\)', clean_text, re.I)
    data['순중량'] = f"{match_net.group(1)} KG" if match_net else "미확인"

    # 6. 신고가격(FOB) - ㊳항목 ($ 금액 우선 추출)
    fob_match = re.search(r'(\$\s?[\d,.]+)', clean_text)
    data['신고가격(FOB)'] = fob_match.group(1) if fob_match else "미확인"

    # 7. FOC 판별 (대소문자 무시)
    data['FOC여부'] = True if "FREE OF CHARGE" in clean_text.upper() else False
    
    return data

def main():
    st.title('📦 수출신고필증 FOC(무상) 항목 추출기')
    st.info("PSM 6 옵션이 적용되어 표 안의 텍스트 인식률을 개선했습니다.")

    with st.sidebar:
        st.header("파일 업로드")
        uploaded_files = st.file_uploader("이미지 또는 PDF 업로드", 
                                         type=['png', 'jpg', 'jpeg', 'pdf'], 
                                         accept_multiple_files=True)

    if uploaded_files:
        all_results = []
        with st.spinner("텍스트 판독 및 데이터 매칭 중..."):
            for uploaded_file in uploaded_files:
                text = extract_text_from_file(uploaded_file)
                if text:
                    all_results.append(parse_export_data(text, uploaded_file.name))
        
        if all_results:
            df_all = pd.DataFrame(all_results)
            df_foc = df_all[df_all['FOC여부'] == True].copy()

            st.subheader("✅ FOC 추출 리스트")
            if not df_foc.empty:
                cols = ['파일명', '수출신고번호', '거래구분', '모델ㆍ규격', '수량(단위)', '순중량', '신고가격(FOB)']
                st.dataframe(df_foc[cols], use_container_width=True, hide_index=True)
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_foc[cols].to_excel(writer, index=False)
                st.download_button("결과 다운로드 (Excel)", output.getvalue(), "FOC_List.xlsx")
            else:
                st.warning("FOC 건이 발견되지 않았습니다.")

            with st.expander("🔍 전체 분석 텍스트 데이터 확인"):
                st.dataframe(df_all)
    else:
        st.info("왼쪽에서 파일을 선택해 주세요.")

if __name__ == '__main__':
    main()
