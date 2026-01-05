import streamlit as st
import pytesseract
from PIL import Image
import pandas as pd
import pdfplumber
import io
import re

st.set_page_config(layout="wide", page_title="수출신고필증 란별 FOC 추출기")

def extract_text_from_file(uploaded_file):
    try:
        if uploaded_file.type in ['image/png', 'image/jpeg']:
            image = Image.open(uploaded_file)
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

def parse_lan_segments(text, filename):
    """텍스트를 란 번호별로 쪼개서 리스트로 반환"""
    results = []
    
    # 공통 정보 추출 (신고번호, 거래구분 등은 문서 상단에 한 번만 나옴)
    match_sin_go = re.search(r'(\d{5}-\d{2}-\d{6}[A-Z])', text)
    sin_go_no = match_sin_go.group(1) if match_sin_go else "미확인"
    
    match_trade = re.search(r'거래구분\s*[:：]?\s*(\d{2})', text)
    trade_code = match_trade.group(1) if match_trade else "11"

    # '품명 · 규격' 문구를 기준으로 란별 섹션 분리
    # (란번호/총란수 : 001/005) 패턴을 찾아 섹션을 나눕니다.
    lan_sections = re.split(r'품\s*명\s*·?\s*규\s*격', text, flags=re.I)
    
    for section in lan_sections[1:]: # 첫 번째 섹션은 헤더이므로 제외
        data = {"파일명": filename, "수출신고번호": sin_go_no, "거래구분": trade_code}
        
        # 1. 란 번호 추출 (ex: 001/005 -> 001 추출)
        match_lan = re.search(r'(\d{3})\s*/\s*\d{3}', section)
        lan_no = match_lan.group(1) if match_lan else "미확인"
        data['란번호'] = lan_no

        # 2. 모델·규격 및 FOC 키워드 확인 (해당 란 섹션 내에서만)
        clean_section = " ".join(section.split())
        model_match = re.search(r'(\(NO\.\d+\).*?FREE OF CHARGE.*?\))', clean_section, re.I)
        
        if model_match:
            data['모델ㆍ규격'] = model_match.group(1)
            data['FOC여부'] = True
        else:
            # FOC가 없더라도 란 정보를 유지하고 싶다면 여기서 처리
            foc_check = re.search(r'FREE OF CHARGE', clean_section, re.I)
            data['모델ㆍ규격'] = clean_section[:100] + "..."
            data['FOC여부'] = True if foc_check else False

        # 3. 수량, 중량, 가격 추출 (해당 란 섹션 내에서)
        match_qty = re.search(r'(\d+)\s*(\([A-Z]{2,3}\))', clean_section)
        data['수량(단위)'] = f"{match_qty.group(1)} {match_qty.group(2)}" if match_qty else "미확인"

        match_net = re.search(r'([\d,.]+)\s*\(KG\)', clean_section, re.I)
        data['순중량'] = f"{match_net.group(1)} KG" if match_net else "미확인"

        match_fob = re.search(r'(\$\s?[\d,.]+)', clean_section)
        data['신고가격(FOB)'] = match_fob.group(1) if match_fob else "미확인"

        results.append(data)
        
    return results

def main():
    st.title('📦 수출신고필증 란별 FOC 추출기')
    st.info("각 란번호(001, 002...)별로 FOC 항목을 분리하여 정리합니다.")

    uploaded_files = st.file_uploader("파일 업로드", type=['png', 'jpg', 'jpeg', 'pdf'], accept_multiple_files=True)

    if uploaded_files:
        all_data = []
        for uploaded_file in uploaded_files:
            with st.spinner(f"{uploaded_file.name} 분석 중..."):
                text = extract_text_from_file(uploaded_file)
                if text:
                    lan_results = parse_lan_segments(text, uploaded_file.name)
                    all_data.extend(lan_results)
        
        if all_data:
            df = pd.DataFrame(all_data)
            # FOC인 것만 필터링
            df_foc = df[df['FOC여부'] == True].copy()

            st.subheader("✅ 란별 FOC 추출 리스트")
            cols = ['파일명', '수출신고번호', '란번호', '거래구분', '모델ㆍ규격', '수량(단위)', '순중량', '신고가격(FOB)']
            
            if not df_foc.empty:
                st.dataframe(df_foc[cols], use_container_width=True, hide_index=True)
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_foc[cols].to_excel(writer, index=False)
                st.download_button("Excel 다운로드", output.getvalue(), "FOC_Detailed_List.xlsx")
            else:
                st.warning("FOC 항목을 찾지 못했습니다.")
    else:
        st.info("파일을 업로드해 주세요.")

if __name__ == '__main__':
    main()
