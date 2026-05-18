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

from dotenv import load_dotenv

load_dotenv()

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

_SYSTEM_INSTRUCTION = """당신은 공공조달 입찰공고 데이터를 분석하는 중립적인 데이터 해석가입니다.
예비창업자가 공공수요 신호를 이해할 수 있도록 데이터를 설명합니다.

반드시 지켜야 할 규칙:
- 창업 성공을 예측하거나 보장하는 표현 금지
- "유망합니다", "추천합니다", "좋은 기회입니다" 같은 판단형 표현 금지
- "~건의 공고가 있었습니다", "~를 의미할 수 있습니다", "참고 지표로 활용하세요" 같은 설명형 표현 사용
- 2~3문장, 한국어로 간결하게
- 수치는 구체적으로 언급"""

_USER_TEMPLATE = """다음은 {city} {district}의 공공조달 수요 데이터입니다.

품목군: {item_category}
- 최근 2년 공고 건수: {bid_count}건
- 총 발주 추정 금액: {amount_sum_str}
- 공공수요 점수: {opportunity_score:.1f}점 (100점 만점, 공고수·금액·최근성·경쟁도 종합)
- 소비층 적합도: {consumer_fit_str}
- 시장 개방도: {competition_str}
{stores_line}
위 데이터를 바탕으로 이 품목군의 공공조달 수요 특성을 설명해주세요.
창업 성공 여부가 아닌, 공공기관의 발주 패턴과 수요 규모 관점에서 서술하세요."""


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
            f"- 인구 1만명당 유사 업종 점포 수: {ctx.stores_per_10k:.1f}개\n"
            if ctx.stores_per_10k is not None
            else ""
        )
        if ctx.competition_score is not None:
            pct = ctx.competition_score * 100
            competition_str = f"{pct:.0f}% (지명경쟁 제외 개방입찰 비율, 높을수록 신규진입 용이)"
        else:
            competition_str = "데이터 없음"

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


_OVERDEMAND_SYSTEM = """당신은 공공조달 시장 경쟁 구조를 분석하는 전문 분석가입니다.
수요가 높은 품목의 진입 조건을 3단계로 해석합니다.

반드시 지켜야 할 규칙:
- 첫 줄에 반드시 다음 셋 중 하나로 시작: 🔴 진입 주의 / 🟡 조건부 검토 / 🟢 진입 검토
- competition_score(개방경쟁 비율)와 bid_count를 반드시 수치로 인용
- 진입 주의 시: 구체적인 이유(기존 지명업체 고착, 대형 납품사 독점 등)를 명시
- 조건부·검토 시: 틈새 전략 또는 차별화 포인트 제시
- 창업 성공 보장 표현 금지 (데이터 기반 해석임을 명시)
- 4~6문장, 한국어"""

_OVERDEMAND_TEMPLATE = """{city} {district}({district_profile}) 고수요 품목 경쟁 구조 해석

현황:
- 같은 {city} 내 지역 평균 공고 수: {city_avg:.0f}건
- 이 지역 고수요 품목 데이터:
{items_lines}

해석 기준 참고:
- competition_score < 0.4 → 기존 지명업체 위주, 신규 진입 어려움
- competition_score 0.4~0.7 → 부분 개방, 틈새 진입 가능
- competition_score > 0.7 → 개방경쟁, 신규 진입 여지 있음
- bid_count가 시/도 평균 대비 5배 이상 → 수요 집중 = 경쟁도 높음 가능성

위 데이터를 해석해:
1. 🔴/🟡/🟢 3단계 진입 조건을 명확히 제시하세요.
2. 진입 주의라면 왜 어려운지 구체적 근거를 대세요.
3. 조건부·검토라면 어떤 방식으로 접근해야 하는지 실질적 전략을 제시하세요."""


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
            f"- {h['item']}: 공고 {h['bid_count']}건 (시/도 최대 {ctx.city_max_bid_count:.0f}건), "
            f"개방경쟁 {h['competition_score']*100:.0f}%, "
            f"평균 집행일 {h.get('avg_lead_time_days', '?')}일"
            for h in ctx.hot_items
        )

        prompt = _OVERDEMAND_TEMPLATE.format(
            city=ctx.city,
            district=ctx.district,
            district_profile=ctx.district_profile,
            city_avg=ctx.city_avg_bid_count,
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
