"""
NEIS 학교기본정보 API — 학교명 → 시도명 자동 매핑

데이터 출처: 교육부 교육통계서비스 (NEIS Open API)
    endpoint: https://open.neis.go.kr/hub/schoolInfo
    API key 발급: https://open.neis.go.kr

응답 컬럼 (사용):
    SCHUL_NM          : 학교명
    ATPT_OFCDC_SC_NM  : 시도교육청명  (e.g. "서울특별시교육청")
    ORG_RDNMA         : 도로명주소
    SD_SCHUL_CODE     : 학교코드
"""

import time

import requests

BASE_URL = "https://open.neis.go.kr/hub/schoolInfo"

# 시도교육청명 → 시도 정규화 테이블
_EDU_OFFICE_TO_SIDO: dict[str, str] = {
    "서울특별시교육청": "서울특별시",
    "부산광역시교육청": "부산광역시",
    "대구광역시교육청": "대구광역시",
    "인천광역시교육청": "인천광역시",
    "광주광역시교육청": "광주광역시",
    "대전광역시교육청": "대전광역시",
    "울산광역시교육청": "울산광역시",
    "세종특별자치시교육청": "세종특별자치시",
    "경기도교육청": "경기도",
    "강원특별자치도교육청": "강원특별자치도",
    "충청북도교육청": "충청북도",
    "충청남도교육청": "충청남도",
    "전라북도교육청": "전라북도",
    "전북특별자치도교육청": "전라북도",  # 2024년 전북특별자치도 출범 후 명칭 변경
    "전라남도교육청": "전라남도",
    "경상북도교육청": "경상북도",
    "경상남도교육청": "경상남도",
    "제주특별자치도교육청": "제주특별자치도",
}


def resolve_sido(atpt_nm: str) -> str:
    """시도교육청명 → 시도명. 매핑 실패 시 원문 그대로."""
    return _EDU_OFFICE_TO_SIDO.get(atpt_nm, atpt_nm)


def search_school(school_name: str, api_key: str = "", retry: int = 2) -> list[dict]:
    """
    학교명으로 NEIS 학교기본정보 조회.

    Returns:
        list of dicts — 각 항목에 SCHUL_NM, ATPT_OFCDC_SC_NM, ORG_RDNMA, SD_SCHUL_CODE 포함.
        빈 리스트 = 조회 실패 또는 결과 없음.
    """
    params: dict = {
        "Type": "json",
        "pIndex": 1,
        "pSize": 10,
        "SCHUL_NM": school_name,
    }
    if api_key:
        params["KEY"] = api_key

    for attempt in range(retry + 1):
        try:
            resp = requests.get(BASE_URL, params=params, timeout=10)
            resp.raise_for_status()
            body = resp.json()

            # NEIS API: 결과 없을 때 {"RESULT": {"CODE": "INFO-200", ...}} 반환
            if "schoolInfo" not in body:
                return []

            rows = body["schoolInfo"][1].get("row", [])
            return rows
        except requests.RequestException:
            if attempt < retry:
                time.sleep(1)
            continue

    return []


def classify_result(school_name: str, rows: list[dict]) -> tuple[str, str]:
    """
    조회 결과를 confirmed / ambiguous / unresolved 로 분류.

    Returns:
        (status, city)
        status: "confirmed" | "ambiguous" | "unresolved"
        city: 확정 시도명 (confirmed일 때만 유효)
    """
    exact = [r for r in rows if r.get("SCHUL_NM", "") == school_name]

    if len(exact) == 1:
        city = resolve_sido(exact[0].get("ATPT_OFCDC_SC_NM", ""))
        return "confirmed", city

    if len(exact) > 1:
        return "ambiguous", ""

    # 이름이 완전 일치하는 항목이 없으면 unresolved
    return "unresolved", ""
