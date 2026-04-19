# 공공조달 수요 기반 사업 아이템·입지 추천 보조 서비스

공공조달 입찰공고를 지역별·품목별 공공수요 신호로 해석해, 예비창업자와 창업상담가가 참고할 수 있는 사업기회 탐색 근거를 만드는 데이터 분석 프로젝트입니다.

## 개발 배경

이 프로젝트는 물류창고 현장에서 10년간 경험한 재고 불균형 문제에서 출발했습니다.

악성재고는 단순히 창고에 남은 물건이 아니라, 수요를 잘못 읽은 결과입니다. 수요가 없는 곳에 물건이 쌓이면 보관비, 처리비, 폐기비가 발생하고 결국 영업손실로 이어집니다.

창업도 비슷합니다. 수요가 충분하지 않은 지역에서 맞지 않는 품목으로 시작하면 재고 부담과 운영 손실이 커질 수 있습니다. 본 프로젝트는 공공조달 데이터를 하나의 수요 신호로 해석해, 창업 전 의사결정에 참고할 수 있는 근거 데이터를 제공하고자 합니다.

## 프로젝트 목적

이 서비스는 창업 성공을 예측하거나 단정하지 않습니다.

목표는 지역별로 어떤 품목의 공공수요가 반복적으로 나타나는지, 특정 품목이 어느 지역에서 자주 발주되는지, 금액 규모와 최근성은 어떤지 정리해 창업상담 과정에서 참고할 수 있는 보조 자료를 만드는 것입니다.

## 핵심 개념

- 공공조달 입찰공고 = 공공기관의 수요 신호
- 지역 x 품목군 매트릭스 = 현재 프로젝트의 핵심 분석표
- opportunity_score = 창업 성공 점수가 아니라 공공수요 참고 점수
- 현재 MVP = 규칙 기반/지표 기반 분석
- 향후 확장 = 인구·세대·연령·상권 특성 기반 클러스터링

## 현재 MVP 기능

- 조달청 입찰공고 API 수집
- 공고명, 수요기관, 지역, 금액, 공고일 정제
- 서울 자치구 추출
- 입찰 공고명 기반 품목군 분류
- 지역 x 품목군 사업기회 매트릭스 생성
- 지역 입력 시 추천 품목 TOP N 제공
- 품목 입력 시 추천 지역 TOP N 제공
- 히트맵, CSV, Markdown 리포트 생성

## 프로젝트 구조

```text
data/
  raw/                 API 원천 데이터
  processed/           정제 데이터
docs/                  기획, 발표, 디버깅 문서
outputs/
  figures/             시각화 이미지
  tables/              분석 결과 CSV
  reports/             요약 리포트
src/
  config/              환경변수와 경로 설정
  api/                 공공데이터 API 호출
  collect/             데이터 수집 실행 스크립트
  preprocess/          원천 데이터 정제
  features/            지역 x 품목군 매트릭스와 feature 생성
  modeling/            향후 클러스터링 모델
  recommendation/      지역->품목, 품목->지역 추천
  visualization/       히트맵과 결과 그래프
  utils/               파일 저장, 로깅 유틸리티
```

## 실행 방법

API 키를 `.env`에 설정합니다.

```text
PROCUREMENT_API_KEY=발급받은_서비스키
```

API 연결만 확인합니다.

```bash
python -m src.collect.test_api
```

서울 주요 자치구 샘플 결과를 생성합니다.

```bash
python -m src.collect.build_seoul_sample
```

중간점검 화면을 실행합니다.

```bash
python -m streamlit run streamlit_review.py
```

## 주요 결과물

```text
data/raw/seoul_bid_sample.csv
data/processed/seoul_bid_cleaned.csv
outputs/tables/seoul_opportunity_matrix.csv
outputs/tables/seoul_top_items_by_district.csv
outputs/figures/seoul_opportunity_heatmap.png
outputs/reports/seoul_sample_summary.md
```

## 다음 단계

- 주민등록 인구 및 세대현황 API 결합
- 인구 대비 공공수요 지표 생성
- 낙찰정보 API 결합
- 품목군 키워드 사전 개선
- 지역 특성 기반 클러스터링 모델 추가
