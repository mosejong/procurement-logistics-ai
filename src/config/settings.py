import os
from dotenv import load_dotenv

load_dotenv()

PROCUREMENT_API_KEY = os.getenv("PROCUREMENT_API_KEY", "")
POPULATION_API_KEY = os.getenv("POPULATION_API_KEY", PROCUREMENT_API_KEY)
BASE_URL_BID = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"
BASE_URL_POPULATION = os.getenv(
    "BASE_URL_POPULATION",
    "https://apis.data.go.kr/1741000/stdgPpltnHhStus/selectStdgPpltnHhStus",
)

DATA_RAW_DIR = "data/raw"
DATA_PROCESSED_DIR = "data/processed"
OUTPUT_TABLE_DIR = "outputs/tables"
OUTPUT_FIGURE_DIR = "outputs/figures"
OUTPUT_REPORT_DIR = "outputs/reports"
