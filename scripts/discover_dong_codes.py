"""
서울 25개 구 행정동 코드 자동 발견 및 dong_codes_raw.json 갱신

동작 방식:
    각 자치구의 후보 코드(51000~99000)를 행안부 연령 인구 API에 순서대로 조회해
    유효한 응답이 돌아오는 코드만 수집합니다.

실행:
    python scripts/discover_dong_codes.py
    python scripts/discover_dong_codes.py --districts 성동구 마포구 영등포구  # 특정 구만
    python scripts/discover_dong_codes.py --dry-run   # JSON 저장 없이 결과만 출력
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

DONG_CODES_PATH = ROOT / "data/reference/dong_codes_raw.json"
OUTPUT_PATH = DONG_CODES_PATH  # 덮어씀 (백업은 스크립트가 자동 생성)
TEST_YM = "202401"  # 테스트용 조회 월

# 서울 25개 구 행정동 코드 앞 4자리
DISTRICT_PREFIXES: dict[str, str] = {
    "종로구":   "1111",
    "중구":     "1114",
    "용산구":   "1117",
    "성동구":   "1120",
    "광진구":   "1121",
    "동대문구": "1123",
    "중랑구":   "1126",
    "성북구":   "1129",
    "강북구":   "1130",
    "도봉구":   "1132",
    "노원구":   "1135",
    "은평구":   "1138",
    "서대문구": "1141",
    "마포구":   "1144",
    "양천구":   "1147",
    "강서구":   "1150",
    "구로구":   "1153",
    "금천구":   "1154",
    "영등포구": "1156",
    "동작구":   "1159",
    "관악구":   "1162",
    "서초구":   "1165",
    "강남구":   "1168",
    "송파구":   "1171",
    "강동구":   "1174",
}


def _test_dong_code(code: str) -> str | None:
    """API 호출로 코드 유효성 확인. 유효하면 dong_nm 반환, 아니면 None."""
    from src.api.population_age_api import _fetch_dong
    rows = _fetch_dong(code, TEST_YM)
    if not rows:
        return None
    # 응답에서 동 이름 추출 시도
    if rows:
        dong_nm = rows[0].get("dongNm") or rows[0].get("admmNm") or rows[0].get("dong_nm")
        return str(dong_nm) if dong_nm else f"unknown_{code}"
    return None


def discover_district(district: str, prefix: str, delay: float = 0.3) -> list[dict]:
    """구 하나의 유효한 행정동 코드 목록을 반환."""
    found = []
    print(f"\n[{district}] 후보 코드 탐색 중 (prefix={prefix})...")
    for seq in range(51, 100):
        code = f"{prefix}{seq:03d}000"
        dong_nm = _test_dong_code(code)
        if dong_nm:
            print(f"  [OK] {code} -> {dong_nm}")
            found.append({"code": code, "dong_nm": dong_nm})
        time.sleep(delay)
    print(f"  → {len(found)}개 동 발견")
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--districts", nargs="*", default=None,
                        help="특정 구만 처리 (기본: 코드 불일치 구 + 관악구 + 18개 미등록 구)")
    parser.add_argument("--all", action="store_true",
                        help="25개 구 전체 재발견")
    parser.add_argument("--dry-run", action="store_true",
                        help="JSON 저장 없이 출력만")
    args = parser.parse_args()

    # 기존 JSON 로드
    with open(DONG_CODES_PATH, encoding="utf-8") as f:
        data: dict = json.load(f)

    # 처리 대상 구 결정
    if args.all:
        targets = list(DISTRICT_PREFIXES.keys())
    elif args.districts:
        targets = args.districts
    else:
        # 기본: 코드 오류 구 + 관악구(불완전) + 미등록 구
        wrong = ["마포구", "영등포구", "성동구"]  # 검증에서 ❌ 판정
        incomplete = ["관악구"]                    # 1개 동만
        missing = [g for g in DISTRICT_PREFIXES if g not in data]
        targets = list(dict.fromkeys(wrong + incomplete + missing))

    print(f"처리 대상 ({len(targets)}개 구): {targets}")

    # 백업
    if not args.dry_run:
        backup = DONG_CODES_PATH.with_suffix(".json.bak")
        backup.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n백업 저장: {backup}")

    # 구별 발견
    results: dict[str, list[dict]] = {}
    for district in targets:
        prefix = DISTRICT_PREFIXES.get(district)
        if not prefix:
            print(f"[SKIP] 알 수 없는 구: {district}")
            continue
        found = discover_district(district, prefix)
        results[district] = found

    # 결과 출력
    print("\n=== 발견 결과 ===")
    for gu, codes in results.items():
        print(f"{gu}: {len(codes)}개 동")

    if args.dry_run:
        print("\n--dry-run 모드: JSON 저장 생략")
        return

    # JSON 업데이트
    data.update(results)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n저장 완료: {OUTPUT_PATH}")
    print(f"총 {len(data)}개 구 등록")


if __name__ == "__main__":
    main()
