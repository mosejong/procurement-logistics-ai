"""
기관명 → agency_type, 공고명 → item_category_detail 룰베이스 분류

역할:
    키워드 사전(_AGENCY_RULES, _ITEM_DETAIL_RULES) 기반으로 두 가지 분류를 생성합니다.

    agency_type     : 기관명 텍스트 → 8개 기관 유형
                      (행정기관 / 공공기관·재단 / 의료기관 / 어린이집·보육 / 학교 /
                       복지시설 / 문화·체육시설 / 기타·미분류)

    item_category_detail : 공고명 텍스트 → 18개 세부 발주 유형
                      (시설유지보수 / IT장비·전산 / 청소·환경미화 / 방역·소독 등)
                      opportunity_score 계산의 기준 분류입니다.

분류 방식:
    - 키워드 리스트를 순서대로 순회하며 첫 매칭 카테고리를 반환합니다.
    - 어느 키워드도 매칭되지 않으면 '기타/미분류'로 분류됩니다.
    - 기타/미분류 목표 비율: 20% 이하 (현재 4.9%)

사용법:
    from src.preprocess.classify_agency import apply_classifications
    df = apply_classifications(df)
"""

import re
import pandas as pd


# ── 텍스트 정규화 ─────────────────────────────────────────────────────────────

def normalize_text(text) -> str:
    """소문자 변환, 특수문자 제거, 연속 공백 정리, 결측치 방어"""
    if text is None or (isinstance(text, float)):
        return ""
    text = str(text)
    text = text.lower()
    text = re.sub(r"[^\w\s가-힣]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ── agency_type 분류 ──────────────────────────────────────────────────────────

# 문화/체육시설 우선 적용 키워드 (행정기관 키워드와 겹칠 때 먼저 체크)
_CULTURE_PRIORITY_KEYWORDS = [
    "도서관", "박물관", "미술관", "체육관", "체육센터", "문화센터", "문화관",
    "수영장", "공연장", "전시관", "스포츠센터",
]

# 행정기관 정규식: "서울특별시 OO구", "서울시 OO구" 형태 감지
# 공단·재단·보건소·유치원 등 다른 키워드 없이 구명으로만 끝나는 경우
_ADMIN_OFFICE_PATTERN = re.compile(
    r"(서울특별시|서울시)\s*(관악구|강남구|마포구|영등포구|성동구|종로구|송파구"
    r"|강북구|강동구|강서구|노원구|도봉구|동대문구|동작구|서대문구|서초구"
    r"|성북구|양천구|용산구|은평구|중구|중랑구|광진구|금천구|구로구)$"
)

# 순서대로 매칭 (위에서 아래로 첫 매칭 적용)
_AGENCY_TYPE_RULES: list[tuple[str, list[str]]] = [
    ("어린이집/보육", ["어린이집", "보육원", "유치원"]),
    ("의료기관",      ["보건소", "보건지소", "병원", "의원", "의료원", "한의원"]),
    ("학교",          ["초등학교", "중학교", "고등학교", "대학교", "특수학교", "학교"]),
    ("복지시설",      ["복지관", "복지원", "요양원", "요양센터", "장애인", "사회복지", "노인복지", "재활원"]),
    ("문화/체육시설", ["도서관", "문화원", "문화센터", "문화관", "체육관", "체육센터",
                       "수영장", "박물관", "미술관", "공연장", "전시관", "스포츠센터"]),
    ("행정기관",      ["구청", "시청", "군청", "동주민센터", "행정복지센터", "주민자치", "동사무소"]),
    ("공공기관/재단", ["공단", "재단", "연구원", "공사", "협회", "진흥원"]),
]


def classify_agency(agency_name: str) -> str:
    """
    기관명 -> agency_type 단일 분류.

    분류 순서:
    1. 문화/체육시설 명확 키워드 선체크 (도서관·박물관 등 행정기관명과 혼재 방어)
    2. 유형별 키워드 순서 매칭
    3. 정규식으로 "서울특별시 OO구" 형태 감지 -> 행정기관
    4. 미매칭 -> 기타/미분류
    """
    raw = str(agency_name) if agency_name else ""
    text = normalize_text(raw)

    # 예외 규칙: 문화/체육 명확 키워드가 있으면 행정기관보다 우선
    if any(kw in text for kw in _CULTURE_PRIORITY_KEYWORDS):
        return "문화/체육시설"

    for agency_type, keywords in _AGENCY_TYPE_RULES:
        if any(kw in text for kw in keywords):
            return agency_type

    # "서울특별시 OO구" 패턴 (구청이라고 명시 안 된 경우 대응)
    if _ADMIN_OFFICE_PATTERN.search(raw.strip()):
        return "행정기관"

    return "기타/미분류"


# ── item_category_detail 분류 ─────────────────────────────────────────────────

# 순서대로 매칭 (위에서 아래로 첫 매칭 적용)
_ITEM_DETAIL_RULES: list[tuple[str, list[str]]] = [
    ("방역/소독",       ["방역", "소독", "해충", "방충", "쥐", "바퀴"]),
    ("폐기물/환경",     ["폐기물", "폐합성", "폐매트리스", "음식물류", "생활폐기물", "쓰레기", "재활용", "수거",
                          "폐비닐", "폐필름", "준설토"]),
    ("급식/식자재",     ["급식", "식자재", "식품", "부식", "식단", "쌀", "김치"]),
    ("IT장비/전산",     ["pc", "노트북", "프린터", "소프트웨어", "sw", "전산", "시스템",
                          "서버", "네트워크", "it", "컴퓨터", "태블릿", "모니터",
                          "cctv", "그룹웨어", "erp", "홈페이지", "앱", "db구축", "gis",
                          "스토리지"]),
    ("경비/보안",       ["경비", "보안", "순찰", "방범"]),
    ("청소/환경미화",   ["청소", "환경미화", "미화", "청결", "가로청소", "뒷골목청소", "세탁", "살수"]),
    ("인쇄/홍보물",     ["인쇄", "현수막", "홍보물", "리플렛", "배너", "책자",
                          "브로슈어", "포스터", "소식지", "발행", "제작", "홍보대행", "sns"]),
    ("시설유지보수",    ["유지보수", "유지관리", "시설관리", "유지", "보수", "수선", "점검", "수리", "정비",
                          "노후", "교체", "승강기", "가림막", "안전관리", "안전진단", "성능평가"]),
    ("교육물품/교구",   ["교구", "교재", "학습", "교육자료", "교육물품", "학용품", "정보화교육", "도서 납품", "도서구입"]),
    ("의료/복지용품",   ["위생용품", "의료용품", "의약품", "복지용품", "기저귀", "마스크",
                          "장갑", "소독제", "모자보건", "유축기", "검진"]),
    ("행사/운영용역",   ["행사", "축제", "운영", "공연", "이벤트", "진행", "콜센터", "프로그램", "위탁"]),
    ("조경/녹지관리",   ["조경", "잔디", "수목", "가로수", "녹지", "제초", "제설", "나무", "공원", "산림", "숲", "화분"]),
    ("급수/전기/설비",  ["급수", "배관", "전기", "설비", "공조", "냉난방", "소방", "가스", "전기안전"]),
    ("차량/운송",       ["차량", "운송", "셔틀", "이사", "임차", "택배", "버스", "구급차"]),
    ("사무용품/소모품", ["사무용품", "문구", "토너", "복사지", "소모품", "잉크", "볼펜"]),
    ("건설/공사",       ["공사", "건축", "철거", "신축", "증축", "감리", "측량", "재개발", "재건축",
                          "영향평가", "지하안전", "계측", "실시설계", "기본설계", "구조설계",
                          "건설사업관리", "설계용역", "보축", "내진", "리모델링", "설계공모"]),
    ("보험/금융",       ["보험가입", "보험 가입", "자동차보험", "자동차 보험", "자전거 보험",
                          "단체보험", "단체보장보험", "단체상해보험", "안전보험", "공제", "재해예방",
                          "상해보험"]),
    ("전문용역/컨설팅", ["컨설팅", "연구용역", "연구 용역", "학술연구", "지역사회보장계획", "조직진단",
                          "성과관리", "용도지구", "지구단위계획", "도시관리계획", "타당성", "교통량",
                          "중장기계획", "종합계획", "수립 용역", "공동조사", "기록화", "실태조사",
                          "씽크홀", "공동탐사", "위험성평가", "위험성 평가"]),
]


def classify_item_detail(bid_title: str) -> str:
    """
    공고명 -> item_category_detail 단일 분류.
    첫 번째 매칭 키워드 기준 적용, 미매칭은 기타/미분류 반환.
    """
    text = normalize_text(bid_title)

    for category, keywords in _ITEM_DETAIL_RULES:
        if any(kw in text for kw in keywords):
            return category

    return "기타/미분류"


# ── DataFrame 적용 ────────────────────────────────────────────────────────────

def apply_classifications(df: pd.DataFrame) -> pd.DataFrame:
    """
    agency_name -> agency_type,
    bid_title   -> item_category_detail
    두 컬럼을 DataFrame에 추가해서 반환.
    """
    df = df.copy()

    agency_col = "agency_name" if "agency_name" in df.columns else None
    title_col  = "bid_title"   if "bid_title"   in df.columns else None

    if agency_col:
        df["agency_type"] = df[agency_col].apply(classify_agency)
    else:
        print("[경고] agency_name 컬럼 없음 - agency_type 생략")

    if title_col:
        df["item_category_detail"] = df[title_col].apply(classify_item_detail)
    else:
        print("[경고] bid_title 컬럼 없음 - item_category_detail 생략")

    return df


# ── 분포 확인 ─────────────────────────────────────────────────────────────────

def print_classification_report(df: pd.DataFrame) -> None:
    """agency_type / item_category_detail 분포 및 기타/미분류 비율 출력"""
    total = len(df)

    if "agency_type" in df.columns:
        print("=" * 50)
        print("[ agency_type 분포 ]")
        dist = df["agency_type"].value_counts()
        for label, cnt in dist.items():
            print(f"  {label:<20} {cnt:>5}건  ({cnt/total*100:.1f}%)")
        etc_rate = (df["agency_type"] == "기타/미분류").sum() / total * 100
        print(f"\n  >> 기타/미분류 비율: {etc_rate:.1f}%")
        if etc_rate > 20:
            print("  [!] 20% 초과 - 키워드 사전 보완 필요")

    if "item_category_detail" in df.columns:
        print("=" * 50)
        print("[ item_category_detail 분포 ]")
        dist = df["item_category_detail"].value_counts()
        for label, cnt in dist.items():
            print(f"  {label:<20} {cnt:>5}건  ({cnt/total*100:.1f}%)")
        etc_rate = (df["item_category_detail"] == "기타/미분류").sum() / total * 100
        print(f"\n  >> 기타/미분류 비율: {etc_rate:.1f}%")
        if etc_rate > 20:
            print("  [!] 20% 초과 - 키워드 사전 보완 필요")

    print("=" * 50)


# ── 직접 실행 시 테스트 ───────────────────────────────────────────────────────

if __name__ == "__main__":
    from src.utils.file_handler import save_csv

    cleaned_path = "data/processed/seoul_bid_cleaned.csv"
    df = pd.read_csv(cleaned_path, encoding="utf-8-sig")

    df = apply_classifications(df)
    print_classification_report(df)

    # 미분류 샘플 확인
    unclassified = df[df["item_category_detail"] == "기타/미분류"][["bid_title", "agency_type"]].head(20)
    with open("debug_unclassified.txt", "w", encoding="utf-8") as f:
        f.write("=== item_category_detail 미분류 샘플 ===\n")
        f.write(unclassified.to_string())

    path = save_csv(df, "data/processed/seoul_bid_classified.csv")
    print(f"\n저장: {path}")
