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
            # PSM 6: 표 형식의 데이터를 줄 단위로 읽는 데 최적화
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
    results = []
    # 공백 정규화
    clean_full_text = " ".join(text.split())
    
    # 공통 정보: 수출신고번호
    match_sin_go = re.search(r'(\d{5}-\d{2}-\d{6}[A-Z])', clean_full_text)
    sin_go_no = match_sin_go.group(1) if match_sin_go else "미확인"

    # 란별 섹션 나누기: "품명 · 규격" 키워드 기준
    sections = re.split(r'품\s*명\s*[·\.]?\s*규\s*격', text, flags=re.I)
    
    for section in sections[1:]: # 헤더 이후의 각 란별 루프
        data = {"파일명": filename, "수출신고번호": sin_go_no}
        # 섹션 내 공백 정리
        s_clean = " ".join(section.split())

        # 1. 란번호 (001/005 등에서 앞의 3자리)
        lan_match = re.search(r'(\d{3})\s*/\s*\d{3}', s_clean)
        data['란번호'] = lan_match.group(1) if lan_match else "미확인"

        # 2. 거래구분 (기본값 11, 명시되어 있으면 추출)
        trade_match = re.search(r'거래구분\s*[:：]?\s*(\d{2})', s_clean)
        data['거래구분'] = trade_match.group(1) if trade_match else "11"

        # 3. 모델·규격 (핵심 데이터 추출)
        # (NO.01) 시작 ~ FREE OF CHARGE 끝점을 정확히 캡처
        model_match = re.search(r'(\(NO\.\d+\).*?FREE OF CHARGE.*?\))', s_clean, re.I)
        if model_match:
            data['모델ㆍ규격'] = model_match.group(1)
            data['FOC여부'] = True
        else:
            # 보조 판별: 전체 문구 중 FOC가 있으면 일단 가져옴
            is_foc = "FREE OF CHARGE" in s_clean.upper()
            data['모델ㆍ규격'] = s_clean[:150] if is_foc else "FOC 아님"
            data['FOC여부'] = is_foc

        # 4. 수량(단위)
        qty_match = re.search(r'(\d[\d,.]*)\s*(\([A-Z]{2,3}\))', s_clean)
        data['수량(단위)'] = f"{qty_match.group(1)} {qty_match.group(2)}" if qty_match else "미확인"

        # 5. 순중량
        weight_match = re.search(r'([\d,.]+)\s*\(KG\)', s_clean, re.I)
        data['순중량'] = f"{weight_match.group(1)} KG" if weight_match else "미확인"

        # 6. 신고가격(FOB)
        fob_match = re.search(r'(\$\s?[\d,.]+)', s_clean)
        data['신고가격(FOB)'] = fob_match.group(1) if fob_match else "미확인"

        results.append(data)
    return results

def main():
    st.title('📦 수출신고필증 란별 FOC 추출기')

    # --- 사이드바 영역 ---
    with st.sidebar:
        st.header("📂 파일 업로드")
        uploaded_files = st.file_uploader(
            "이미지 또는 PDF 파일을 선택하세요", 
            type=['png', 'jpg', 'jpeg', 'pdf'], 
            accept_multiple_files=True
        )
        st.divider()
        st.info("💡 Tip: 란번호별로(001, 002...) FOC 항목을 자동 분류합니다.")

    # --- 메인 영역 ---
    if uploaded_files:
        all_data = []
        progress_bar = st.progress(0)
        
        for idx, file in enumerate(uploaded_files):
            with st.status(f" 분석 중: {file.name}", expanded=False):
                text = extract_text_from_file(file)
                if text:
                    lan_results = parse_lan_segments(text, file.name)
                    all_data.extend(lan_results)
            progress_bar.progress((idx + 1) / len(uploaded_files))
        
        if all_data:
            df = pd.DataFrame(all_data)
            # FOC여부가 True인 행만 필터링
            df_foc = df[df['FOC여부'] == True].copy()

            st.subheader("✅ 란별 FOC 추출 결과")
            if not df_foc.empty:
                cols = ['파일명', '수출신고번호', '란번호', '거래구분', '모델ㆍ규격', '수량(단위)', '순중량', '신고가격(FOB)']
                st.dataframe(df_foc[cols], use_container_width=True, hide_index=True)
                
                # 엑셀 다운로드 버튼
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_foc[cols].to_excel(writer, index=False)
                
                st.download_button(
                    label="📊 추출 결과 엑셀 다운로드",
                    data=output.getvalue(),
                    file_name="FOC_Detailed_List.xlsx",
                    mime="application/vnd.ms-excel"
                )
            else:
                st.warning("⚠️ FOC(FREE OF CHARGE) 키워드가 포함된 란을 찾지 못했습니다.")
                
            with st.expander("🔍 전체 분석 데이터 확인 (모든 란)"):
                st.dataframe(df)
    else:
        st.info("사이드바에서 분석할 파일을 업로드해 주세요.")

if __name__ == '__main__':
    main()
