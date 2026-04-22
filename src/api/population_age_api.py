"""
행정안전부 행정동별 5세 연령 및 성별 주민등록인구 API

admmCd = 10자리 행정동코드 (동 단위)
srchFrYm / srchToYm = 'yyyyMM' 형식
"""
import json
import logging
import time
from pathlib import Path

import requests
import pandas as pd
import xml.etree.ElementTree as ET

from src.config.settings import POPULATION_AGE_API_KEY

logger = logging.getLogger(__name__)

BASE_URL = "https://apis.data.go.kr/1741000/admmSexdAgePpltn/selectAdmmSexdAgePpltn"
DONG_CODES_PATH = Path("data/reference/dong_codes_raw.json")


def load_dong_codes() -> dict[str, list[dict]]:
    """자치구 → 행정동 코드 목록 반환"""
    if not DONG_CODES_PATH.exists():
        raise FileNotFoundError(f"행정동 코드 파일 없음: {DONG_CODES_PATH}")
    with open(DONG_CODES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _fetch_dong(admm_cd: str, ym: str) -> list[dict]:
    """단일 행정동의 1개월 인구 데이터 반환"""
    r = requests.get(BASE_URL, params={
        "serviceKey": POPULATION_AGE_API_KEY,
        "admmCd": admm_cd,
        "srchFrYm": ym,
        "srchToYm": ym,
        "pageNo": 1,
        "numOfRows": 1000,
    }, timeout=20)

    try:
        root = ET.fromstring(r.text)
    except ET.ParseError:
        logger.warning("XML 파싱 오류: %s", admm_cd)
        return []

    header = root.find(".//header")
    if header is None:
        return []
    rc = header.find("resultCode")
    if rc is None or rc.text not in ("0", "00"):
        return []

    items = root.find(".//items")
    if items is None:
        return []

    rows = []
    for item in items:
        row = {child.tag: child.text for child in item}
        rows.append(row)
    return rows


def fetch_district_age_profile(district: str, dong_codes: list[str], ym: str = "202401") -> pd.DataFrame:
    """
    자치구 내 모든 행정동 인구 데이터를 합산해 연령대별 프로파일 반환.

    Returns:
        DataFrame with columns [district, age_group, male_cnt, feml_cnt, total_cnt]
    """
    age_cols = [f"male{a}AgeNmprCnt" for a in range(0, 110, 10)] + \
               [f"feml{a}AgeNmprCnt" for a in range(0, 110, 10)]

    all_rows = []
    for code in dong_codes:
        rows = _fetch_dong(code, ym)
        all_rows.extend(rows)
        time.sleep(0.3)

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    for col in age_cols:
        df[col] = pd.to_numeric(df.get(col, 0), errors="coerce").fillna(0)

    # 연령대 집계 (10세 단위)
    age_labels = ["0~9세", "10대", "20대", "30대", "40대", "50대", "60대", "70대", "80대", "90세이상"]
    records = []
    for i, label in enumerate(age_labels):
        age_val = i * 10
        male = df[f"male{age_val}AgeNmprCnt"].sum()
        feml = df[f"feml{age_val}AgeNmprCnt"].sum()
        records.append({
            "district": district,
            "age_group": label,
            "male_cnt": int(male),
            "feml_cnt": int(feml),
            "total_cnt": int(male + feml),
        })

    return pd.DataFrame(records)


def fetch_all_districts(ym: str = "202401") -> pd.DataFrame:
    """7개 자치구 전체 연령별 인구 수집"""
    dong_map = load_dong_codes()
    frames = []
    for district, codes in dong_map.items():
        if not codes:
            logger.warning("행정동 코드 없음: %s", district)
            continue
        code_list = [c["code"] for c in codes]
        logger.info("%s: %d개 행정동 수집 중", district, len(code_list))
        df = fetch_district_age_profile(district, code_list, ym)
        if not df.empty:
            frames.append(df)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
