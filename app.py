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
    match_sin_go = re.search(r'(\d{5}-\d{2}-\d{6}[A-Z])', clean_text)
    sin_go_no = match_sin_go.group(1) if match_sin_go else "미확인"
    
    # 란별 섹션 분리
    lan_sections = re.split(r'\(란번호/총란수\s*:\s*', text)
    results = []

    for section in lan_sections[1:]:
        s_clean = " ".join(section.split())
        lan_no_match = re.search(r'^(\d{3})', s_clean)
        lan_no = lan_no_match.group(1) if lan_no_match else "미확인"
        
        # 003란 대응: (NO.01), (NO.02) 단위로 쪼개기
        # 이 정규식은 (NO.01) 같은 태그를 기준으로 섹션을 나눕니다.
        sub_items = re.split(r'(\(NO\.\d+\))', s_clean)
        
        # 해당 란 우측의 수량(단위) 칸 숫자들 추출 (예: 13, 7)
        all_qtys = re.findall(r'(\d+)\s*\(BO\)', s_clean)
        
        item_idx = 0
        # split 결과에서 (NO.XX)는 홀수 인덱스에, 내용은 짝수 인덱스에 들어감
        for i in range(1, len(sub_items), 2):
            no_tag = sub_items[i]        # (NO.01)
            content = sub_items[i+1]     # 모델 내용 및 FOC 문구
            
            # 1) FOC 여부 확인
            is_foc_text = "FREE OF CHARGE" in content.upper()
            
            # 2) 제외 키워드 확인 (CANISTER, CARRY BOX, DRUM)
            exclude_keywords = ['CANISTER', 'CARRY BOX', 'DRUM']
            is_excluded = any(ex in content.upper() for ex in exclude_keywords)

            # 데이터 생성 (KeyError 방지를 위해 모든 행에 'FOC여부' 컬럼을 반드시 생성)
            row_data = {
                "파일명": filename,
                "수출신고번호": sin_go_no,
                "거래구분": "11",
                "란번호": f"{lan_no}-{no_tag.strip('()')}",
                "모델ㆍ규격": f"{no_tag} {content.split('㉛')[0].strip()}",
                "수량(단위)": f"{all_qtys[item_idx]} (BO)" if item_idx < len(all_qtys) else "미확인",
                "순중량": "란 합산치 참조",
                "신고가격(FOB)": "미확인",
                "FOC여부": False # 기본값
            }

            # FOC 금액 추출 (FREE OF CHARGE 옆의 USD 금액)
            fob_val = re.search(r'USD\s?([\d,.]+)', content, re.I)
            if fob_val:
                row_data["신고가격(FOB)"] = f"USD {fob_val.group(1)}"

            # 최종 FOC 판정
            if is_foc_text and not is_excluded:
                row_data["FOC여부"] = True
            
            results.append(row_data)
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
            
            # [KeyError 방지] 데이터가 비어있지 않은지 확인 후 필터링
            if 'FOC여부' in df.columns:
                df_foc = df[df['FOC여부'] == True].copy()
                
                st.subheader("✅ 추출된 FOC 리스트 (003란 세부분할 적용)")
                target_cols = ['파일명', '수출신고번호', '거래구분', '란번호', '모델ㆍ규격', '수량(단위)', '순중량', '신고가격(FOB)']
                
                if not df_foc.empty:
                    st.dataframe(df_foc[target_cols], use_container_width=True, hide_index=True)
                    
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df_foc[target_cols].to_excel(writer, index=False)
                    st.download_button("📊 결과 엑셀 다운로드", output.getvalue(), "FOC_Final.xlsx")
                else:
                    st.warning("FOC 항목이 없거나 제외 조건에 해당합니다.")
            
            with st.expander("🔍 전체 데이터 분석 결과 보기"):
                st.dataframe(df)
    else:
        st.info("사이드바에서 파일을 업로드해 주세요.")

if __name__ == '__main__':
    main()
