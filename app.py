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
            # 1. 텍스트에서 신고번호 먼저 추출
            text = page.extract_text() or ""
            sin_go_match = re.search(r'(\d{5}-\d{2}-\d{6}[A-Z])', text)
            if sin_go_match:
                current_sin_go_no = sin_go_match.group(1)

            # 2. 표 추출 (선 기반 전략)
            table = page.extract_table({
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
                "snap_tolerance": 3,
            })

            if not table:
                continue

            # 3. 데이터 파싱 (표의 각 행을 순회)
            for i, row in enumerate(table):
                # None 값 제거 및 공백 정리
                row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]
                
                # '모델·규격' 칸이나 '(NO.01)' 같은 패턴이 보이면 데이터 행으로 간주
                row_str = " ".join(row)
                
                if "(NO." in row_str:
                    # 필증 양식에 따른 인덱스 추정 (전자 PDF 표 구조 기준)
                    # [주의] 이 인덱스는 PDF 생성 엔진에 따라 1~2칸씩 차이날 수 있음
                    try:
                        model_info = row[0] # 보통 첫 번째 칸에 (NO.01) 모델명
                        qty_info = row[2]   # 보통 세 번째 칸에 수량
                        price_info = row[4] # 보통 다섯 번째 칸에 금액(USD)
                        
                        # FOC 판별 (FREE OF CHARGE 문구 확인)
                        is_foc = "FREE OF CHARGE" in model_info.upper()
                        # 제외 키워드
                        exclude = any(ex in model_info.upper() for ex in ['CANISTER', 'CARRY BOX', 'DRUM'])

                        if is_foc and not exclude:
                            # 순중량 및 다른 정보 찾기 (현재 행 근처에서 추출)
                            # 아래 로직은 일반적인 필증 구조를 따름
                            results.append({
                                "파일명": uploaded_file.name,
                                "수출신고번호": current_sin_go_no,
                                "거래구분": "11",
                                "란-번호": re.search(r'\(NO\.\d+\)', model_info).group() if "(NO." in model_info else "확인불가",
                                "모델ㆍ규격": model_info.split(')')[-1].strip(),
                                "수량(단위)": qty_info,
                                "순중량": "하단 참조", # 표 구조에 따라 다음 줄에 있을 수 있음
                                "신고가격(FOB)": f"USD {price_info}",
                                "FOC여부": True
                            })
                    except:
                        continue

    return results

def main():
    st.title('📦 수출신고필증 FOC 상세 추출기 (전자 PDF용)')
    st.info("텍스트 선택이 가능한 전자 PDF에 최적화된 버전입니다.")

    with st.sidebar:
        st.header("📂 파일 업로드")
        uploaded_files = st.file_uploader("PDF 파일을 선택하세요", type=['pdf'], accept_multiple_files=True)

    if uploaded_files:
        all_rows = []
        for file in uploaded_files:
            data = parse_pdf_table(file)
            all_rows.extend(data)
        
        if all_rows:
            df = pd.DataFrame(all_rows)
            st.subheader("✅ 추출된 FOC 리스트")
            
            # 불필요한 컬럼 제외하고 보여주기
            display_cols = ['파일명', '수출신고번호', '거래구분', '란-번호', '모델ㆍ규격', '수량(단위)', '신고가격(FOB)']
            st.dataframe(df[display_cols], use_container_width=True, hide_index=True)
            
            # 엑셀 다운로드 기능
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df[display_cols].to_excel(writer, index=False)
            st.download_button("📊 엑셀 다운로드", output.getvalue(), "FOC_Report.xlsx")
        else:
            st.warning("FOC(FREE OF CHARGE) 항목을 찾지 못했습니다. 표 구조를 다시 확인해야 할 수 있습니다.")
    else:
        st.info("왼쪽 사이드바에서 PDF 파일을 업로드해주세요.")

if __name__ == '__main__':
    main()
