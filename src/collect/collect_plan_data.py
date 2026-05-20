"""
발주계획 + 종합쇼핑몰 납품요구 수집 및 집계

결과물:
    outputs/tables/procurement_plan_summary.csv  — 향후 N개월 발주계획 (도시 × 품목 집계)
    outputs/tables/shopping_mall_summary.csv     — 최근 M일 종합쇼핑몰 납품요구 (도시 × 품목 집계)

사용:
    python -m src.collect.collect_plan_data                 # 기본: 6개월 발주계획 + 30일 납품요구
    python -m src.collect.collect_plan_data --months 3      # 향후 3개월 발주계획
    python -m src.collect.collect_plan_data --days 7        # 최근 7일 납품요구
    python -m src.collect.collect_plan_data --plan-only     # 발주계획만
    python -m src.collect.collect_plan_data --shop-only     # 납품요구만
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from src.api.procurement_plan_api import collect_mas_products, collect_plan_all

OUTPUT_DIR = Path("outputs/tables")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 시/도명 정규화 ─────────────────────────────────────────────────────

_CITY_FULL = [
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
    "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원도",
    "충청북도", "충청남도", "전라북도", "전라남도", "경상북도", "경상남도",
    "제주특별자치도",
]
_SHORT_TO_FULL = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시",
    "인천": "인천광역시", "광주": "광주광역시", "대전": "대전광역시",
    "울산": "울산광역시", "세종": "세종특별자치시", "경기": "경기도",
    "강원": "강원도", "충북": "충청북도", "충남": "충청남도",
    "전북": "전라북도", "전남": "전라남도", "경북": "경상북도",
    "경남": "경상남도", "제주": "제주특별자치도",
}


def _extract_city(inst_name: str | None) -> str:
    if not inst_name:
        return "기타"
    for full in _CITY_FULL:
        if full[:2] in inst_name:
            return full
    for short, full in _SHORT_TO_FULL.items():
        if short in inst_name:
            return full
    return "기타"


# ── 품목 카테고리 매핑 (키워드 기반) ──────────────────────────────────

_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("식품/급식", ["식품", "급식", "식자재", "식재료", "농산", "농축산", "수산", "가공식품", "쌀", "채소", "과일", "식사"]),
    ("의료/복지용품", ["의료", "복지", "의약", "의약품", "의료기기", "의료용품", "마스크", "장갑", "수술", "진단"]),
    ("위생/방역", ["방역", "소독", "해충", "방충", "살균", "방제"]),
    ("사무용품/문구", ["사무용품", "문구", "복사지", "사무소모품", "토너", "잉크", "사무기기"]),
    ("청소/환경", ["청소", "환경미화", "폐기물", "재활용", "쓰레기", "오물", "위생관리"]),
    ("전기/전자", ["전기", "전자", "전력", "조명", "LED", "컴퓨터", "PC", "프린터", "복합기", "배선"]),
    ("IT/소프트웨어", ["소프트웨어", "시스템", "정보화", "데이터", "플랫폼", "앱", "서버", "클라우드", "네트워크"]),
    ("시설유지보수", ["시설", "유지보수", "유지관리", "보수", "수리", "설비", "배관", "냉난방", "에어컨", "보일러", "도색"]),
    ("시설위탁/운영", ["위탁운영", "시설운영", "주차", "경비", "보안", "관리대행"]),
    ("교육/훈련", ["교육", "훈련", "연수", "강의", "학습", "교재", "교구", "세미나"]),
    ("출판/인쇄", ["출판", "인쇄", "도서", "책자", "간행물", "현수막", "홍보물", "책"]),
    ("행사/홍보", ["행사", "홍보", "이벤트", "축제", "박람회", "전시", "공연", "캠페인"]),
    ("운송/물류", ["운송", "물류", "배송", "택배", "운반", "이송", "화물"]),
    ("컨설팅/연구", ["컨설팅", "연구", "조사", "자문", "진단", "분석", "평가", "용역"]),
    ("농산물/원자재", ["원자재", "자재", "건축자재", "목재", "철재", "비료", "종자", "골재"]),
    ("건설/감리", ["건설", "공사", "감리", "건축", "토목", "신축", "증축", "리모델링"]),
    ("도시정비/재개발", ["정비", "재개발", "재건축", "도시정비"]),
]


def _assign_category(texts: list[str | None]) -> str:
    combined = " ".join(t for t in texts if t)
    for category, keywords in _CATEGORY_KEYWORDS:
        for kw in keywords:
            if kw in combined:
                return category
    return "기타"


# ── 발주계획 처리 ──────────────────────────────────────────────────────

def _process_plan(records: list[dict]) -> pd.DataFrame:
    """발주계획 레코드 → (city, item_category, plan_count, plan_amount_sum) 집계"""
    if not records:
        return pd.DataFrame(columns=["city", "item_category", "plan_count", "plan_amount_sum"])

    rows = []
    for r in records:
        # orderInsttNm에 "경상북도 포항시", "경기도교육청" 등 시/도 정보 포함
        inst = (
            r.get("orderInsttNm")
            or r.get("totlmngInsttNm")
            or r.get("rlDminsttNm")
            or r.get("dminsttNm")
            or ""
        )
        # 물품분류명 + 사업명으로 카테고리 매핑
        cat_text = [
            r.get("prdctClsfcNoNm"),
            r.get("dtilPrdctClsfcNoNm"),
            r.get("bizNm"),
            r.get("bsnsTyNm"),
        ]
        # 금액: sumOrderAmt (합계발주금액)
        try:
            amount = float(r.get("sumOrderAmt") or r.get("orderContrctAmt") or 0)
        except (ValueError, TypeError):
            amount = 0.0

        rows.append({
            "city": _extract_city(inst),
            "item_category": _assign_category(cat_text),
            "amount": amount,
        })

    df = pd.DataFrame(rows)
    agg = (
        df.groupby(["city", "item_category"])
        .agg(plan_count=("amount", "count"), plan_amount_sum=("amount", "sum"))
        .reset_index()
    )
    return agg


# ── MAS 대분류 → item_category 직접 매핑 ──────────────────────────────

_MAS_LRG_MAP: dict[str, str] = {
    "사무/교육/가구":       "사무용품/문구",
    "전기/전자/통신":       "전기/전자",
    "전기/기계/설비":       "전기/전자",
    "전자/정보/통신/영상":  "전기/전자",
    "소프트웨어/정보통신":  "IT/소프트웨어",
    "의료/보건/복지":       "의료/복지용품",
    "식품/음료/농수축산":   "식품/급식",
    "청소/환경/방역":       "청소/환경",
    "조경":                 "청소/환경",
    "시설/건설/안전":       "시설유지보수",
    "도로/철도/시설":       "시설유지보수",
    "인쇄/출판/홍보":       "출판/인쇄",
    "운반/교통/차량":       "운송/물류",
    "교육/연구/스포츠":     "교육/훈련",
    "위생/방역":            "위생/방역",
    "사무용품":             "사무용품/문구",
    "토목/건축/자재":       "농산물/원자재",
}


def _mas_category(r: dict) -> str:
    lrg = r.get("prdctLrgclsfcNm", "")
    for key, cat in _MAS_LRG_MAP.items():
        if key in lrg or lrg in key:
            return cat
    # fallback: 키워드 매핑
    mid = r.get("prdctMidclsfcNm", "")
    return _assign_category([lrg, mid, r.get("prdctClsfcNoNm")])


# ── MAS 품목 처리 ──────────────────────────────────────────────────────

def _process_shopping(records: list[dict]) -> pd.DataFrame:
    """
    MAS 품목 레코드 → (item_category, shopping_count, price_avg) 집계.

    MAS 계약은 전국 단위라 city 구분 없이 품목군별로 집계.
    """
    if not records:
        return pd.DataFrame(columns=["item_category", "shopping_count", "price_avg"])

    rows = []
    for r in records:
        try:
            price = float(r.get("cntrctPrceAmt") or 0)
        except (ValueError, TypeError):
            price = 0.0

        rows.append({
            "item_category": _mas_category(r),
            "price": price,
        })

    df = pd.DataFrame(rows)
    agg = (
        df.groupby("item_category")
        .agg(shopping_count=("price", "count"), price_avg=("price", "mean"))
        .reset_index()
    )
    agg["price_avg"] = agg["price_avg"].round(0)
    return agg


# ── 메인 ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="발주계획 + 종합쇼핑몰 납품요구 수집 및 집계")
    parser.add_argument("--months", type=int, default=6, help="발주계획 수집 기간 (개월, 기본 6)")
    parser.add_argument("--days", type=int, default=30, help="납품요구 수집 기간 (일, 기본 30)")
    parser.add_argument("--max-records", type=int, default=5000, dest="max_records",
                        help="MAS 품목 최대 수집 건수 (기본 5000)")
    parser.add_argument("--plan-only", action="store_true", help="발주계획만 수집")
    parser.add_argument("--shop-only", action="store_true", help="MAS 품목만 수집")
    args = parser.parse_args()

    run_plan = not args.shop_only
    run_shop = not args.plan_only

    # ── 발주계획 수집 ──────────────────────────────────────────────
    if run_plan:
        print(f"[collect_plan_data] 향후 {args.months}개월 발주계획 수집 중...")
        try:
            plan_records = collect_plan_all(months_ahead=args.months)
            print(f"  수집 완료: {len(plan_records):,}건")
            plan_df = _process_plan(plan_records)
            plan_path = OUTPUT_DIR / "procurement_plan_summary.csv"
            plan_df.to_csv(plan_path, index=False, encoding="utf-8-sig")
            total_amt = plan_df["plan_amount_sum"].sum()
            print(f"  집계 결과: {len(plan_df)}개 행 (도시 × 품목), 총 {total_amt/1e8:.1f}억원")
            print(f"  저장: {plan_path}")
        except PermissionError as e:
            print(f"  [오류] {e}", file=sys.stderr)
            print("  → API 승인 후 재실행하세요.", file=sys.stderr)
        except Exception as e:
            print(f"  [오류] 발주계획 수집 실패: {e}", file=sys.stderr)

    # ── MAS 품목 수집 ──────────────────────────────────────────────
    if run_shop:
        max_rec = getattr(args, "max_records", 5000)
        print(f"[collect_plan_data] 종합쇼핑몰 MAS 계약 품목 수집 중 (최대 {max_rec:,}건)...")
        try:
            shop_records = collect_mas_products(max_records=max_rec)
            print(f"  수집 완료: {len(shop_records):,}건")
            shop_df = _process_shopping(shop_records)
            shop_path = OUTPUT_DIR / "shopping_mall_summary.csv"
            shop_df.to_csv(shop_path, index=False, encoding="utf-8-sig")
            print(f"  집계 결과: {len(shop_df)}개 품목군")
            print(f"  저장: {shop_path}")
        except PermissionError as e:
            print(f"  [오류] {e}", file=sys.stderr)
            print("  → API 승인 후 재실행하세요.", file=sys.stderr)
        except Exception as e:
            print(f"  [오류] MAS 품목 수집 실패: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
