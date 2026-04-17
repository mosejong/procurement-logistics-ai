import os
from dotenv import load_dotenv

load_dotenv()

PROCUREMENT_API_KEY = os.getenv("PROCUREMENT_API_KEY", "")
BASE_URL_BID = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"