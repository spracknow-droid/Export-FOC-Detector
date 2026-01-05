import streamlit as st
import pdfplumber
import pandas as pd
import io
import re

st.set_page_config(layout="wide", page_title="수출신고필증 FOC 상세 추출기")

def parse_pdf_table(uploaded_file):
    results = []
    current_sin_go_no = "미확인"
    
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            # 1. 신고번호 추출
            text = page.extract_text() or ""
            sin_go_match = re.search(r'(\d{5}-\d{2}-\d{6}[A-Z])', text)
            if sin_go_match:
                current_sin_go_no = sin_go_match.group(1)

            # 2. 표 추출 (표의 선이 겹치거나 끊겨도 최대한 인식하도록 설정)
            table = page.extract_table({
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
                "snap_tolerance": 5, # 선 인식 허용치 상향
                "join_tolerance": 5,
            })

            if not table: continue

            # 3. 유연한 데이터 매칭 로직
            for i, row in enumerate(table):
                # 셀 내부 줄바꿈 처리 및 빈 값 제거
                row = [str(cell).strip() if cell else "" for cell in row]
                row_str = " ".join(row).replace('\n', ' ')

                # (NO.01) 패턴 탐색
                if "(NO." in row_str:
                    try:
                        # 현재 행(row)과 바로 다음 행(row+1)을 병합하여 데이터 누락 방지
                        # 필증 구조상 모델명이나 수량이 다음 줄에 걸쳐 있는 경우가 많음
                        next_row = [str(cell).strip() if cell else "" for cell in table[i+1]] if i+1 < len(table) else [""] * len(row)
                        
                        # 각 항목별 데이터 추출 (내용이 있는 칸을 우선 탐색)
                        full_content = " ".join(row) + " " + " ".join(next_row)
                        full_content = full_content.replace('\n', ' ')

                        # FOC 판별 및 제외 키워드
                        if "FREE OF CHARGE" in full_content.upper() and not any(ex in full_content.upper() for ex in ['CANISTER', 'DRUM']):
                            
                            # 모델명 추출: (NO.01) 뒤의 텍스트
                            model_match = re.search(r'\(NO\.\d+\)\s*(.*)', full_content)
                            model_name = model_match.group(1).split('㉛')[0].strip() if model_match else "확인불가"

                            # 수량 추출: 숫자 + (BO) 또는 (GT) 등 단위 패턴
                            qty_match = re.search(r'(\d+)\s*\((BO|GT|KG|EA)\)', full_content)
                            qty = qty_match.group(0) if qty_match else "확인불가"

                            # 순중량 추출: (36)번 근처 숫자
                            weight_match = re.search(r'([\d,.]+)\s*\(KG\)', full_content)
                            weight = weight_match.group(0) if weight_match else "란 합산치 참조"

                            # 금액(USD) 추출
                            usd_match = re.search(r'(?:USD|\$)\s?([\d,.]+)', full_content)
                            price = f"USD {usd_match.group(1)}" if usd_match else "미확인"

                            results.append({
                                "파일명": uploaded_file.name,
                                "수출신고번호": current_sin_go_no,
                                "거래구분": "11",
                                "란-번호": re.search(r'\(NO\.\d+\)', full_content).group() if "(NO." in full_content else "확인",
                                "모델ㆍ규격": model_name,
                                "수량(단위)": qty,
                                "순중량": weight,
                                "신고가격(FOB)": price,
                            })
                    except Exception:
                        continue

    return results

def main():
    st.title('📦 수출신고필증 FOC 상세 추출기 (보정 버전)')
    st.info("표 구조가 복잡한 필증의 데이터를 줄바꿈과 상관없이 병합하여 추출합니다.")

    with st.sidebar:
        st.header("📂 파일 업로드")
        uploaded_files = st.file_uploader("전자 PDF 파일을 선택하세요", type=['pdf'], accept_multiple_files=True)

    if uploaded_files:
        all_rows = []
        for file in uploaded_files:
            data = parse_pdf_table(file)
            all_rows.extend(data)
        
        if all_rows:
            df = pd.DataFrame(all_rows).drop_duplicates()
            st.subheader("✅ 최종 추출 결과")
            # Streamlit 최신 버전 규격 적용
            st.dataframe(df, width='stretch', hide_index=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button("📊 엑셀 다운로드", output.getvalue(), "FOC_Final_Report.xlsx")
        else:
            st.warning("FOC 항목을 찾지 못했습니다. PDF가 스캔 이미지가 아닌 '전자문서'인지 확인해주세요.")

if __name__ == '__main__':
    main()
