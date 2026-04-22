"""
소상공인시장진흥공단 상가(상권)정보 API - 자치구별 점포 수 집계

divId=signguCd, key=5자리법정동코드 형식으로 조회
"""

import time
import logging
import pandas as pd
import requests

from src.config.settings import STORE_API_KEY

logger = logging.getLogger(__name__)

BASE_URL = "https://apis.data.go.kr/B553077/api/open/sdsc2/storeListInDong"

# 소상공인 API 시군구코드 (법정동코드 앞 5자리 기준 — 표준 행정코드와 다름)
# API 실측 확인된 코드에 * 표시
DISTRICT_SIGNGU_CD: dict[str, str] = {
    "종로구": "11110",   # *확인
    "중구": "11020",
    "용산구": "11030",
    "성동구": "11440",   # *확인
    "광진구": "11215",
    "동대문구": "11230",
    "중랑구": "11260",
    "성북구": "11290",
    "강북구": "11305",
    "도봉구": "11320",
    "노원구": "11350",
    "은평구": "11380",
    "서대문구": "11410",
    "마포구": "11140",   # *확인
    "양천구": "11470",
    "강서구": "11160",
    "구로구": "11170",
    "금천구": "11545",
    "영등포구": "11590", # *확인
    "동작구": "11200",   # *확인
    "관악구": "11620",   # *확인
    "서초구": "11650",   # *확인
    "강남구": "11680",   # *확인
    "송파구": "11710",   # *확인
    "강동구": "11740",
}

# 업종대분류코드 → 우리 품목군 매핑 (소상공인 업종 기준)
INDS_LCL_TO_CATEGORY: dict[str, str] = {
    "D1": "급식/식품",          # 슈퍼마켓/편의점
    "D2": "사무용품/문구",       # 소매 - 도서/문구
    "D3": "가구/인테리어",       # 가정용품 소매
    "D4": "사무용품/문구",       # 전자/통신 소매
    "D5": "차량/운송",           # 자동차 소매
    "F1": "급식/식품",           # 한식
    "F2": "급식/식품",           # 외국식
    "F3": "급식/식품",           # 분식
    "F4": "급식/식품",           # 패스트푸드
    "F5": "급식/식품",           # 카페/음료
    "F6": "급식/식품",           # 주점
    "G1": "위생/방역",           # 세탁/세차
    "G2": "위생/방역",           # 이미용
    "G3": "시설관리/공사",       # 수리서비스
    "G4": "교육/교구",           # 교육
    "H1": "시설위탁/운영",       # 스포츠/레저
    "H2": "행사/홍보",           # 오락/문화
    "I1": "시설위탁/운영",       # 숙박
    "J1": "시설위탁/운영",       # 스포츠시설
    "L1": "환경개선/생활민원",   # 부동산
    "O1": "의료/복지",           # 의료
    "O2": "의료/복지",           # 보건/복지
    "P1": "교육/교구",           # 학문/교육
    "Q1": "의료/복지",           # 의료/복지 서비스
    "Q2": "위생/방역",           # 수리/개인서비스
}


def _fetch_page(signgu_cd: str, page: int, num_rows: int = 1000) -> dict:
    r = requests.get(
        BASE_URL,
        params={
            "serviceKey": STORE_API_KEY,
            "divId": "signguCd",
            "key": signgu_cd,
            "pageNo": page,
            "numOfRows": num_rows,
            "type": "json",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def fetch_store_counts(district: str, max_pages: int = 50) -> pd.DataFrame:
    """
    자치구명으로 소상공인 업종별 점포 수를 반환합니다.

    Returns:
        DataFrame with columns [district, inds_lv1_cd, inds_lv1_nm, store_count]
    """
    signgu_cd = DISTRICT_SIGNGU_CD.get(district)
    if not signgu_cd:
        logger.warning("시군구코드 없음: %s", district)
        return pd.DataFrame()

    all_items: list[dict] = []
    page = 1

    while page <= max_pages:
        try:
            data = _fetch_page(signgu_cd, page)
        except Exception as e:
            logger.error("store API 오류 (%s, page=%d): %s", district, page, e)
            break

        rc = data.get("header", {}).get("resultCode", "")
        if rc != "00":
            break

        body = data.get("body", {})
        items = body.get("items", [])
        if not items:
            break

        all_items.extend(items)

        total = int(body.get("totalCount", 0))
        if len(all_items) >= total:
            break

        page += 1
        time.sleep(0.3)

    if not all_items:
        return pd.DataFrame()

    df = pd.DataFrame(all_items)
    if "indsLclsCd" not in df.columns:
        return pd.DataFrame()

    counts = (
        df.groupby(["indsLclsCd", "indsLclsNm"], dropna=False)
        .size()
        .reset_index(name="store_count")
        .rename(columns={"indsLclsCd": "inds_lv1_cd", "indsLclsNm": "inds_lv1_nm"})
    )
    counts.insert(0, "district", district)
    return counts