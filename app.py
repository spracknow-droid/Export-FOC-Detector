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
    sin_go_no = re.search(r'(\d{5}-\d{2}-\d{6}[A-Z])', clean_text)
    sin_go_no = sin_go_no.group(1) if sin_go_no else "미확인"

    lan_sections = re.split(r'\(란번호/총란수\s*:\s*', text)
    results = []

    for section in lan_sections[1:]:
        s_clean = " ".join(section.split())
        lan_no = re.search(r'^(\d{3})', s_clean)
        lan_no = lan_no.group(1) if lan_no else "미확인"

        # [핵심] 란 내부의 (NO.01), (NO.02) 단위를 찾아서 쪼갭니다.
        sub_items = re.split(r'(\(NO\.\d+\))', s_clean)
        # sub_items 결과 예: ['', '(NO.01)', 'Waikiki... ', '(NO.02)', 'Waikiki...']
        
        # 우측 칸의 수량값들을 리스트로 추출 (예: [13, 7])
        all_qtys = re.findall(r'(\d+)\s*\(BO\)', s_clean)

        item_idx = 0
        for i in range(1, len(sub_items), 2):
            no_tag = sub_items[i]        # (NO.01)
            content = sub_items[i+1]     # Waikiki... (FREE OF CHARGE...)
            
            # FOC 여부 및 제외 키워드 체크
            is_foc = "FREE OF CHARGE" in content.upper()
            exclude_keywords = ['CANISTER', 'CARRY BOX', 'DRUM']
            is_excluded = any(ex in content.upper() for ex in exclude_keywords)

            if is_foc and not is_excluded:
                data = {
                    "파일명": filename,
                    "수출신고번호": sin_go_no,
                    "거래구분": "11",
                    "란번호": f"{lan_no}-{no_tag.strip('()')}", # 예: 003-NO.01
                    "모델ㆍ규격": f"{no_tag} {content.split('㉛')[0].strip()}",
                    "수량(단위)": f"{all_qtys[item_idx]} (BO)" if item_idx < len(all_qtys) else "확인불가",
                    "순중량": "란 합산치 참조", # 란 전체 중량만 기재되므로 비고처리
                    "신고가격(FOB)": re.search(r'USD[\d,.]+', content).group(0) if "USD" in content else "별도확인"
                }
                results.append(data)
            item_idx += 1
            
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
