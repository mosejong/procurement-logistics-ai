# 데이터 사전

원천 API의 컬럼명은 공고 유형에 따라 달라질 수 있으므로, 전처리 단계에서 아래 표준 컬럼으로 변환합니다.

## 표준 컬럼

| 표준 컬럼 | 설명 | 예시 |
| --- | --- | --- |
| `bid_title` | 입찰 공고명 또는 사업명 | 사무용품 구매 |
| `agency_name` | 수요기관명 | 서울특별시 관악구 |
| `region` | 시도 단위 지역명 | 서울 |
| `district` | 서울 자치구명 | 관악구 |
| `posted_date` | 공고일 | 2026-04-19 |
| `estimated_amount` | 추정가격 또는 배정예산 | 15000000 |
| `item_text` | 품목 분류와 검색에 사용할 텍스트 | 공고명 + 기관명 + 구매품목 |
| `item_category` | 공고명 기반 품목군 | 사무용품/문구 |

## 핵심 분석 테이블

현재 프로젝트의 핵심은 `지역 x 품목군` 매트릭스입니다.

| 컬럼 | 설명 | 예시 |
| --- | --- | --- |
| `district` | 서울 자치구 | 종로구 |
| `district_profile` | 사람이 읽는 지역 특성 라벨 | 공공기관/전통상권/관광 |
| `item_category` | 품목군 | 도서/콘텐츠 |
| `bid_count` | 해당 자치구·품목군 공고 수 | 5 |
| `amount_sum` | 추정금액 합계 | 647945000 |
| `amount_mean` | 평균 추정금액 | 129589000 |
| `latest_posted_date` | 가장 최근 공고일 | 2025-11-21 |
| `count_score` | 공고 수 정규화 점수 | 1.0 |
| `amount_score` | 금액 규모 정규화 점수 | 1.0 |
| `recency_score` | 최근성 점수 | 0.19 |
| `opportunity_score` | 최종 공공수요 참고 점수 | 83.92 |

## 점수 산식 초안

초기 MVP에서는 설명 가능한 단순 가중합을 사용합니다.

```text
opportunity_score = 공고 수 점수 50% + 금액 점수 30% + 최근성 점수 20%
```

주의:

- `opportunity_score`는 창업 성공 점수가 아닙니다.
- 공공조달 데이터 안에서 눈에 띄는 지역·품목 조합을 찾기 위한 참고 지표입니다.
- 다음 단계에서 주민등록 인구 및 세대현황을 결합하면 인구 대비 공공수요 지표를 추가할 수 있습니다.

## 향후 feature 후보

| feature | 설명 |
| --- | --- |
| `population` | 자치구 인구 |
| `households` | 자치구 세대수 |
| `bids_per_10k_population` | 인구 1만 명당 공고 수 |
| `bids_per_10k_households` | 세대 1만 세대당 공고 수 |
| `award_count` | 낙찰 건수 |
| `award_amount_sum` | 낙찰 금액 합계 |
| `region_cluster` | 지역 특성 기반 클러스터 |
