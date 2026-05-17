"""
한국 시군구 GeoJSON 다운로드 스크립트

출처: southkorea/southkorea-maps (GitHub, 공개 라이선스)
대상: 전국 250여 개 시군구 경계 (0.4MB 경량화 버전)
출력: data/reference/korea_sigungu.geojson
"""
import json
from pathlib import Path

import requests

ROOT    = Path(__file__).parent.parent.parent
OUT_DIR = ROOT / "data" / "reference"
OUT_PATH = OUT_DIR / "korea_sigungu.geojson"

URL = (
    "https://raw.githubusercontent.com/southkorea/southkorea-maps"
    "/master/kostat/2013/json/skorea_municipalities_geo_simple.json"
)

CODE_TO_SIDO: dict[str, str] = {
    "11": "서울특별시",
    "21": "부산광역시",
    "22": "대구광역시",
    "23": "인천광역시",
    "24": "광주광역시",
    "25": "대전광역시",
    "26": "울산광역시",
    "29": "세종특별자치시",
    "31": "경기도",
    "32": "강원특별자치도",
    "33": "충청북도",
    "34": "충청남도",
    "35": "전라북도",
    "36": "전라남도",
    "37": "경상북도",
    "38": "경상남도",
    "39": "제주특별자치도",
}


def run() -> None:
    print(f"다운로드 중: {URL}")
    resp = requests.get(URL, timeout=30)
    resp.raise_for_status()
    geojson = resp.json()

    # 각 feature에 sido_name 속성 추가
    for feature in geojson.get("features", []):
        props = feature.setdefault("properties", {})
        code = str(props.get("code", ""))
        props["sido_name"] = CODE_TO_SIDO.get(code[:2], "기타")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False)

    feat_count = len(geojson.get("features", []))
    print(f"[OK] {OUT_PATH.name} ({feat_count}개 시군구)")


if __name__ == "__main__":
    run()
