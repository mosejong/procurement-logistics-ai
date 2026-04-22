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

_USER_TEMPLATE = """다음은 서울 {district} 자치구의 공공조달 수요 데이터입니다.

품목군: {item_category}
- 최근 2년 공고 건수: {bid_count}건
- 총 발주 추정 금액: {amount_sum_str}
- 공공수요 점수: {opportunity_score:.1f}점 (100점 만점, 공고수·금액·최근성 종합)
- 소비층 적합도: {consumer_fit_str}
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
    consumer_fit_score: float | None = None
    stores_per_10k: float | None = None


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

        prompt = _USER_TEMPLATE.format(
            district=ctx.district,
            item_category=ctx.item_category,
            bid_count=ctx.bid_count,
            amount_sum_str=_format_amount(ctx.amount_sum),
            opportunity_score=ctx.opportunity_score,
            consumer_fit_str=consumer_fit_str,
            stores_line=stores_line,
        )

        last_error = None
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model="models/gemini-3.1-flash-lite-preview",
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


def _fallback_summary(ctx: DemandContext, error: str = "") -> str:
    """API 키 없거나 오류 시 수치 기반 정적 문구 반환"""
    amount_str = _format_amount(ctx.amount_sum)
    lines = [
        f"최근 2년간 {ctx.district}에서 **{ctx.item_category}** 관련 공고가 {ctx.bid_count}건 발생했으며, "
        f"총 발주 추정 금액은 {amount_str}입니다.",
        f"공공수요 점수는 {ctx.opportunity_score:.1f}점으로, "
        f"공고 수·금액 규모·최근성을 종합한 참고 지표입니다.",
    ]
    if error:
        lines.append(f"_(AI 해석 생성 실패: {error[:60]})_")
    return " ".join(lines)
