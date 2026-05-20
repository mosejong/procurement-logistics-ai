# Changelog

## [2026-05-21] 발주계획 + 종합쇼핑몰 MAS API 연동 — AI 해석 컨텍스트 자동 주입

### 핵심 변경

**`src/api/procurement_plan_api.py`** (신규)
- `get_plan_items` / `get_plan_services`: 향후 발주계획 조회 (물품/용역)
- `collect_plan_all(months_ahead=6)`: 향후 N개월 전수 수집
- `get_mas_products`: 종합쇼핑몰 다수공급자계약 품목 조회 (`getMASCntrctPrdctInfoList`)
- `collect_mas_products(max_records=5000)`: MAS 계약 품목 전수 수집
- 403 오류 시 `PermissionError` 명시 (승인 대기 안내)

**`src/collect/collect_plan_data.py`** (신규)
- 발주계획 445건 수집 → 시/도×품목군 집계 → `procurement_plan_summary.csv`
  - `orderInsttNm` 기반 시/도 추출 (17개 시/도 매핑)
  - `prdctClsfcNoNm` + `bizNm` 키워드 기반 item_category 매핑
  - 총 발주금액 1,249.8억원
- MAS 품목 5,000건 수집 → 품목군별 집계 → `shopping_mall_summary.csv`
  - `prdctLrgclsfcNm` 직접 매핑 테이블 (`_MAS_LRG_MAP`): 8개 품목군 확인
  - 사무용품/문구 2,321건(평균 34.7만원), 전기/전자 1,211건(평균 875만원) 등

**`src/recommendation/gemini_client.py`** 업데이트
- `_load_plan_df` / `_load_shop_df`: `@lru_cache` 1회 로딩
- `_lookup_plan(city, category)` / `_lookup_shop(city, category)`: CSV 조회
- `build_demand_summary` 내 자동 주입: CSV 존재 시 프롬프트에 추가
  - "향후 6개월 발주계획: N건 (X억원)  [출처: 나라장터 발주계획]"
  - "종합쇼핑몰 MAS 등록 품목 수: N건 (평균단가 Y원)  [출처: 나라장터 다수공급자계약]"
- `DemandContext`에 `plan_count`, `plan_amount`, `shopping_count`, `shopping_amount` 필드 추가 (선택적 직접 주입용)
- CSV 없으면 조용히 생략 → 기존 호환성 유지

### 데이터 생성
```
python -m src.collect.collect_plan_data
  → outputs/tables/procurement_plan_summary.csv  (130행, 17개 시/도 × 품목군)
  → outputs/tables/shopping_mall_summary.csv     (8행, 품목군별 MAS 집계)
```

### API 엔드포인트
- 발주계획: `https://apis.data.go.kr/1230000/ao/OrderPlanSttusService`
- 종합쇼핑몰: `https://apis.data.go.kr/1230000/at/ShoppingMallPrdctInfoService`

### 갱신 주기
- 발주계획: 월 1회 (`--plan-only`)
- MAS 품목: 분기 1회 (`--shop-only`)

---

## [2026-05-20] 점수 신뢰도 전면 개선 + 문서 통합

### 핵심 변경

**`competition_score` 재설계 (`src/features/build_opportunity_matrix.py`)**
- 기존: 개방입찰 비율(1 − 지명경쟁 비율) → 90%+가 1.0으로 몰리는 신뢰도 문제
- 변경: 품목군 내 공고수 역백분위 (`1.0 - rank(pct=True)`)
- 효과: mean=0.497, std=0.288으로 실질적 차별화 달성

**카테고리 통일 (`src/features/build_opportunity_matrix.py`)**
- 기존: `classify_agency.py`의 `item_category_detail`(18종, 자체 분류기) → matrix에 사용
- 변경: `bid_cleaned_national.csv`의 `item_category`(19종) 그대로 사용
- 이유: demand_forecast.py도 `item_category`를 사용하여 두 파일 간 카테고리 불일치 발생
  - 불일치 예시: matrix에 없는 '시설위탁/운영', '창업/경영지원' 등 → "데이터 없음" 오류
- 효과: forecast 탭에서 모든 도시+품목군 조합 정상 표시

**수요 예측 개선 (`src/modeling/demand_forecast.py`)**
- 계절성 임계값: CV > 0.5 → CV > 0.8 (기존에 거의 모든 품목군이 경고를 받던 문제 해결)
- 트렌드 판정: 전체 2년 기울기 → 최근 6개월 기울기 우선 (모멘텀 반영)
- 현재 계절성 경고 대상: `사무용품/문구`(CV 0.859), `위생/방역`(CV 0.826)

**블루오션 탐지 (`src/modeling/demand_anomaly.py`)**
- 방향 수정: 새 competition_score(높을수록 진입 용이)에 맞게 `>= 0.5` 필터 유지 확인

**AI 해석 냉정화 (`src/recommendation/gemini_client.py`)**
- `_SYSTEM_INSTRUCTION`: 기본 분류 📊/⚠️/🔍, 막연한 긍정 표현 금지
- `_OVERDEMAND_SYSTEM`: 기본값 🔴 진입 주의, 🟢는 competition_score >= 0.6 AND bid_count 평균 이하 조건부만 허용

**Streamlit 개선 (`streamlit_review.py`)**
- 계절성 경고: 차트 상단 → 하단 이동
- 계절성 이유 룩업 테이블 (`_SEASON_REASON`): 12개 카테고리별 발생 원인 명시
  - 예: 위생/방역 → "하절기(5~9월) 방역·소독 수요 급증"
  - 예: 급식/식품 → "학기 중 급식 수요 집중, 방학 기간 감소"
- 수요 예측 탭 도시 드롭다운: blue_ocean 파일 기준 → matrix_all 전체 도시 기준
- 영문 컬럼명 → `_COL_KR` dict으로 한글 일괄 매핑 (17개 컬럼)

### 데이터 재생성
```
python -m src.features.build_opportunity_matrix (내부 스크립트로 대체)
  → outputs/tables/opportunity_matrix_national.csv (2,446행, 19개 카테고리)
python -m src.modeling.demand_anomaly
  → outputs/tables/blue_ocean_districts.csv (50개 블루오션)
python -m src.modeling.demand_forecast
  → outputs/tables/demand_forecast.csv (587행, 6개월 예측)
```

---

## [2026-05-14] 강사님 피드백 5개 이행 + 공모전 방어선 구축

### 핵심 변경
- `competition_score` 초기 개선 (개방입찰 비율 방식, 이후 2026-05-20에 재설계)
- 수요 예측 6개월로 확장 (기존 3개월)
- 계절성 경고 추가 (`has_seasonality`, `seasonal_cv` 컬럼)
- 수요 예측 탭 추가 (블루오션 판정 + 트렌드 통합)
- TOP3 메트릭 카드 → 기회 상위/하위 해석 블록으로 교체
- 예측 차트: 3개월 이동평균 추세선 + 예측 구간 음영
- 블루오션 판정 fallback: blue_ocean 파일 없으면 matrix_all에서 직접 조회

---

## [2026-05-10] 나라장터 계약정보 API 연결

### 핵심 변경
- 계약정보 API(CntrctInfoService) 연동: 38,367건 수집
- "공고=의사 / 계약=실측" 2단 구조 완성
- `demand_confidence_score` 신호 추가
- gemini_client.py 프롬프트에 계약 실측 근거 인용 구조 추가

---

## [2026-04-XX] 전국 확장 + 물류 거점

### 핵심 변경
- 서울 전용 → 전국 17개 시/도 (100,083건)
- 국토부 물류창고 등록정보 연동 (5,911개소)
- aT 학교급식 입찰·낙찰 데이터 연동 (BID 285,552건, AWARD 448,690건)
- 물류 거점 분석 탭 추가 (hub_score, 1·2·3티어)
