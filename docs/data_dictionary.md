# 데이터 사전

원천 API의 컬럼명은 공고 유형에 따라 달라질 수 있으므로, 전처리 단계에서 아래 표준 컬럼으로 변환합니다.

## 데이터 소스 현황 (6개 기관)

| # | 데이터 | 기관 | 활용 지표 | 상태 |
|---|---|---|---|---|
| 1 | 나라장터 입찰공고 | 조달청(필수) | count_score, amount_score, recency_score, competition_score | ✅ |
| 2 | 연령별 주민등록 인구 | 행정안전부 | consumer_fit_score (소비층 적합도) | ✅ |
| 3 | 소상공인 상가정보 | 소상공인진흥공단 | competition_score (점포 경쟁 밀도) | ✅ |
| 4 | 신생기업 생존율 | KOSIS(통계청) | adjusted_score (리스크 보정) | ✅ |
| 5 | 학교급식 입찰·낙찰현황 | aT(농수산물유통공사) | demand_confidence_score (수요 신뢰도) | ✅ (전 연도 수집) |
| 6 | 물류창고업 등록정보 | 국토교통부 | logistics_infra_score (물류 인프라) | ✅ |

## 표준 컬럼

| 표준 컬럼 | 설명 | 예시 |
|---|---|---|
| `bid_title` | 입찰 공고명 또는 사업명 | 급식 식자재 구매 |
| `agency_name` | 수요기관명 | 부산광역시 해운대구청 |
| `region` | 시도 단위 지역명 | 부산 |
| `district` | 시군구명 | 해운대구 |
| `posted_date` | 공고일 | 2024-11-15 |
| `estimated_amount` | 추정가격 또는 배정예산 | 210000000 |
| `item_text` | 품목 분류와 검색에 사용할 텍스트 | 공고명 + 기관명 + 구매품목 |
| `item_category` | 공고명 기반 품목군 (18개) | 급식·식자재 |

## 핵심 분석 테이블 (지역 × 품목군 매트릭스)

| 컬럼 | 설명 | 예시 |
|---|---|---|
| `district` | 시군구 | 해운대구 |
| `item_category` | 품목군 | 급식·식자재 |
| `bid_count` | 해당 지역·품목군 공고 수 | 62 |
| `amount_sum` | 추정금액 합계 | 2100000000 |
| `amount_mean` | 평균 추정금액 | 33870968 |
| `latest_posted_date` | 가장 최근 공고일 | 2024-11-15 |
| `count_score` | 공고 수 정규화 (0~1) | 0.85 |
| `amount_score` | 금액 정규화 (0~1) | 0.78 |
| `recency_score` | 최근성 점수 (30일 감쇠) | 0.62 |
| `competition_score` | 개방입찰 비율 (0~1) | 0.90 |
| `opportunity_score` | 공공수요 기회점수 (0~100) | 29.7 |

## 점수 산식

### opportunity_score (공공수요 기회점수)
```
opportunity_score =
    count_score × 0.40
  + amount_score × 0.25
  + recency_score × 0.15
  + competition_score × 0.20
```
> 가중치 근거: 반복 발주(40%)가 지속 수요의 가장 강한 신호. 금액(25%)은 시장 규모 반영이나 대형 1건 왜곡 제한. 최근성(15%)은 현재 수요 유효성 보정. 경쟁도(20%)는 신규 진입 가능성.

### adjusted_score (생존율 보정 점수)
```
adjusted_score = opportunity_score × (survival_5y / 100) × (1 − dissolution_rate)
```
> KOSIS 신생기업 5년 생존율로 업종 리스크 하향 보정.

### demand_confidence_score (수요 신뢰도) — 학교급식 분야
```
demand_confidence_score =
    0.5 × normalized(notice_count)     ← 공고 수 = 공공기관 구매 의향
  + 0.3 × normalized(award_count)      ← 낙찰 건수 = 실제 구매 확정
  + 0.2 × normalized(award_amount_sum) ← 낙찰 금액 = 실제 시장 규모
```
> 공고=의사 / 계약=실측 2단 구조. aT 학교급식 낙찰·계약현황(전 연도)으로 실측 레이어 구현.

### logistics_infra_score (물류 인프라 점수)
```
logistics_infra_score =
    0.5 × normalized(warehouse_count)
  + 0.3 × normalized(warehouse_area_sum)
  + 0.2 × normalized(cold_storage_count)
```
> 국토부 물류창고업 등록정보 기반. 수요 집중지(hub_score) + 창고 인프라(logistics_infra_score) 결합으로 물류 거점 판단.

## 집계 기준 정의 (수치 정합성)

> 발표 및 기획서에서 사용하는 모든 수치의 집계 단위

| 수치 | 집계 기준 | 비고 |
|---|---|---|
| 10만건 | 전국 전 품목 2년치 입찰공고 전체 | 중복 제거 후 기준 |
| 253개 시군구 | 소상공인 상가정보 API 기준 커버리지 | 255개 중 99.2% |
| 220개 표현 | 시군구 중 공고 집계 기준 사용값 | 슬라이드에서 기준 명시 필요 |
| 29.7점 | 부산 해운대구 / 급식·식자재 / opportunity_score | 전국 평균 25.5점 대비 |
| 62건 | 부산 해운대구 / 급식·식자재 / bid_count | 최근 2년 기준 |
| 21억원 | 부산 해운대구 / 급식·식자재 / amount_sum | 추정금액 합계 |
| 98% | ML 분류기 정확도 / 홀드아웃 14,070건 기준 | 사무용품 Recall 0.57 약점 포함 |

## 주의사항

- 모든 점수는 **공공조달 수요 기반 참고 지표**입니다.
- 창업 성공, 투자 수익, 계약 보장을 예측하지 않습니다.
- 민간 소비 수요(B2C)는 반영되지 않습니다. 공공조달(B2G) 관점에 한정됩니다.
- demand_confidence_score는 학교급식 분야에만 현재 적용됩니다. 전 품목 낙찰 데이터는 향후 연계 과제입니다.
