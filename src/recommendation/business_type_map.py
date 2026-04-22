"""
사업 유형(예: 문구점, 카페) → 공공조달 품목군 매핑

이 매핑의 의미:
  사업 유형이 "공공기관 납품(B2G)"과 관련 있으면 조달 데이터에서 수요 신호를 찾을 수 있습니다.
  소비자 대상(B2C) 위주의 업종은 조달 데이터에서 신호가 약하고, 상권 데이터가 더 적합합니다.
"""

# 사업 유형 키워드 → 매핑 품목군 + 업종 성격
BUSINESS_TYPE_MAP: dict[str, dict] = {
    # B2G 친화 업종 (공공조달 데이터에서 신호 잘 나옴)
    "IT": {"categories": ["IT/소프트웨어"], "type": "B2G", "note": "공공기관 시스템 구축, 유지보수 수요"},
    "소프트웨어": {"categories": ["IT/소프트웨어"], "type": "B2G", "note": "공공기관 시스템 구축, 유지보수 수요"},
    "시스템": {"categories": ["IT/소프트웨어"], "type": "B2G", "note": "공공기관 IT 시스템 수요"},
    "청소": {"categories": ["위생/방역"], "type": "B2G", "note": "공공시설 청소·방역 용역 수요"},
    "방역": {"categories": ["위생/방역"], "type": "B2G", "note": "공공시설 방역 수요"},
    "소독": {"categories": ["위생/방역"], "type": "B2G", "note": "공공시설 소독·방제 수요"},
    "건설": {"categories": ["시설관리/공사", "건설/감리"], "type": "B2G", "note": "공공시설 공사·보수 수요"},
    "전기": {"categories": ["시설관리/공사"], "type": "B2G", "note": "공공시설 전기·설비 수요"},
    "소방": {"categories": ["시설관리/공사"], "type": "B2G", "note": "공공시설 소방 설비 수요"},
    "감리": {"categories": ["건설/감리"], "type": "B2G", "note": "건설사업관리·정밀점검 수요"},
    "도서": {"categories": ["도서/콘텐츠"], "type": "B2G", "note": "공공도서관, 학교, 구청 도서 구매 수요"},
    "출판": {"categories": ["도서/콘텐츠"], "type": "B2G", "note": "공공기관 소식지·콘텐츠 제작 수요"},
    "콘텐츠": {"categories": ["도서/콘텐츠", "행사/홍보"], "type": "B2G", "note": "구청 홍보·영상 제작 수요"},
    "홍보": {"categories": ["행사/홍보"], "type": "B2G", "note": "공공기관 홍보·인쇄물 수요"},
    "교육": {"categories": ["교육/교구"], "type": "B2G", "note": "학교·공공기관 교육 프로그램 수요"},
    "학원": {"categories": ["교육/교구"], "type": "B2G+B2C", "note": "공공기관 교육 용역 + 일반 수강생 수요"},
    "교구": {"categories": ["교육/교구"], "type": "B2G", "note": "학교·어린이집 교구 납품 수요"},
    "급식": {"categories": ["급식/식품"], "type": "B2G", "note": "학교·공공기관 급식 납품 수요"},
    "식자재": {"categories": ["급식/식품"], "type": "B2G", "note": "공공기관 식자재 납품 수요"},
    "차량": {"categories": ["차량/운송"], "type": "B2G", "note": "공공기관 차량 임차·운송 수요"},
    "운송": {"categories": ["차량/운송"], "type": "B2G", "note": "공공기관 운송·운반 수요"},
    "의료": {"categories": ["의료/복지"], "type": "B2G", "note": "공공의료기관 의료기기·소모품 수요"},
    "복지": {"categories": ["의료/복지"], "type": "B2G", "note": "공공복지시설 서비스 수요"},
    "컨설팅": {"categories": ["창업/경영지원"], "type": "B2G", "note": "소상공인·창업 지원사업 관련 수요"},
    "환경": {"categories": ["환경개선/생활민원"], "type": "B2G", "note": "자치구 생활환경 개선 수요"},
    "폐기물": {"categories": ["환경개선/생활민원"], "type": "B2G", "note": "자치구 폐기물 처리 수요"},
    "재개발": {"categories": ["도시정비/재개발"], "type": "B2G", "note": "정비사업 전문관리 수요"},
    "인테리어": {"categories": ["가구/인테리어", "시설관리/공사"], "type": "B2G+B2C", "note": "공공시설 인테리어 + 일반 소비자 수요"},
    "가구": {"categories": ["가구/인테리어"], "type": "B2G", "note": "공공기관 비품·집기 납품 수요"},

    # B2C 위주 업종 (공공조달 신호 약함)
    "문구점": {"categories": ["사무용품/문구"], "type": "B2C", "note": "주로 일반 소비자 대상. 공공조달보다 상권 데이터가 더 적합"},
    "카페": {"categories": [], "type": "B2C", "note": "소비자 대상 업종. 유동인구·상권 데이터가 필요"},
    "커피": {"categories": [], "type": "B2C", "note": "소비자 대상 업종. 유동인구·상권 데이터가 필요"},
    "식당": {"categories": ["급식/식품"], "type": "B2C+B2G", "note": "일반 식당은 B2C, 단체급식 납품은 B2G 가능"},
    "음식점": {"categories": ["급식/식품"], "type": "B2C+B2G", "note": "일반 식당은 B2C, 단체급식 납품은 B2G 가능"},
    "미용": {"categories": [], "type": "B2C", "note": "소비자 대상 업종. 공공조달 수요 없음"},
    "헬스장": {"categories": ["시설위탁/운영"], "type": "B2C+B2G", "note": "공공체육시설 위탁운영 가능 (B2G), 일반 회원은 B2C"},
    "편의점": {"categories": [], "type": "B2C", "note": "소비자 대상 업종. 공공조달 수요 없음"},
    "옷가게": {"categories": [], "type": "B2C", "note": "소비자 대상 업종. 공공조달 수요 없음"},
    "약국": {"categories": ["의료/복지"], "type": "B2C+B2G", "note": "일반 약국은 B2C, 공공의료기관 납품은 B2G 가능"},
    "부동산": {"categories": [], "type": "B2C", "note": "소비자 대상 서비스. 공공조달 수요 없음"},
}


def search_business_type(query: str) -> dict | None:
    """
    사용자가 입력한 사업 유형을 조달 품목군으로 매핑합니다.
    가장 일치하는 항목을 반환하고, 없으면 None을 반환합니다.
    """
    query = query.strip().lower()

    # 완전 일치 우선
    for key, value in BUSINESS_TYPE_MAP.items():
        if key.lower() == query:
            return {"matched_key": key, **value}

    # 부분 일치
    for key, value in BUSINESS_TYPE_MAP.items():
        if key.lower() in query or query in key.lower():
            return {"matched_key": key, **value}

    return None


def suggest_similar(query: str) -> list[str]:
    """입력과 비슷한 사업 유형 키워드를 제안합니다."""
    query = query.strip().lower()
    suggestions = []
    for key in BUSINESS_TYPE_MAP:
        if any(ch in key for ch in query) or any(ch in query for ch in key):
            suggestions.append(key)
    return suggestions[:5]
