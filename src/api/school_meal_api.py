"""
aT 농수산물사이버거래소 — 학교급식 낙찰/입찰 현황 API

데이터 출처: 공공데이터포털 — 한국농수산식품유통공사
    낙찰: https://api.odcloud.kr/api/15071800/v1/uddi:e1e17d54-39f7-421d-9f2b-b633ff59b8b3
    입찰: https://api.odcloud.kr/api/15070124/v1/uddi:a11112e2-6450-43c7-9c85-ac65562ba2a5

낙찰 컬럼: 개찰일시, 계약명, 계약방법명, 계약형태명, 공고번호, 구매사명, 등록일자, 전자입찰상태명
입찰 컬럼: 계약방법명, 공고일자, 구매사명, 등록일자, 입찰명, 입찰시작일시, 전자입찰일련번호

건수 (2024-12-31 기준):
    낙찰: 165,461건
    입찰:  83,963건

한계: 시도(지역) 컬럼 없음 → 구매사명(학교명) 키워드로 지역 추출 필요
"""

import requests
import pandas as pd

from src.config.settings import PUBLIC_DATA_API_KEY

BASE = "https://api.odcloud.kr/api"

URL_AWARD = f"{BASE}/15071800/v1/uddi:e1e17d54-39f7-421d-9f2b-b633ff59b8b3"
URL_BID   = f"{BASE}/15070124/v1/uddi:a11112e2-6450-43c7-9c85-ac65562ba2a5"

# 학교명 → 시도 키워드 매핑 (학교명에 포함된 지역 힌트)
SCHOOL_SIDO_KEYWORDS: dict[str, str] = {
    "서울": "서울특별시", "경기": "경기도", "인천": "인천광역시",
    "부산": "부산광역시", "대구": "대구광역시", "울산": "울산광역시",
    "광주": "광주광역시", "대전": "대전광역시", "세종": "세종특별자치시",
    "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
    "전북": "전라북도", "전남": "전라남도", "경북": "경상북도",
    "경남": "경상남도", "제주": "제주특별자치도",
}

# 학교명 → 시도 직접 매핑 (GPT 생성, 미매핑 상위 30개 기준)
# 주의: 동명이교 가능성이 있는 항목은 주석 표시.
# 향후 원본 데이터에 학교 주소·교육청·지역 컬럼이 추가되면 그 값을 우선 사용하고,
# 이 dict는 fallback으로만 사용할 것.
SCHOOL_CITY_MAP: dict[str, str] = {
    "명지초등학교": "서울특별시",
    "영흥고등학교": "전라남도",        # 주의: 인천 동명 후보
    "순창고등학교": "전라북도",
    "산외초등학교": "전라북도",        # 주의: 경남/충북 동명 후보
    "광양제철고등학교": "전라남도",
    "오현고등학교": "제주특별자치도",
    "덕원여자고등학교": "서울특별시",
    "백석중학교": "경기도",            # 주의: 서울/경기/인천/충남 동명 후보
    "문지초등학교": "대전광역시",
    "고창북고등학교": "전라북도",
    "덕암정보고등학교": "전라북도",
    "동암차돌학교": "전라북도",
    "순천금당고등학교": "전라남도",
    "장성고등학교": "전라남도",
    "신명초등학교": "부산광역시",      # 주의: 서울신명/김해신명 유사명
    "부안해오름유치원": "전라북도",
    "명지꿈자람유치원": "부산광역시",
    "언남고등학교": "서울특별시",
    "대일외국어고등학교": "서울특별시",
    "성동초등학교": "서울특별시",      # 주의: 충남/울산/경북 동명 후보
    "대연고등학교": "부산광역시",
    "동천초등학교": "부산광역시",      # 주의: 울산/경북/대구 동명 후보
    "부암초등학교": "부산광역시",
    "신촌초등학교": "부산광역시",      # 주의: 인천/경기 동명 후보
    "정관초등학교": "부산광역시",
    "죽성초등학교": "부산광역시",
    "내리초등학교": "부산광역시",      # 주의: 인천 폐교/전남 동명 후보
    "명호초등학교": "부산광역시",      # 주의: 경북 봉화 동명 후보
    "숭덕여자고등학교": "인천광역시",
    "대월초등학교": "경기도",          # 주의: 인천 강화 동명 후보
}


def _get_page(url: str, page: int, per_page: int = 1000) -> dict:
    r = requests.get(
        url,
        params={"serviceKey": PUBLIC_DATA_API_KEY, "page": page, "perPage": per_page},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def fetch_all(url: str, max_pages: int = 200, per_page: int = 1000, verbose: bool = True) -> pd.DataFrame:
    """전체 페이지 수집."""
    first = _get_page(url, 1, per_page)
    total = first.get("matchCount", 0)
    frames = [pd.DataFrame(first.get("data", []))]

    if verbose:
        print(f"  총 {total:,}건, {-(-total // per_page)}페이지 수집 예정")

    import math
    pages = min(math.ceil(total / per_page), max_pages)

    for p in range(2, pages + 1):
        data = _get_page(url, p, per_page)
        rows = data.get("data", [])
        if not rows:
            break
        frames.append(pd.DataFrame(rows))
        if verbose and p % 10 == 0:
            print(f"  {p}/{pages} 페이지 완료")

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_neis_cache() -> dict[str, str]:
    """NEIS 자동 매핑 캐시 로드. 파일 없으면 빈 dict."""
    from pathlib import Path
    csv_path = Path(__file__).parent.parent.parent / "data" / "reference" / "school_city_map_neis.csv"
    if not csv_path.exists():
        return {}
    try:
        df = pd.read_csv(csv_path, encoding="utf-8-sig")
        return dict(zip(df["school_name"], df["city"]))
    except Exception:
        return {}


# 모듈 로드 시 캐시 1회 읽기 (build_school_city_map.py 실행 전엔 빈 dict)
_NEIS_CACHE: dict[str, str] = load_neis_cache()


def extract_sido(school_name: str, neis_cache: dict[str, str] | None = None) -> str:
    """
    학교명 → 시도 추출. 매핑 실패 시 '기타'.

    우선순위:
      1. SCHOOL_SIDO_KEYWORDS — 학교명 내 시도 키워드 포함 여부 (빠른 패턴)
      2. NEIS 자동 매핑 캐시  — build_school_city_map.py 실행 결과
      3. SCHOOL_CITY_MAP      — GPT 수동 매핑 (동명이교 주의 항목 포함)
    """
    if not isinstance(school_name, str):
        return "기타"
    for keyword, city in SCHOOL_SIDO_KEYWORDS.items():
        if keyword in school_name:
            return city
    cache = neis_cache if neis_cache is not None else _NEIS_CACHE
    if school_name in cache:
        return cache[school_name]
    if school_name in SCHOOL_CITY_MAP:
        return SCHOOL_CITY_MAP[school_name]
    return "기타"
