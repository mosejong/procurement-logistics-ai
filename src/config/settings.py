import os
from dotenv import load_dotenv

load_dotenv()


def _get_secret(key: str, default: str = "") -> str:
    """로컬: .env / Streamlit Cloud: st.secrets 순서로 읽음."""
    value = os.getenv(key, "")
    if value:
        return value
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        return default


PUBLIC_DATA_API_KEY = _get_secret("PUBLIC_DATA_API_KEY")

# 하위 호환: 개별 키가 .env에 있으면 그걸 쓰고, 없으면 공통 키로 폴백
PROCUREMENT_API_KEY = _get_secret("PROCUREMENT_API_KEY") or PUBLIC_DATA_API_KEY
POPULATION_API_KEY = _get_secret("POPULATION_API_KEY") or PUBLIC_DATA_API_KEY
POPULATION_AGE_API_KEY = _get_secret("POPULATION_AGE_API_KEY") or PUBLIC_DATA_API_KEY
STORE_API_KEY = _get_secret("STORE_API_KEY") or PUBLIC_DATA_API_KEY
AWARD_API_KEY = _get_secret("AWARD_API_KEY") or PUBLIC_DATA_API_KEY

GEMINI_API_KEY = _get_secret("GEMINI_API_KEY")

BASE_URL_BID = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"
BASE_URL_POPULATION = os.getenv(
    "BASE_URL_POPULATION",
    "https://apis.data.go.kr/1741000/stdgPpltnHhStus/selectStdgPpltnHhStus",
)
BASE_URL_POPULATION_AGE = "https://apis.data.go.kr/1741000/주민등록인구기타현황/행정동별5세연령및성별주민등록인구"
BASE_URL_STORE = "https://apis.data.go.kr/B553077/api/open/sdsc2"
BASE_URL_AWARD = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"

DATA_RAW_DIR = "data/raw"
DATA_PROCESSED_DIR = "data/processed"
OUTPUT_TABLE_DIR = "outputs/tables"
OUTPUT_FIGURE_DIR = "outputs/figures"
OUTPUT_REPORT_DIR = "outputs/reports"
