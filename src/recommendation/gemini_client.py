"""
Gemini API 연동: 공공수요 데이터 기반 설명형 문장 생성

사용법:
    from src.recommendation.gemini_client import build_demand_summary

    summary = build_demand_summary(
        district="강남구",
        item_category="시설유지보수",
        bid_count=122,
        amount_sum=26988893600,
        opportunity_score=71.63,
        consumer_fit_score=0.98,
        stores_per_10k=None,
        recommendation_flag="추천",
    )
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

_PLAN_CSV = Path("outputs/tables/procurement_plan_summary.csv")
_SHOP_CSV = Path("outputs/tables/shopping_mall_summary.csv")


@lru_cache(maxsize=1)
def _load_plan_df() -> pd.DataFrame:
    if _PLAN_CSV.exists():
        return pd.read_csv(_PLAN_CSV)
    return pd.DataFrame()


@lru_cache(maxsize=1)
def _load_shop_df() -> pd.DataFrame:
    if _SHOP_CSV.exists():
        return pd.read_csv(_SHOP_CSV)
    return pd.DataFrame()


def _lookup_plan(city: str, item_category: str) -> tuple[int, float]:
    """발주계획 집계 CSV에서 (건수, 금액합계) 반환. 없으면 (0, 0)."""
    df = _load_plan_df()
    if df.empty:
        return 0, 0.0
    row = df[(df["city"] == city) & (df["item_category"] == item_category)]
    if row.empty:
        return 0, 0.0
    return int(row["plan_count"].iloc[0]), float(row["plan_amount_sum"].iloc[0])


def _lookup_shop(city: str, item_category: str) -> tuple[int, float]:
    """MAS 품목 집계 CSV에서 (품목수, 평균단가) 반환. MAS는 전국 단위라 city 무시."""
    df = _load_shop_df()
    if df.empty:
        return 0, 0.0
    row = df[df["item_category"] == item_category]
    if row.empty:
        return 0, 0.0
    cnt = int(row["shopping_count"].iloc[0])
    price_avg = float(row.get("price_avg", pd.Series([0])).iloc[0]) if "price_avg" in row.columns else 0.0
    return cnt, price_avg

# ── 추천 정책 상수 ─────────────────────────────────────────────────
_STATIC_MESSAGES = {
    "제외": (
        "⛔ **추천 제외 항목**\n\n"
        "이 품목군은 공공수요 규모는 있으나, "
        "사업 영위에 전문 허가·면허·장비 요건이 필요한 업종입니다. "
        "일반 예비창업자 대상 추천에서는 제외됩니다. "
        "관련 자격을 보유한 경우에는 공고 건수와 금액 규모를 참고하세요."
    ),
    "데이터부족": (
        "🟡 **데이터 부족**\n\n"
        "수집 기간 내 공고 건수가 10건 미만입니다. "
        "현재 데이터만으로는 안정적인 수요 패턴을 파악하기 어렵습니다. "
        "수집 범위(자치구·기간)를 확장하면 더 정확한 해석이 가능합니다."
    ),
}

_SYSTEM_INSTRUCTION = """당신은 공공조달 입찰공고 데이터를 분석하는 냉정한 데이터 분석가입니다.
상담가처럼 좋게만 말하지 않습니다. 수치가 나쁘면 나쁘다고 말합니다.

반드시 지켜야 할 규칙:
- 첫 줄에 반드시 다음 셋 중 하나로 시작: 📊 수요 있음 / ⚠️ 수요 미약 / 🔍 판단 어려움
- 창업 성공을 예측하거나 보장하는 표현 절대 금지
- "유망합니다", "좋은 기회입니다", "진입 검토해볼 만합니다" 같은 막연한 긍정 표현 금지
- 수치가 낮으면 낮다고, 경쟁이 많으면 많다고 사실대로 기술
- 수치는 반드시 제공된 숫자를 그대로 인용 (임의 생성 금지)
- 2~3문장, 한국어
- 마지막 문장: "이 수치는 공공조달 참고 지표이며 창업 성공을 보장하지 않습니다." 필수"""

_USER_TEMPLATE = """다음은 {city} {district}의 공공조달 수요 데이터입니다.

품목군: {item_category}
- 최근 2년 공고 건수: {bid_count}건  [출처: 나라장터 입찰공고]
- 총 발주 추정 금액: {amount_sum_str}  [출처: 나라장터 추정가격]
- 공공수요 점수: {opportunity_score:.1f}점 (100점 만점, 공고수40%·금액25%·최근성15%·경쟁도20% 가중합)
- 소비층 적합도: {consumer_fit_str}  [출처: 행정안전부 연령별 인구]
- 시장 개방도: {competition_str}  [출처: 나라장터 입찰방식]
{stores_line}{confidence_line}{plan_line}{shop_line}
위 데이터를 바탕으로 이 품목군의 공공조달 수요 특성을 설명해주세요.
창업 성공 여부가 아닌, 공공기관의 발주 패턴과 수요 규모 관점에서 서술하세요.
제공된 수치만 인용하고, 수치에 없는 내용은 추측하지 마세요."""


@dataclass
class DemandContext:
    district: str
    item_category: str
    bid_count: int
    amount_sum: float
    opportunity_score: float
    recommendation_flag: str
    city: str = "서울특별시"
    consumer_fit_score: float | None = None
    stores_per_10k: float | None = None
    competition_score: float | None = None  # 개방경쟁 비율 (0~1)
    demand_confidence_score: float | None = None  # 공고+낙찰 2단 수요 신뢰도 (0~1, 학교급식 분야)
    plan_count: int | None = None          # 향후 발주계획 건수 (수집 후 자동주입)
    plan_amount: float | None = None       # 향후 발주계획 금액합계
    shopping_count: int | None = None      # 최근 종합쇼핑몰 납품요구 건수
    shopping_amount: float | None = None   # 최근 종합쇼핑몰 납품요구 금액합계


def _format_amount(amount: float) -> str:
    if amount >= 1_000_000_000:
        return f"약 {amount / 1_000_000_000:.1f}억 원"
    if amount >= 1_000_000:
        return f"약 {amount / 1_000_000:.0f}만 원"
    return f"{int(amount):,}원"


def build_demand_summary(ctx: DemandContext) -> str:
    """
    DemandContext를 받아 Gemini 생성 문장 또는 정책 안내 문구를 반환합니다.

    recommendation_flag가 '추천'이 아닐 경우 정적 문구를 반환하며 API를 호출하지 않습니다.
    GEMINI_API_KEY가 없으면 폴백 문구를 반환합니다.
    """
    if ctx.recommendation_flag != "추천":
        return _STATIC_MESSAGES.get(ctx.recommendation_flag, "해석 정보 없음")

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return _fallback_summary(ctx)

    try:
        from google import genai
        from google.genai import types
        import time

        client = genai.Client(api_key=api_key)

        consumer_fit_str = (
            f"{ctx.consumer_fit_score:.2f} (0~1, 해당 품목 주소비층 인구 비중)"
            if ctx.consumer_fit_score is not None
            else "데이터 없음"
        )
        stores_line = (
            f"- 인구 1만명당 유사 업종 점포 수: {ctx.stores_per_10k:.1f}개  [출처: 소상공인 상가정보]\n"
            if ctx.stores_per_10k is not None
            else ""
        )
        if ctx.competition_score is not None:
            pct = ctx.competition_score * 100
            competition_str = f"{pct:.0f}% (같은 품목군 내 공고수 역백분위, 높을수록 기존 납품사 적음 = 진입 용이)"
        else:
            competition_str = "데이터 없음"

        confidence_line = (
            f"- 수요 신뢰도: {ctx.demand_confidence_score:.2f} (공고=의사 0.5 + 낙찰건수=실측 0.3 + 낙찰금액 0.2, 출처: aT 학교급식)\n"
            if ctx.demand_confidence_score is not None
            else ""
        )

        # 발주계획 — ctx에 직접 세팅된 값 우선, 없으면 CSV 자동 조회
        plan_cnt = ctx.plan_count
        plan_amt = ctx.plan_amount
        if plan_cnt is None:
            plan_cnt, plan_amt = _lookup_plan(ctx.city, ctx.item_category)
        plan_line = (
            f"- 향후 6개월 발주계획: {plan_cnt}건"
            + (f" ({_format_amount(plan_amt)})" if plan_amt else "")
            + "  [출처: 나라장터 발주계획]\n"
            if plan_cnt and plan_cnt > 0
            else ""
        )

        # 종합쇼핑몰 납품요구
        shop_cnt = ctx.shopping_count
        shop_amt = ctx.shopping_amount
        if shop_cnt is None:
            shop_cnt, shop_amt = _lookup_shop(ctx.city, ctx.item_category)
        shop_line = (
            f"- 종합쇼핑몰 MAS 등록 품목 수: {shop_cnt}건"
            + (f" (평균단가 {_format_amount(shop_amt)})" if shop_amt and shop_amt > 0 else "")
            + "  [출처: 나라장터 다수공급자계약]\n"
            if shop_cnt and shop_cnt > 0
            else ""
        )

        prompt = _USER_TEMPLATE.format(
            city=ctx.city,
            district=ctx.district,
            item_category=ctx.item_category,
            bid_count=ctx.bid_count,
            amount_sum_str=_format_amount(ctx.amount_sum),
            opportunity_score=ctx.opportunity_score,
            consumer_fit_str=consumer_fit_str,
            competition_str=competition_str,
            stores_line=stores_line,
            confidence_line=confidence_line,
            plan_line=plan_line,
            shop_line=shop_line,
        )

        last_error = None
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model="gemini-3.1-flash-lite",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=_SYSTEM_INSTRUCTION,
                        max_output_tokens=300,
                        temperature=0.3,
                    ),
                )
                text = ""
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "text") and part.text:
                        text += part.text
                if text.strip():
                    return text.strip()
            except Exception as e:
                last_error = e
                if "503" in str(e) and attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                break

        return _fallback_summary(ctx, error=str(last_error) if last_error else "")

    except Exception as e:
        return _fallback_summary(ctx, error=str(e))


@dataclass
class ShortageContext:
    city: str
    district: str
    district_profile: str
    shortage_items: list[str]
    total_bids_in_district: int
    same_city_comparison: list[dict]  # [{item, avg_count, districts_with_data, total_districts}]


_SHORTAGE_SYSTEM = """당신은 공공조달 입찰공고 데이터 패턴을 분석하는 전문 분석가입니다.
수치를 비교해 블루오션(숨은 수요)인지 실제 저수요인지 해석합니다.

반드시 지켜야 할 규칙:
- 판정 결과를 첫 문장에 명확히 제시 (블루오션 가능성 높음 / 저수요 가능성 높음 / 판단 어려움)
- 판정 근거는 반드시 제공된 수치를 인용
- 창업 성공 보장 표현 금지
- 3~5문장, 한국어"""

_SHORTAGE_TEMPLATE = """{city} {district}({district_profile})의 데이터부족 품목 진단

현황:
- 해당 지역 전체 공고 수: {total_bids}건
- 데이터부족 품목 {n_items}개: {items_list}

같은 {city} 내 비교 데이터:
{comparison_lines}

위 수치를 비교 분석해 이 지역의 데이터부족이 다음 중 어느 쪽에 가까운지 판정하세요:
- 블루오션: 수요는 있지만 소액 수의계약·직접구매로 처리되어 공개 입찰에 미등록
- 실제 저수요: 해당 지역 공공기관 수요 자체가 낮음

판정 후, 이 지역에서 해당 품목 진입을 고려하는 창업자에게 다음 행동을 구체적으로 제안하세요."""


def build_shortage_verdict(ctx: ShortageContext) -> str:
    """데이터부족 품목이 블루오션인지 실제 저수요인지 AI 판정 반환"""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return _shortage_fallback(ctx)

    try:
        from google import genai
        from google.genai import types
        import time

        comparison_lines = "\n".join(
            f"- {c['item']}: {c['city']} 내 평균 {c['avg_count']:.0f}건 "
            f"({c['districts_with_data']}/{c['total_districts']}개 지역 데이터 있음)"
            for c in ctx.same_city_comparison
        )

        prompt = _SHORTAGE_TEMPLATE.format(
            city=ctx.city,
            district=ctx.district,
            district_profile=ctx.district_profile,
            total_bids=ctx.total_bids_in_district,
            n_items=len(ctx.shortage_items),
            items_list=", ".join(ctx.shortage_items),
            comparison_lines=comparison_lines or "비교 데이터 없음",
        )

        client = genai.Client(api_key=api_key)
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model="gemini-3.1-flash-lite",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=_SHORTAGE_SYSTEM,
                        max_output_tokens=400,
                        temperature=0.2,
                    ),
                )
                text = "".join(
                    part.text for part in response.candidates[0].content.parts
                    if hasattr(part, "text") and part.text
                )
                if text.strip():
                    return text.strip()
            except Exception as e:
                if "503" in str(e) and attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                return _shortage_fallback(ctx, error=str(e))

    except Exception as e:
        return _shortage_fallback(ctx, error=str(e))

    return _shortage_fallback(ctx)


@dataclass
class OverdemandContext:
    city: str
    district: str
    district_profile: str
    hot_items: list[dict]        # [{item, bid_count, opportunity_score, competition_score, avg_lead_time_days}]
    city_avg_bid_count: float    # 같은 시/도 전체 평균 공고 수
    city_max_bid_count: float    # 같은 시/도 최대 공고 수


_OVERDEMAND_SYSTEM = """당신은 공공조달 시장 경쟁 구조를 분석하는 냉정한 분석가입니다.
좋게 봐주지 않습니다. 수치가 불리하면 불리하다고 명시합니다.

반드시 지켜야 할 규칙:
- 첫 줄에 반드시 다음 셋 중 하나로 시작: 🔴 진입 주의 / 🟡 조건부 검토 / 🟢 진입 여지 있음
- 기본값은 🔴 진입 주의입니다. 🟢는 competition_score가 0.6 이상이고 bid_count가 시/도 평균의 2배 미만일 때만 가능합니다.
- competition_score와 bid_count를 반드시 수치로 인용
- 진입 주의: 기존 납품사 점유 / 규모 격차 / 장벽 등 구체 근거 명시
- 조건부: 어떤 조건에서만 가능한지 한정적으로 기술
- 4~6문장, 한국어"""

_OVERDEMAND_TEMPLATE = """{city} {district}({district_profile}) 고수요 품목 진입 가능성 진단

데이터:
- {city} 지역 평균 공고 수: {city_avg:.0f}건 / 최대: {city_max:.0f}건
- 분석 품목:
{items_lines}

판단 기준:
- competition_score < 0.4: 기존 납품사 포화 → 신규 진입 매우 어려움
- competition_score 0.4~0.6: 진입 여지 일부 있으나 경쟁 있음
- competition_score > 0.6: 기존 납품사 적음 → 진입 여지 있음
- bid_count가 지역 평균 3배 이상: 수요 집중 = 이미 공급자 고착 가능성

각 품목에 대해 🔴/🟡/🟢 판정을 내리고, 진입 주의 판정이 나온 품목은 그 이유를 구체적으로 명시하세요.
데이터 없이 낙관적 해석을 하지 마세요."""


def build_overdemand_verdict(ctx: OverdemandContext) -> str:
    """고수요 품목이 레드오션인지 진입 여지가 있는지 AI 판정 반환"""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return _overdemand_fallback(ctx)

    try:
        from google import genai
        from google.genai import types
        import time

        items_lines = "\n".join(
            f"- {h['item']}: 공고 {h['bid_count']}건, "
            f"진입용이도 {h['competition_score']*100:.0f}%(높을수록 기존납품사 적음), "
            f"기회점수 {h['opportunity_score']:.1f}점"
            for h in ctx.hot_items
        )

        prompt = _OVERDEMAND_TEMPLATE.format(
            city=ctx.city,
            district=ctx.district,
            district_profile=ctx.district_profile,
            city_avg=ctx.city_avg_bid_count,
            city_max=ctx.city_max_bid_count,
            items_lines=items_lines,
        )

        client = genai.Client(api_key=api_key)
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model="gemini-3.1-flash-lite",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=_OVERDEMAND_SYSTEM,
                        max_output_tokens=400,
                        temperature=0.2,
                    ),
                )
                text = "".join(
                    part.text for part in response.candidates[0].content.parts
                    if hasattr(part, "text") and part.text
                )
                if text.strip():
                    return text.strip()
            except Exception as e:
                if "503" in str(e) and attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                return _overdemand_fallback(ctx, error=str(e))

    except Exception as e:
        return _overdemand_fallback(ctx, error=str(e))

    return _overdemand_fallback(ctx)


def _overdemand_fallback(ctx: OverdemandContext, error: str = "") -> str:
    lines = [f"**{ctx.district} 고수요 품목 간이 진단**"]
    for h in ctx.hot_items:
        comp = h["competition_score"]
        verdict = "🟢 진입 검토" if comp >= 0.7 else ("🔴 진입 주의" if comp < 0.4 else "🟡 조건부 검토")
        lines.append(
            f"- **{h['item']}**: 공고 {h['bid_count']}건, 개방경쟁 {comp*100:.0f}% → {verdict}"
        )
    if error:
        lines.append(f"_(AI 해석 실패: {error[:60]})_")
    return "\n".join(lines)


@dataclass
class HubStrategyContext:
    hub_candidates: list[dict]   # [{city, zone, physical_bids, physical_amount, top_categories, hub_score}]
    national_total_bids: int
    national_total_amount: float


_HUB_SYSTEM = """당신은 공공조달 물류 네트워크 전략가입니다.
전국 공공수요 데이터를 분석해 최적 물류 거점 전략을 제안합니다.

반드시 지켜야 할 규칙:
- 1·2·3티어 허브 구조로 제안 (전국 거점 / 권역 거점 / 보조 거점)
- 각 거점 선정 근거를 수치로 명시
- 어떤 품목 흐름이 해당 거점을 정당화하는지 설명
- 물류 실무자가 바로 활용할 수 있는 수준으로 구체적으로
- 5~8문장, 한국어"""

_HUB_TEMPLATE = """전국 공공조달 물리적 납품 수요 데이터 기반 물류 거점 전략 분석

전국 현황:
- 총 물리적 납품 공고: {national_bids}건
- 총 발주 금액: {national_amount}

권역별 허브 후보 (허브점수 순):
{candidates_lines}

위 데이터를 바탕으로:
1. 전국 공공조달 납품을 커버할 최적 1·2·3티어 물류 허브 구조를 제안하세요.
2. 각 거점이 담당해야 할 품목 흐름과 커버 권역을 명시하세요.
3. 물류 스타트업이나 중소 납품업체 입장에서 첫 거점으로 어디를 선택해야 하는지 결론을 내리세요."""


def build_hub_strategy(ctx: HubStrategyContext) -> str:
    """전국 공공수요 기반 최적 물류 거점 전략 AI 분석"""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return _hub_fallback(ctx)

    try:
        from google import genai
        from google.genai import types
        import time

        candidates_lines = "\n".join(
            f"- {c['city']}({c['zone']}): 허브점수 {c['hub_score']:.1f}, "
            f"물리적 공고 {c['physical_bids']:,}건, "
            f"금액 {_format_amount(c['physical_amount'])}, "
            f"주요품목: {', '.join(c['top_categories'][:3])}"
            for c in ctx.hub_candidates[:8]
        )

        prompt = _HUB_TEMPLATE.format(
            national_bids=f"{ctx.national_total_bids:,}",
            national_amount=_format_amount(ctx.national_total_amount),
            candidates_lines=candidates_lines,
        )

        client = genai.Client(api_key=api_key)
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model="gemini-3.1-flash-lite",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=_HUB_SYSTEM,
                        max_output_tokens=600,
                        temperature=0.3,
                    ),
                )
                text = "".join(
                    part.text for part in response.candidates[0].content.parts
                    if hasattr(part, "text") and part.text
                )
                if text.strip():
                    return text.strip()
            except Exception as e:
                if "503" in str(e) and attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                return _hub_fallback(ctx, error=str(e))

    except Exception as e:
        return _hub_fallback(ctx, error=str(e))

    return _hub_fallback(ctx)


def _hub_fallback(ctx: HubStrategyContext, error: str = "") -> str:
    top3 = ctx.hub_candidates[:3]
    lines = ["**물류 거점 간이 추천 (AI 분석 대체)**"]
    tiers = ["1티어 (전국 거점)", "2티어 (권역 거점)", "3티어 (보조 거점)"]
    for tier, c in zip(tiers, top3):
        lines.append(f"- **{tier}**: {c['city']} — 물리적 공고 {c['physical_bids']:,}건, 주요 품목: {', '.join(c['top_categories'][:2])}")
    if error:
        lines.append(f"_(AI 분석 실패: {error[:60]})_")
    return "\n".join(lines)


def _shortage_fallback(ctx: ShortageContext, error: str = "") -> str:
    has_nearby = any(c["districts_with_data"] > 0 for c in ctx.same_city_comparison)
    verdict = "블루오션 가능성 있음" if has_nearby else "추가 현장 조사 필요"
    lines = [
        f"**{ctx.district} 데이터부족 품목 ({len(ctx.shortage_items)}개) 간이 진단**",
        f"판정: **{verdict}**",
    ]
    for c in ctx.same_city_comparison[:3]:
        lines.append(
            f"- {c['item']}: 동일 시/도 내 {c['districts_with_data']}/{c['total_districts']}개 지역 데이터 있음 "
            f"(평균 {c['avg_count']:.0f}건)"
        )
    if error:
        lines.append(f"_(AI 해석 실패: {error[:60]})_")
    return "\n".join(lines)


def _fallback_summary(ctx: DemandContext, error: str = "") -> str:
    """API 키 없거나 오류 시 수치 기반 정적 문구 반환"""
    amount_str = _format_amount(ctx.amount_sum)
    region_label = f"{ctx.city} {ctx.district}" if ctx.city and ctx.city not in ctx.district else ctx.district
    lines = [
        f"최근 2년간 {region_label}에서 **{ctx.item_category}** 관련 공고가 {ctx.bid_count}건 발생했으며, "
        f"총 발주 추정 금액은 {amount_str}입니다.",
        f"공공수요 점수는 {ctx.opportunity_score:.1f}점으로, "
        f"공고 수·금액 규모·최근성·경쟁도를 종합한 참고 지표입니다.",
    ]
    if ctx.demand_confidence_score is not None:
        lines.append(
            f"aT 학교급식 낙찰 데이터 기반 수요 신뢰도는 {ctx.demand_confidence_score:.2f}로, "
            f"공고(의사)와 실제 계약(실측)을 함께 반영한 지표입니다."
        )
    lines.append("이 수치는 공공조달 참고 지표이며 창업 성공을 보장하지 않습니다.")
    if error:
        lines.append(f"_(AI 해석 생성 실패: {error[:60]})_")
    return " ".join(lines)


# ── 지역 비교 AI 분석 ──────────────────────────────────────────────

_COMPARE_SYSTEM = """당신은 공공조달 입찰공고 데이터를 분석하는 중립적인 데이터 해석가입니다.
두 지역의 공공조달 수요 포트폴리오를 비교해 예비창업자·납품업체가 참고할 수 있는 설명을 제공합니다.

반드시 지켜야 할 규칙:
- 창업 성공을 예측하거나 보장하는 표현 금지
- "유망합니다", "추천합니다" 같은 판단형 표현 금지
- 두 지역의 수요 구조 차이를 수치 중심으로 설명
- 4~6문장, 한국어로 간결하게
- 어느 지역이 어떤 품목군에 집중되어 있는지 구체적으로 언급"""

_COMPARE_TEMPLATE = """두 지역의 공공조달 수요 포트폴리오 비교입니다.

[{label_a}]
{items_a}

[{label_b}]
{items_b}

A 지역이 우세한 품목군: {dominant_a}
B 지역이 우세한 품목군: {dominant_b}

위 데이터를 바탕으로 두 지역의 공공조달 수요 구조 차이를 설명해주세요.
어떤 지역이 어떤 품목군에 수요가 집중되어 있는지, 두 지역의 포트폴리오 특성 차이를 중심으로 서술하세요."""


@dataclass
class CompareContext:
    dist_a: str
    dist_b: str
    city_a: str
    city_b: str
    items_a: list[dict]   # [{"item": str, "bid_count": int, "score": float}]
    items_b: list[dict]
    dominant_a: list[str]  # A가 우세한 품목군
    dominant_b: list[str]  # B가 우세한 품목군


def build_compare_summary(ctx: CompareContext) -> str:
    """두 지역 공공조달 수요 포트폴리오 비교 AI 설명"""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return _compare_fallback(ctx)

    def _fmt_items(items: list[dict]) -> str:
        return "\n".join(
            f"  - {d['item']}: {d['bid_count']}건, 수요점수 {d['score']:.1f}"
            for d in items[:6]
        )

    label_a = f"{ctx.city_a} {ctx.dist_a}" if ctx.city_a else ctx.dist_a
    label_b = f"{ctx.city_b} {ctx.dist_b}" if ctx.city_b else ctx.dist_b

    prompt = _COMPARE_TEMPLATE.format(
        label_a=label_a,
        label_b=label_b,
        items_a=_fmt_items(ctx.items_a),
        items_b=_fmt_items(ctx.items_b),
        dominant_a=", ".join(ctx.dominant_a[:4]) or "없음",
        dominant_b=", ".join(ctx.dominant_b[:4]) or "없음",
    )

    try:
        from google import genai
        from google.genai import types
        import time

        client = genai.Client(api_key=api_key)
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model="gemini-3.1-flash-lite",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=_COMPARE_SYSTEM,
                        max_output_tokens=400,
                        temperature=0.3,
                    ),
                )
                text = "".join(
                    part.text for part in response.candidates[0].content.parts
                    if hasattr(part, "text") and part.text
                )
                if text.strip():
                    return text.strip()
            except Exception as e:
                if "503" in str(e) and attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                return _compare_fallback(ctx, error=str(e))

    except Exception as e:
        return _compare_fallback(ctx, error=str(e))

    return _compare_fallback(ctx)


def _compare_fallback(ctx: CompareContext, error: str = "") -> str:
    label_a = f"{ctx.city_a} {ctx.dist_a}" if ctx.city_a else ctx.dist_a
    label_b = f"{ctx.city_b} {ctx.dist_b}" if ctx.city_b else ctx.dist_b
    lines = [f"**{label_a} vs {label_b} 수요 포트폴리오 비교**"]
    if ctx.dominant_a:
        lines.append(f"- {label_a} 우세 품목: {', '.join(ctx.dominant_a[:3])}")
    if ctx.dominant_b:
        lines.append(f"- {label_b} 우세 품목: {', '.join(ctx.dominant_b[:3])}")
    top_a = ctx.items_a[0] if ctx.items_a else None
    top_b = ctx.items_b[0] if ctx.items_b else None
    if top_a:
        lines.append(f"- {label_a} 최다 수요: {top_a['item']} ({top_a['bid_count']}건)")
    if top_b:
        lines.append(f"- {label_b} 최다 수요: {top_b['item']} ({top_b['bid_count']}건)")
    if error:
        lines.append(f"_(AI 분석 실패: {error[:60]})_")
    return "\n".join(lines)
