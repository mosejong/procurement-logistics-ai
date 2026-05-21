"""
카테고리명 통합 매핑

clean_bid_data.py (matrix_all) taxonomy → classify_agency.py (display) taxonomy
두 분류 체계가 다르게 발전해서 생긴 불일치를 이 파일 하나로 관리합니다.

사용:
  - build_map_summary.py: MATRIX_TO_DISPLAY로 map_summary 저장 전 rename + re-aggregate
  - streamlit_review.py 드릴다운: DISPLAY_TO_MATRIX로 matrix_all 역방향 필터링
"""

# matrix_all (clean_bid_data.py) 이름 → UI 표시명 (classify_agency.py)
MATRIX_TO_DISPLAY: dict[str, str] = {
    "IT/소프트웨어":        "IT장비/전산",
    "가구/인테리어":        "사무용품/소모품",
    "건설/감리":            "건설/공사",
    "교육/교구":            "교육물품/교구",
    "금융/보험":            "보험/금융",
    "급식/식품":            "급식/식자재",
    "기타":                 "기타/미분류",
    "도서/콘텐츠":          "교육물품/교구",
    "도시정비/재개발":      "건설/공사",
    "사무용품/문구":        "사무용품/소모품",
    "시설관리/공사":        "시설유지보수",
    "시설위탁/운영":        "행사/운영용역",
    "위생/방역":            "방역/소독",
    "의료/복지":            "의료/복지용품",
    "차량/운송":            "차량/운송",
    "창업/경영지원":        "전문용역/컨설팅",
    "행사/홍보":            "행사/운영용역",
    "환경개선/생활민원":    "청소/환경미화",
    "회계/전문용역":        "전문용역/컨설팅",
}

# UI 표시명 → matrix_all 카테고리 목록 (드릴다운 역방향 필터용, 자동 생성)
DISPLAY_TO_MATRIX: dict[str, list[str]] = {}
for _mat, _disp in MATRIX_TO_DISPLAY.items():
    DISPLAY_TO_MATRIX.setdefault(_disp, []).append(_mat)
