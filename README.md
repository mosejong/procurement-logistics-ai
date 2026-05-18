# 공공조달 수요 기반 입지 · 물류 거점 분석

**2026 공공조달데이터·AI 활용 창업경진대회 출품작 (주최: 조달청)**

나라장터 입찰공고를 지역별 공공수요 신호로 해석해, 예비창업자·납품업체·물류사가 수요 패턴을 데이터 근거로 탐색하는 분석 서비스.

## 👉 [라이브 데모](https://procurement-logistics-ai-5qian47widxpcuqefpjipy.streamlit.app)

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://procurement-logistics-ai-5qian47widxpcuqefpjipy.streamlit.app)

---

## 아키텍처

```
조달청 입찰공고 API
  → build_national_sample.py (전국 17개 시/도 수집, 100,083건)
  → classify_agency.py
      공고명 → item_category_detail (18종)
        1단계: 키워드 규칙 매칭
        2단계: TF-IDF + Logistic Regression (86,991건 훈련, 정확도 98.6%)
        3단계: confidence 미달 → 기타/미분류 유지
  → build_opportunity_matrix.py
      opportunity_score = 공고수(40%) + 금액(25%) + 최근성(15%) + 경쟁도(20%)
  → build_features.py (인구 보정: bids_per_10k_population)

행안부 연령별 인구 API
  → build_national_consumer_fit.py (consumer_fit_score, 242개 지역)

소상공인 상권정보 API
  → build_national_competition.py (stores_per_10k, 253개 지역, 10개 업종)

KOSIS 신생기업 생존율 API
  → collect_kosis_survival.py (survival_5y, dissolution_rate)
  → build_map_summary.py
      adjusted_score = opportunity_score × (survival_5y/100) × (1 - dissolution_rate)

Gemini API (gemini_client.py) — AI 해석 5종 (정량 지표를 사람이 이해하기 쉬운 설명으로 변환)
  ① 수요 설명: 추천 품목 공공수요 해석 문장
  ② 수요 공백: 데이터부족 → 블루오션 vs 실제 저수요 해석
  ③ 경쟁 구조: 고수요 지역 → 🔴진입 주의 / 🟡조건부 검토 / 🟢진입 검토
  ④ 물류 거점: 전국 수요 분포 기반 1·2·3티어 거점 전략
  ⑤ 지역 비교: 두 지역 품목군 수요 포트폴리오 차이 설명

Streamlit 대시보드 (streamlit_review.py) — 10개 탭
  🌏 전국 지도 → 🔍 사업 유형 검색 → 🗺️ 지역 분석 → 📦 품목 분석
  ⚖️ 자치구 비교 → 👥 소비층 적합도 → 🏪 경쟁 분석 → 🚚 물류 거점 분석
  🔬 분석 근거 데이터 → 📋 프로젝트 개요
```

---

## 공모전 요건 매핑

| 요건 | 구현 |
|---|---|
| 공공데이터 API 활용 | ✅ 조달청(필수) + 행안부 인구 + 소상공인 상권정보 + KOSIS 생존율 — 4개 기관 실결합 |
| AI 활용 | ✅ Gemini 해석 5종 (수요설명·수요공백·경쟁구조·물류거점·지역비교) + ML 분류기 |
| 수집 범위 | ✅ 전국 17개 시/도, 220개 지역, 100,083건, 최근 2년 |
| 창업 지원 활용성 | ✅ 예비창업자 / 납품업체 / 물류사·3PL 3개 타겟 |
| 재현 가능성 | ✅ 파이프라인 전 단계 CLI 실행 가능 |

---

## 빠른 시작

```bash
# 1. 환경 설정
pip install -r requirements.txt
cp .env.example .env
# .env에 PUBLIC_DATA_API_KEY, GEMINI_API_KEY 입력

# 2. 대시보드 실행 (수집된 데이터 포함)
streamlit run streamlit_review.py

# 3. 전국 데이터 재수집 (선택)
python -m src.collect.build_national_sample
# 특정 시/도만:
python -m src.collect.build_national_sample --cities 서울특별시 경기도
```

---

## 주요 지표

| 지표 | 계산 방식 | 의미 |
|---|---|---|
| `opportunity_score` | 공고수(40%) + 금액(25%) + 최근성(15%) + 경쟁도(20%) | 지역·품목 공공수요 종합 매력도 |
| `adjusted_score` | opportunity_score × 생존율 × (1 − 소멸률) | KOSIS 생존율 보정 점수 |
| `competition_score` | 개방입찰 비율 = 1 − 지명경쟁(dsgntCmptYn=Y) 비율 | 신규 진입 용이성 |
| `bids_per_10k_population` | 공고수 ÷ (인구 / 10,000) | 인구 규모 편향 보정 수요 밀도 |
| `consumer_fit_score` | 주소비층 연령 비중 min-max 정규화 | 인구 구성 기반 소비층 적합도 |
| `stores_per_10k` | 점포수 ÷ (인구 / 10,000) | 업종별 경쟁 포화도 |
| `hub_score` | 물리적 공고수(50%) + 금액(30%) + 품목다양성(20%) | 물류 거점 후보 종합 점수 |

---

## 추천 정책

| 플래그 | 조건 | 처리 |
|---|---|---|
| 추천 | 공고 10건 이상, 비규제 업종 | 점수 노출 + AI 수요 해석 + 경쟁 구조 판정 |
| 제외 | 폐기물/환경·건설/공사·기타/미분류 | TOP3 미노출, 정적 경고 문구 |
| 데이터부족 | 공고 10건 미만 | AI 블루오션/저수요 판정 제공 |

---

## 분류 체계

### `item_category_detail` (공고명 → 18종)

```
청소/환경미화  방역/소독  폐기물/환경  급식/식자재  IT장비/전산
사무용품/소모품  시설유지보수  교육물품/교구  의료/복지용품  행사/운영용역
조경/녹지관리  급수/전기/설비  차량/운송  경비/보안  인쇄/홍보물
건설/공사  보험/금융  전문용역/컨설팅
```

ML 적용 전 기타/미분류 13.1% → ML 적용 후 **9.2%** (TF-IDF + LogReg fallback)

---

## 수집 범위

| 항목 | 현재 |
|---|---|
| 지역 | 전국 17개 시/도, 220개 구·시·군 |
| 건수 | 100,083건 (최근 2년) |
| 인구 보정 | 206개 지역 매칭 |
| 소비층 적합도 | 242개 지역 (행안부 연령별 인구) |
| 경쟁 분석 | 253개 지역, 10개 업종 (소상공인 상권정보) |
| 생존율 보정 | 시도 × 산업 (KOSIS 신생기업 생존율) |

---

## 프로젝트 구조

```
src/
  collect/        전국 데이터 수집 (조달청·행안부·소상공인·KOSIS)
  preprocess/     정제 + 기관/공고명 분류기 (키워드 규칙 + ML fallback)
  modeling/       ML 분류기 훈련·추론 (item_classifier.pkl)
  features/       기회 매트릭스·소비층 적합도·경쟁 포화도·인구 보정
  recommendation/ 추천 정책 + Gemini AI 해석 (5종)
models/
  item_classifier.pkl    공고명 분류 ML 모델
outputs/tables/
  opportunity_matrix_national.csv   220개 지역 × 품목군
  feature_table_national.csv        인구 보정 피처 (206개 지역)
  national_consumer_fit.csv         소비층 적합도 (242개 지역)
  national_competition_matrix.csv   경쟁 포화도 (253개 지역)
  map_item_city_summary.csv         지도 탭용 선처리 집계 (adjusted_score 포함)
streamlit_review.py     메인 대시보드 (10개 탭)
check.md                검수 기록 (13차)
```

---

## 비즈니스 모델

| 타겟 | 제공 가치 |
|---|---|
| 창업지원센터 / 소상공인진흥공단 (B2B) | 상담사용 지역별 공공수요 리포트 대시보드 |
| 예비창업자 (B2C) | 업종·입지 탐색 + AI 진입 판정 |
| B2G 납품업체 (B2B) | 영업 거점 우선순위 설정 |
| 물류사 / 3PL (B2B) | 공공수요 기반 물류 거점 최적화 근거 |

**단계별 수익 구조**: POC(현재 무료 데모) → B2B SaaS 구독 → 플랫폼 연계·컨설팅

---

## 현재 한계

| 항목 | 내용 |
|---|---|
| 민간 수요 미반영 | 공공조달(B2G) 관점만. B2C 업종은 상권 데이터가 더 적합 |
| 데이터부족 비중 | 지역·품목 조합 중 10건 미만 구간 다수 (보수적 정책의 결과) |
| Gemini 모델 | `gemini-3.1-flash-lite` (정식 버전) — API 실패 시 수치 기반 폴백 자동 대체 |
| 소비층 적합도 | 시/도별 연령 분포 기반 추정값 (실측 시군구 연령 데이터 미확보) |

---

> `opportunity_score`는 공공수요 참고 지표이며, 창업 성공 예측값이 아닙니다.  
> AI 해석은 정량화 수치를 사람이 이해하기 쉬운 설명으로 변환한 보조 자료이며, 투자·창업 판단 근거가 아닙니다.
