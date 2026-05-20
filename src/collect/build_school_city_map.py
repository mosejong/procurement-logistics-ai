"""
NEIS 학교기본정보 API로 학교명 → 시도 매핑 캐시 생성

입력:
    outputs/tables/unmapped_schools.txt  — 미매핑 학교명 (행당 1건)

출력:
    data/reference/school_city_map_neis.csv  — 확정 매핑 (school_name, city)
    outputs/tables/ambiguous_schools.csv      — 동명이교 (학교명, 후보 목록)
    outputs/tables/unresolved_schools.csv     — API 미조회 또는 결과 없음

실행:
    python -m src.collect.build_school_city_map
    python -m src.collect.build_school_city_map --limit 100  # 처음 N개만 (테스트)
    python -m src.collect.build_school_city_map --delay 0.3  # 요청 간 대기(초)
"""

import argparse
import time
from pathlib import Path

import pandas as pd

from src.api.neis_school_api import classify_result, search_school
from src.config.settings import NEIS_API_KEY

ROOT = Path(__file__).parent.parent.parent
UNMAPPED_PATH = ROOT / "outputs" / "tables" / "unmapped_schools.txt"
CACHE_PATH    = ROOT / "data" / "reference" / "school_city_map_neis.csv"
AMBIG_PATH    = ROOT / "outputs" / "tables" / "ambiguous_schools.csv"
UNRESOLV_PATH = ROOT / "outputs" / "tables" / "unresolved_schools.csv"


def _load_existing_cache() -> set[str]:
    """이미 캐시에 저장된 학교명 반환 (재실행 시 중복 조회 방지)."""
    if not CACHE_PATH.exists():
        return set()
    df = pd.read_csv(CACHE_PATH, encoding="utf-8-sig")
    return set(df["school_name"].tolist())


def run(limit: int | None = None, delay: float = 0.2) -> None:
    if not UNMAPPED_PATH.exists():
        print(f"[ERROR] {UNMAPPED_PATH} 없음 — collect_school_meal.py를 먼저 실행하세요.")
        return

    raw_lines = UNMAPPED_PATH.read_text(encoding="utf-8").strip().splitlines()
    schools = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        # 헤더 줄 건너뜀 ("미매핑", "school_name" 등으로 시작)
        if line.startswith("미매핑") or line.startswith("school_name"):
            continue
        # "학교명: N건" 형식 → 학교명만 추출
        if ": " in line:
            name = line.split(":")[0].strip()
        else:
            name = line
        if name:
            schools.append(name)

    already_cached = _load_existing_cache()
    schools = [s.strip() for s in schools if s.strip() and s.strip() not in already_cached]

    if limit:
        schools = schools[:limit]

    total = len(schools)
    print(f"조회 대상: {total:,}건 (기존 캐시 {len(already_cached):,}건 제외)")

    confirmed_rows: list[dict] = []
    ambiguous_rows: list[dict] = []
    unresolved_rows: list[dict] = []

    for i, name in enumerate(schools, 1):
        rows = search_school(name, api_key=NEIS_API_KEY)
        status, city = classify_result(name, rows)

        if status == "confirmed":
            confirmed_rows.append({"school_name": name, "city": city})
        elif status == "ambiguous":
            candidates = ", ".join(
                f"{r.get('SCHUL_NM')}({r.get('ATPT_OFCDC_SC_NM', '')})"
                for r in rows if r.get("SCHUL_NM") == name
            )
            ambiguous_rows.append({"school_name": name, "candidates": candidates})
        else:
            unresolved_rows.append({"school_name": name})

        if i % 50 == 0 or i == total:
            print(f"  {i}/{total} / confirmed={len(confirmed_rows)}, ambiguous={len(ambiguous_rows)}, unresolved={len(unresolved_rows)}")

        time.sleep(delay)

    # ── 저장 ──────────────────────────────────────────────────────────
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 확정 캐시: 기존 파일에 append (중복 제거)
    if confirmed_rows:
        new_df = pd.DataFrame(confirmed_rows)
        if CACHE_PATH.exists():
            existing = pd.read_csv(CACHE_PATH, encoding="utf-8-sig")
            combined = pd.concat([existing, new_df], ignore_index=True).drop_duplicates("school_name")
        else:
            combined = new_df
        combined.to_csv(CACHE_PATH, index=False, encoding="utf-8-sig")
        print(f"\n[OK] 확정 캐시 → {CACHE_PATH.name} ({len(combined):,}건)")

    if ambiguous_rows:
        pd.DataFrame(ambiguous_rows).to_csv(AMBIG_PATH, index=False, encoding="utf-8-sig")
        print(f"[OK] 동명이교 → {AMBIG_PATH.name} ({len(ambiguous_rows):,}건)")

    if unresolved_rows:
        pd.DataFrame(unresolved_rows).to_csv(UNRESOLV_PATH, index=False, encoding="utf-8-sig")
        print(f"[OK] 미해결  → {UNRESOLV_PATH.name} ({len(unresolved_rows):,}건)")

    print(f"\n완료: 확정 {len(confirmed_rows)}, 동명이교 {len(ambiguous_rows)}, 미해결 {len(unresolved_rows)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="처음 N건만 처리 (테스트)")
    parser.add_argument("--delay", type=float, default=0.2, help="요청 간 대기 시간(초)")
    args = parser.parse_args()
    run(limit=args.limit, delay=args.delay)
