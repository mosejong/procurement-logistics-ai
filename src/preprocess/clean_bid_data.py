import pandas as pd

# 서울 자치구 이름을 원천 공고 텍스트에서 찾기 위한 목록입니다.
SEOUL_DISTRICTS = [
    "강남구", "강동구", "강북구", "강서구", "관악구", "광진구", "구로구", "금천구",
    "노원구", "도봉구", "동대문구", "동작구", "마포구", "서대문구", "서초구",
    "성동구", "성북구", "송파구", "양천구", "영등포구", "용산구", "은평구",
    "종로구", "중구", "중랑구",
]

# 서울 외 지역까지 기본 지역명으로 추출할 때 쓰는 목록입니다.
REGION_KEYWORDS = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충청북도", "충남", "충청남도", "전북", "전라북도",
    "전남", "전라남도", "경북", "경상북도", "경남", "경상남도", "제주",
]

# API마다 컬럼명이 조금씩 달라질 수 있어서, 표준 컬럼으로 바꿀 후보명을 모아둡니다.
STANDARD_COLUMN_CANDIDATES = {
    "bid_title": ["bidNtceNm", "bidNm", "ntceNm", "공고명", "입찰공고명"],
    "agency_name": ["dminsttNm", "ntceInsttNm", "orderInsttNm", "수요기관", "기관명"],
    "region": ["prtcptPsblRgnNm", "jntcontrctDutyRgnNm1", "rgnLmtBidLocplcJdgmBssNm", "region"],
    "posted_date": ["bidNtceDt", "bidNtceBgn", "ntceDt", "공고일시", "공고일"],
    "estimated_amount": ["asignBdgtAmt", "presmptPrce", "bdgtAmt", "추정가격", "배정예산"],
}

# 공고명에 들어간 키워드로 품목군을 거칠게 분류합니다.
# 지금은 MVP용 키워드 사전이라, 결과를 보면서 계속 수정하면 됩니다.
ITEM_CATEGORY_KEYWORDS = {
    "창업/경영지원": ["소상공인", "창업", "경영환경", "컨설팅", "판로", "마케팅", "지원사업"],
    "도서/콘텐츠": ["도서", "전자책", "소식지", "유튜브", "채널", "콘텐츠", "영상", "제작"],
    "금융/보험": ["보험", "신용카드", "결제", "납부", "정산"],
    "환경개선/생활민원": ["환경개선", "흡연", "종량제", "생활폐기물", "폐기물"],
    "IT/소프트웨어": [
        "시스템", "서버", "소프트웨어", "SW", "전산", "정보화", "네트워크", "보안",
        "홈페이지", "플랫폼", "데이터", "유지관리", "장비", "컴퓨터", "노트북",
    ],
    "사무용품/문구": ["사무용품", "문구", "복사용지", "토너", "프린터", "복합기", "소모품"],
    "위생/방역": ["방역", "소독", "마스크", "위생", "청소", "세척", "방제"],
    "시설관리/공사": [
        "시설", "공사", "보수", "전기", "기계", "설비", "소방", "승강기", "냉난방",
        "조성", "건립", "신설", "리모델링", "증축", "개축", "철거", "내진",
    ],
    "가구/인테리어": ["가구", "책상", "의자", "인테리어", "칸막이", "집기", "비품"],
    "교육/교구": ["교육", "교구", "교재", "학습", "강의", "훈련", "실습", "학교"],
    "행사/홍보": ["행사", "축제", "홍보", "디자인", "전시", "공연", "인쇄"],
    "의료/복지": ["의료", "병원", "의약", "복지", "검사", "진료", "보건", "산소"],
    "급식/식품": ["급식", "식품", "식자재", "도시락", "음식", "농산물", "축산물"],
    "차량/운송": ["차량", "자동차", "버스", "운송", "운반", "렌트", "임차"],
    "건설/감리": [
        "건설사업관리", "감리", "건설재해예방", "기술지도", "정밀안전점검",
        "안전점검", "안전진단", "재건축진단", "전문감리", "하수도", "빗물펌프장",
        "도로하부", "공동조사", "지하차도", "터널", "교량", "토목",
    ],
    "도시정비/재개발": [
        "재개발", "재건축", "정비사업", "정비구역", "재정비촉진", "추진위원회",
        "주택정비", "정비계획", "뉴타운", "도시재생", "도시재개발",
    ],
    "회계/전문용역": [
        "회계감사", "회계법인", "감사용역", "세무", "법무", "정비사업전문관리",
        "건설사업지원", "공공지원", "관리처분",
    ],
    "시설위탁/운영": [
        "위탁운영", "운영대행", "민간위탁", "수탁", "관리위탁",
        "운영용역", "관리운영", "인공암벽", "체육시설",
    ],
}


def _first_existing_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """후보 컬럼 중 실제 DataFrame에 존재하는 첫 번째 컬럼명을 찾습니다."""
    for column in candidates:
        if column in df.columns:
            return column
    return None


def _row_text(row: pd.Series) -> str:
    """한 행의 모든 값을 합쳐서 지역명/품목 키워드 검색용 텍스트로 만듭니다."""
    return " ".join(str(value) for value in row.dropna().tolist())


def _extract_region(row: pd.Series) -> str:
    """행 전체 텍스트에서 시도 단위 지역명을 찾습니다."""
    text = _row_text(row)
    for region in REGION_KEYWORDS:
        if region in text:
            return region
    return "미상"


def _extract_district(row: pd.Series) -> str:
    """행 전체 텍스트에서 서울 자치구명을 찾습니다."""
    text = _row_text(row)
    for district in SEOUL_DISTRICTS:
        if district in text:
            return district
    return "미상"


def _to_amount(series: pd.Series) -> pd.Series:
    """문자열 금액에서 콤마/원 문자를 제거하고 숫자로 바꿉니다."""
    cleaned = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("원", "", regex=False)
        .str.strip()
    )
    return pd.to_numeric(cleaned, errors="coerce").fillna(0)


def _classify_item_category(text: str) -> str:
    """공고명/기관명/품목 텍스트를 보고 품목군을 하나 선택합니다."""
    normalized = str(text)
    for category, keywords in ITEM_CATEGORY_KEYWORDS.items():
        if any(keyword.lower() in normalized.lower() for keyword in keywords):
            return category
    return "기타"


def clean_bid_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    원천 입찰공고 DataFrame을 분석에 쓰기 좋은 형태로 정리합니다.

    여기서 만들어지는 핵심 컬럼:
    - bid_title
    - agency_name
    - region
    - district
    - posted_date
    - estimated_amount
    - item_text
    - item_category
    """
    if df.empty:
        return df.copy()

    df = df.copy()
    df.columns = [str(col).strip() for col in df.columns]

    for standard_name, candidates in STANDARD_COLUMN_CANDIDATES.items():
        # 원천 컬럼명을 표준 컬럼명으로 복사합니다.
        source_column = _first_existing_column(df, candidates)
        if source_column is not None:
            df[standard_name] = df[source_column]

    if "bid_title" not in df.columns:
        df["bid_title"] = ""

    if "agency_name" not in df.columns:
        df["agency_name"] = ""

    if "region" not in df.columns:
        df["region"] = df.apply(_extract_region, axis=1)
    else:
        df["region"] = df["region"].astype("object")
        missing_region = df["region"].isna() | (df["region"].astype(str).str.strip() == "")
        df.loc[missing_region, "region"] = df.loc[missing_region].apply(_extract_region, axis=1)

    # 서울 자치구가 잡히면 region은 서울로 보정합니다.
    df["district"] = df.apply(_extract_district, axis=1)
    df.loc[df["district"] != "미상", "region"] = "서울"

    # 수집 단계에서 dminsttNm으로 태깅된 자치구는 텍스트 추출보다 신뢰도가 높으므로 덮어씁니다.
    if "_source_district" in df.columns:
        tagged = df["_source_district"].notna() & (df["_source_district"].astype(str).str.strip() != "")
        df.loc[tagged, "district"] = df.loc[tagged, "_source_district"]
        df.loc[tagged, "region"] = "서울"

    if "posted_date" in df.columns:
        df["posted_date"] = pd.to_datetime(df["posted_date"], errors="coerce")
    else:
        df["posted_date"] = pd.NaT

    if "estimated_amount" in df.columns:
        df["estimated_amount"] = _to_amount(df["estimated_amount"])
    else:
        df["estimated_amount"] = 0

    product_text = df.get("purchsObjPrdctList", "")
    df["item_text"] = (
        df["bid_title"].fillna("").astype(str)
        + " "
        + df["agency_name"].fillna("").astype(str)
        + " "
        + pd.Series(product_text, index=df.index).fillna("").astype(str)
    ).str.strip()
    df["item_category"] = df["item_text"].apply(_classify_item_category)

    return df
