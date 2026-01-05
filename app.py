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
            return pytesseract.image_to_string(image, lang='kor+eng', config=r'--oem 3 --psm 6')
        elif uploaded_file.type == 'application/pdf':
            full_text = ""
            with pdfplumber.open(uploaded_file) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text: full_text += text + "\n"
            return full_text
    except Exception as e:
        st.error(f"파일 처리 중 오류: {e}")
        return ""

def parse_lan_segments(text, filename):
    # 1. 문서 전체에서 줄바꿈 제거 (한 줄로 인식률 극대화)
    clean_text = " ".join(text.split())
    
    # 2. 공통 정보 (신고번호) - 문서에 한 번만 나옴
    match_sin_go = re.search(r'(\d{5}-\d{2}-\d{6}[A-Z])', clean_text)
    sin_go_no = match_sin_go.group(1) if match_sin_go else "미확인"

    # 3. [핵심] 란 번호 기호를 기준으로 텍스트를 통째로 쪼갭니다.
    # 예: "(란번호/총란수 : 001/005)" 문구를 기준으로 나눔
    lan_sections = re.split(r'\(란번호/총란수\s*:\s*', text)
    
    results = []
    # 첫 번째 섹션은 공통 헤더이므로 제외하고, 두 번째 섹션부터가 실제 '란' 데이터입니다.
    for section in lan_sections[1:]:
        s_clean = " ".join(section.split())
        data = {"파일명": filename, "수출신고번호": sin_go_no}

        # 란번호 추출 (001, 002 등)
        lan_match = re.search(r'^(\d{3})', s_clean)
        data['란번호'] = lan_match.group(1) if lan_match else "미확인"
        
        # 거래구분 (필증 전체에서 찾거나 섹션 내에서 찾음)
        trade_match = re.search(r'거래구분\s*[:：]?\s*(\d{2})', clean_text)
        data['거래구분'] = trade_match.group(1) if trade_match else "11"

        # 모델·규격 (해당 란 안에서 FREE OF CHARGE 문구 포함된 구역 추출)
        # ㉚ 기호나 NO.01 등을 기준으로 캡처
        model_part = re.search(r'(\(NO\.\d+\).*?FREE OF CHARGE.*?\))', s_clean, re.I)
        if model_part:
            data['모델ㆍ규격'] = model_part.group(1)
            data['FOC여부'] = True
        else:
            # FOC가 없는 란일 경우
            data['모델ㆍ규격'] = "일반 품목"
            data['FOC여부'] = False

        # 수량, 순중량, 신고가격 추출
        qty_match = re.search(r'(\d[\d,.]*)\s*(\([A-Z]{2,3}\))', s_clean)
        data['수량(단위)'] = f"{qty_match.group(1)} {qty_match.group(2)}" if qty_match else "미확인"

        weight_match = re.search(r'([\d,.]+)\s*\(KG\)', s_clean, re.I)
        data['순중량'] = f"{weight_match.group(1)} KG" if weight_match else "미확인"

        fob_match = re.search(r'(\$\s?[\d,.]+)', s_clean)
        data['신고가격(FOB)'] = fob_match.group(0) if fob_match else "미확인"

        results.append(data)
        
    return results

def main():
    st.title('📦 수출신고필증 란별 FOC 추출기')

    with st.sidebar:
        st.header("📂 파일 업로드")
        uploaded_files = st.file_uploader("파일 선택", type=['png', 'jpg', 'jpeg', 'pdf'], accept_multiple_files=True)

    if uploaded_files:
        all_rows = []
        for file in uploaded_files:
            text = extract_text_from_file(file)
            if text:
                # 파일 하나당 여러 개의 란(rows)이 나옵니다.
                lan_rows = parse_lan_segments(text, file.name)
                all_rows.extend(lan_rows)
        
        if all_rows:
            df = pd.DataFrame(all_rows)
            # FOC 항목만 필터링해서 보여줌
            df_foc = df[df['FOC여부'] == True].copy()

            st.subheader("✅ 추출된 FOC 리스트 (란별 분리 완료)")
            cols = ['파일명', '수출신고번호', '란번호', '거래구분', '모델ㆍ규격', '수량(단위)', '순중량', '신고가격(FOB)']
            
            if not df_foc.empty:
                st.dataframe(df_foc[cols], use_container_width=True, hide_index=True)
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_foc[cols].to_excel(writer, index=False)
                st.download_button("Excel 다운로드", output.getvalue(), "FOC_Detailed.xlsx")
            else:
                st.warning("FOC 항목이 없습니다.")
                
            with st.expander("🔍 전체 란 데이터 보기"):
                st.dataframe(df)

if __name__ == '__main__':
    main()
