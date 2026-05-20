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


def extract_sido(school_name: str) -> str:
    """학교명에서 시도 추출. 매핑 실패 시 '기타'."""
    if not isinstance(school_name, str):
        return "기타"
    for keyword, city in SCHOOL_SIDO_KEYWORDS.items():
        if keyword in school_name:
            return city
    return "기타"
