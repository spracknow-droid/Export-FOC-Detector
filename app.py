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
    clean_text = " ".join(text.split())
    
    # 1. 수출신고번호 추출
    match_sin_go = re.search(r'(\d{5}-\d{2}-\d{6}[A-Z])', clean_text)
    sin_go_no = match_sin_go.group(1) if match_sin_go else "미확인"

    # 2. 란 번호 기호 기준으로 섹션 분리
    lan_sections = re.split(r'\(란번호/총란수\s*:\s*', text)
    
    results = []
    for section in lan_sections[1:]:
        s_clean = " ".join(section.split())
        data = {"파일명": filename, "수출신고번호": sin_go_no}

        # 란번호 추출
        lan_match = re.search(r'^(\d{3})', s_clean)
        data['란번호'] = lan_match.group(1) if lan_match else "미확인"
        
        # 거래구분 추출 (기본값 11)
        trade_match = re.search(r'거래구분\s*[:：]?\s*(\d{2})', clean_text)
        data['거래구분'] = trade_match.group(1) if trade_match else "11"

        # 3. 모델·규격 및 FOC/제외 키워드 판별
        model_part = re.search(r'(\(NO\.\d+\).*?FREE OF CHARGE.*?\))', s_clean, re.I)
        
        is_foc_text = False
        model_val = "일반 품목"
        
        if model_part:
            model_val = model_part.group(1)
            is_foc_text = True
        elif "FREE OF CHARGE" in s_clean.upper():
            model_val = "FREE OF CHARGE 포함 (패턴 미일치)"
            is_foc_text = True

        # [중요] 제외 조건 체크: CANISTER, CARRY BOX, DRUM
        exclude_keywords = ['CANISTER', 'CARRY BOX', 'DRUM']
        is_excluded = any(ex in s_clean.upper() for ex in exclude_keywords)

        data['모델ㆍ규격'] = model_val
        # FOC 문구가 있고, 제외 키워드가 없어야만 True
        data['FOC여부'] = True if (is_foc_text and not is_excluded) else False

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
                all_rows.extend(parse_lan_segments(text, file.name))
        
        if all_rows:
            df = pd.DataFrame(all_rows)
            df_foc = df[df['FOC여부'] == True].copy()

            st.subheader("✅ 추출된 FOC 리스트 (제외 조건 적용)")
            
            # 요청하신 컬럼 순서 적용: 수출신고번호 바로 다음에 거래구분
            target_cols = ['파일명', '수출신고번호', '거래구분', '란번호', '모델ㆍ규격', '수량(단위)', '순중량', '신고가격(FOB)']
            
            if not df_foc.empty:
                st.dataframe(df_foc[target_cols], use_container_width=True, hide_index=True)
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_foc[target_cols].to_excel(writer, index=False)
                st.download_button("📊 결과 엑셀 다운로드", output.getvalue(), "FOC_Final_List.xlsx")
            else:
                st.warning("FOC 항목이 없거나 모두 제외 대상(Canister 등)입니다.")
                
            with st.expander("🔍 전체 데이터 분석 결과 (제외 항목 포함)"):
                st.dataframe(df)

if __name__ == '__main__':
    main()
