# 파일 정리표

현재 프로젝트 기준은 **공공조달 수요 데이터를 활용한 예비창업자 사업 아이템·입지 추천 보조 서비스**입니다.
아래 표는 지금부터 디버깅하거나 기능을 붙일 때 어떤 파일을 봐야 하는지 정리한 목록입니다.

## 1. 지금 실행 흐름에 필요한 핵심 파일

| 구분 | 파일 | 역할 |
|---|---|---|
| 설정 | `src/config/settings.py` | API 키, API URL, 데이터/결과 저장 경로 관리 |
| 조달 API | `src/api/procurement_api.py` | 나라장터 입찰공고 API 호출 |
| 인구 API | `src/api/population_api.py` | 행정안전부 인구/세대현황 API 호출 |
| 조달 수집 | `src/collect/build_seoul_sample.py` | 서울 샘플 입찰공고 수집부터 분석 결과까지 한 번에 생성 |
| 조달 수집 | `src/collect/fetch_bid_data.py` | 입찰공고 원천/정제 데이터만 저장하는 단순 수집 스크립트 |
| 인구 수집 | `src/collect/fetch_population_data.py` | 서울 자치구 인구/세대현황 raw/processed CSV 생성 |
| feature 생성 | `src/collect/build_feature_table.py` | 조달 matrix와 인구/세대 데이터를 결합 |
| 조달 정제 | `src/preprocess/clean_bid_data.py` | 공고명, 자치구, 품목군, 금액, 공고일 표준화 |
| 인구 정제 | `src/preprocess/clean_population.py` | 자치구, 총인구, 세대수 표준화 |
| matrix 생성 | `src/features/build_opportunity_matrix.py` | 지역 x 품목군 matrix와 opportunity_score 생성 |
| feature 생성 | `src/features/build_features.py` | 인구/세대 대비 공공수요 feature 생성 |
| 추천 | `src/recommendation/recommend_items.py` | 지역 입력 -> 추천 품목 |
| 추천 | `src/recommendation/recommend_regions.py` | 품목 입력 -> 추천 지역 |
| 시각화 | `src/visualization/plot_heatmap.py` | 지역 x 품목군 히트맵 생성 |
| 시각화 | `src/visualization/plot_opportunity_map.py` | 점수 기반 막대그래프 생성 |
| 점검 화면 | `streamlit_review.py` | 중간점검/PPT식 확인 화면 |

## 2. 문서 파일

| 파일 | 역할 |
|---|---|
| `README.md` | 프로젝트 전체 소개와 실행법 |
| `docs/project_status_guide.md` | 사용자를 위한 현재 상태 설명서 |
| `docs/debug_execution_order.md` | 디버깅 순서와 실행 순서 |
| `docs/presentation_5slides.md` | 5장 발표자료 초안 |
| `docs/data_dictionary.md` | 주요 데이터 컬럼 설명 |
| `docs/idea.md` | 아이디어/문제의식 정리 |
| `docs/gpt_material_request.md` | GPT에게 자료 요청할 때 쓸 정리 문서 |

## 3. 보조 또는 호환용 파일

이 파일들은 당장 핵심 흐름에는 없어도, 예전 import나 빠른 확인용으로 남겨둔 파일입니다.
다음 정리 단계에서 지워도 되는지 다시 판단하면 됩니다.

| 파일 | 현재 판단 |
|---|---|
| `src/collect/test_api.py` | API 연결 확인용. 디버깅 때는 유용해서 보류 |
| `src/preprocess/clean_procurement.py` | 예전 이름 호환 wrapper. 새 코드는 `clean_bid_data.py` 사용 |
| `src/visualization/plot_dashboard.py` | 예전 이름 호환 wrapper. 새 코드는 `plot_heatmap.py`, `plot_opportunity_map.py` 사용 |
| `src/api/public_data_api.py` | 현재 직접 사용처 없음. 공공데이터 키 정규화 helper였으나 삭제 후보 |
| `src/preprocess/merge_region_data.py` | 현재 직접 사용처 없음. feature table 구조로 대체 가능해서 삭제 후보 |
| `src/utils/file_handler.py` | CSV 저장/로드 helper. 수집 스크립트에서 사용 중이면 유지 |
| `src/utils/logger.py` | 로그 helper. 현재 사용 빈도 낮지만 나중에 수집 로그 붙일 때 사용 가능 |

## 4. 정리 완료한 파일

아래 파일들은 현재 방향과 맞지 않거나, 캐시/예전 산출물이어서 정리했습니다.

| 종류 | 정리 내용 |
|---|---|
| Python 캐시 | `src/**/__pycache__` 삭제 |
| 예전 물류 분석 코드 | `src/analysis/*` 삭제 상태 유지 |
| 예전 원천 샘플 | `data/raw/bid_list_sample.csv` 삭제 |
| 예전 정제 샘플 | `data/processed/bid_list_cleaned.csv` 삭제 |
| 예전 지역점수 표 | `outputs/tables/region_demand_scores.csv` 삭제 |
| 예전 지역점수 그림 | `outputs/figures/region_demand_scores.png` 삭제 |

## 5. 앞으로 기준

- 새 기능은 되도록 `src/features`, `src/recommendation`, `src/modeling`에 붙입니다.
- API 호출은 `src/api`, 실행 스크립트는 `src/collect`에 둡니다.
- raw/processed 데이터는 `data` 아래에 두고, 발표용 산출물은 `outputs` 아래에 둡니다.
- `opportunity_score`는 창업 성공 점수가 아니라 공공수요 참고 점수입니다.
