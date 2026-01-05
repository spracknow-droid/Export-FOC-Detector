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
    # 신고번호 추출
    match_sin_go = re.search(r'(\d{5}-\d{2}-\d{6}[A-Z])', clean_text)
    sin_go_no = match_sin_go.group(1) if match_sin_go else "미확인"
    
    # 란별 섹션 분리
    lan_sections = re.split(r'\(란번호/총란수\s*:\s*', text)
    results = []

    for section in lan_sections[1:]:
        s_clean = " ".join(section.split())
        lan_no_match = re.search(r'^(\d{3})', s_clean)
        lan_no = lan_no_match.group(1) if lan_no_match else "미확인"
        
        # 란 전체 순중량 추출 (예: 96.0 (KG))
        weight_match = re.search(r'([\d,.]+)\s*\(KG\)', s_clean, re.I)
        total_weight = f"{weight_match.group(1)} KG" if weight_match else "미확인"
        
        # 세부 번호(NO.01, NO.02...) 단위로 쪼개기
        sub_items = re.split(r'(\(NO\.\d+\))', s_clean)
        
        # 해당 란의 모든 수량값 추출 (순서대로 매칭 위함)
        all_qtys = re.findall(r'(\d+)\s*\(BO\)', s_clean)
        
        item_idx = 0
        for i in range(1, len(sub_items), 2):
            no_tag = sub_items[i]        # (NO.01)
            content = sub_items[i+1]     # 모델 내용
            
            # FOC 및 제외 키워드 판별
            is_foc_text = "FREE OF CHARGE" in content.upper()
            exclude_keywords = ['CANISTER', 'CARRY BOX', 'DRUM']
            is_excluded = any(ex in content.upper() for ex in exclude_keywords)

            # 모델명 정제 (표 제목 숫자들 제거)
            model_name = no_tag + " " + content.split('㉛')[0].strip()
            model_name = re.sub(r'\d+\s+\(BO\).*$', '', model_name) # 뒤에 붙은 숫자 노이즈 제거

            row_data = {
                "파일명": filename,
                "수출신고번호": sin_go_no,
                "거래구분": "11",
                "란번호": f"{lan_no}-{no_tag.strip('()')}",
                "모델ㆍ규격": model_name,
                "수량(단위)": f"{all_qtys[item_idx]} (BO)" if item_idx < len(all_qtys) else "확인불가",
                "순중량": f"란 합산치({total_weight}) 참조", # 사용자 요청 반영
                "신고가격(FOB)": "미확인",
                "FOC여부": False
            }

            # FOC 금액 추출 (USD 113,904 등)
            fob_val = re.search(r'USD\s?([\d,.]+)', content, re.I)
            if fob_val:
                row_data["신고가격(FOB)"] = f"USD {fob_val.group(1)}"
            else:
                # 모델 내용에 없을 경우 ㊳번 항목 근처에서 재검색
                fob_alt = re.search(r'㊳?\s*\$\s?([\d,.]+)', s_clean)
                if fob_alt: row_data["신고가격(FOB)"] = f"USD {fob_alt.group(1)}"

            if is_foc_text and not is_excluded:
                row_data["FOC여부"] = True
            
            results.append(row_data)
            item_idx += 1
            
    return results

def main():
    st.title('📦 수출신고필증 FOC 상세 추출기')

    with st.sidebar:
        st.header("📂 파일 업로드")
        uploaded_files = st.file_uploader("파일을 선택하세요", type=['png', 'jpg', 'jpeg', 'pdf'], accept_multiple_files=True)
        st.info("💡 CANISTER, DRUM 등 용기류는 FOC 목록에서 자동 제외됩니다.")

    if uploaded_files:
        all_rows = []
        for file in uploaded_files:
            text = extract_text_from_file(file)
            if text:
                all_rows.extend(parse_lan_segments(text, file.name))
        
        if all_rows:
            df = pd.DataFrame(all_rows)
            
            if 'FOC여부' in df.columns:
                df_foc = df[df['FOC여부'] == True].copy()
                st.subheader("✅ 최종 FOC 리스트")
                
                target_cols = ['파일명', '수출신고번호', '거래구분', '란번호', '모델ㆍ규격', '수량(단위)', '순중량', '신고가격(FOB)']
                
                if not df_foc.empty:
                    st.dataframe(df_foc[target_cols], use_container_width=True, hide_index=True)
                    
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df_foc[target_cols].to_excel(writer, index=False)
                    st.download_button("📊 엑셀 다운로드", output.getvalue(), "FOC_Final_Report.xlsx")
                else:
                    st.warning("추출된 FOC 항목이 없습니다.")
            
            with st.expander("🔍 전체 데이터 분석 결과 (참고용)"):
                st.dataframe(df)
    else:
        st.info("사이드바에서 파일을 업로드해 주세요.")

if __name__ == '__main__':
    main()
