# 점수 모델 설계 근거

> 이 서비스의 점수는 공공수요 참고 지표이며, 창업 성공 예측값이 아닙니다.

---

## 1. opportunity_score (공공수요 기회 점수)

```
opportunity_score =
    count_score × 0.40
  + amount_score × 0.25
  + recency_score × 0.15
  + competition_score × 0.20
```

### 가중치 설계 이유

| 지표 | 가중치 | 설계 이유 |
|---|---|---|
| `count_score` (공고수) | 40% | 반복 발주는 수요의 지속성을 나타내는 가장 강한 신호. 1회성 대형 공고보다 반복 소규모 공고가 창업 입지 판단에 더 유의미함 |
| `amount_score` (금액) | 25% | 시장 규모를 반영하지만, 대형 1건으로 왜곡될 수 있어 25%로 제한. 단순히 금액이 크다고 진입이 쉬운 것은 아님 |
| `recency_score` (최근성) | 15% | 2년 전 수요가 현재도 유효한지 보정. 최근 공고일수록 현재 수요 가능성이 높음 |
| `competition_score` (경쟁도) | 20% | 같은 수요라도 지명경쟁 비율이 높으면 신규 진입이 어려움. 개방입찰 비율이 높을수록 신규 진입 용이 |

### 계산 방식

- `count_score`, `amount_score`: 전국 구·시·군 단위 min-max 정규화 (0~1)
- `recency_score`: `1 / (1 + 경과일/30)` — 현재 기준 30일마다 감쇠
- `competition_score`: `1 - 지명경쟁(dsgntCmptYn=Y) 비율`

---

## 2. adjusted_score (생존율 보정 점수)

```
adjusted_score = opportunity_score × (survival_5y / 100) × (1 − dissolution_rate)
```

KOSIS 신생기업 생존율 데이터를 결합해 공공수요가 높아도 업종 자체의 진입 리스크가 높은 경우 점수를 하향 보정합니다.

---

## 3. hub_score (물류 거점 점수)

```
hub_score = normalized(bid_count) within item_category group (0~100)
```

품목군 내에서 공고 수 기준으로 정규화한 점수. 같은 품목군 내 지역 간 상대적 수요 집중도를 나타냅니다.

---

## 4. demand_confidence_score (수요 신뢰도 점수) ⚠️ MVP

```
demand_confidence_score =
    0.5 × normalized(notice_count)
  + 0.3 × normalized(award_count)
  + 0.2 × normalized(award_amount_sum)
```

> ⚠️ MVP 단계의 가중치입니다. 향후 실제 낙찰률·계약전환율 데이터로 보정 예정.

입찰공고(의사 신호)와 낙찰/계약(실측 신호)을 결합한 수요 신뢰도 지표입니다.

- `notice_count`: 공고 수 = 기관의 구매 의향 (예정 수요)
- `award_count`: 낙찰 건수 = 실제 구매 확정 (실측 수요)
- `award_amount_sum`: 낙찰 금액 = 실제 시장 규모

### 공고 수요 vs 계약 수요

| 구분 | 데이터 | 의미 |
|---|---|---|
| 입찰공고 | 나라장터 입찰공고 API | 공공기관의 구매 의사가 공개된 **강한 수요 신호** |
| 낙찰/계약 | 나라장터 낙찰결과 API | 실제 구매가 완료된 **확정 수요** |

입찰공고만으로 실제 수요를 단정하지 않기 위해, 두 데이터를 결합해 수요 신뢰도를 산출합니다.

---

## 5. logistics_infra_score (물류 인프라 점수)

```
logistics_infra_score =
    0.5 × normalized(warehouse_count)
  + 0.3 × normalized(warehouse_area_sum)
  + 0.2 × normalized(cold_storage_count)
```

국토부 물류창고업 등록정보를 기반으로 지역 물류 인프라 수준을 점수화합니다.

기존 `hub_score`가 수요 집중도 기반이라면, `logistics_infra_score`는 실제 창고 인프라 가용성을 반영합니다.

### 물류 거점 판단 = 수요 + 인프라

```
거점 후보 = 수요가 많은 지역 (hub_score 상위)
          + 창고 인프라가 있는 지역 (logistics_infra_score 상위)
```

---

## 주의사항

- 모든 점수는 **공공조달 수요 기반 참고 지표**입니다.
- 창업 성공, 투자 수익, 계약 보장을 예측하지 않습니다.
- 민간 소비 수요(B2C)는 반영되지 않습니다. 공공조달(B2G) 관점에 한정됩니다.
- 서비스 내 모든 화면에 이 한계를 명시합니다.
