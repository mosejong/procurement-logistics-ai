# 디버깅 순서와 파일 역할

이 문서는 프로젝트를 디버깅할 때 어떤 파일을 어떤 순서로 보면 되는지 정리한 안내서입니다.

## 1. 전체 실행 순서

현재 서울 샘플 결과를 만드는 메인 명령은 다음입니다.

```bash
python -m src.collect.build_seoul_sample
```

이 명령을 실행하면 아래 순서로 코드가 움직입니다.

```text
1. src/collect/build_seoul_sample.py
   -> 전체 파이프라인을 실행하는 시작점

2. src/api/procurement_api.py
   -> 조달청 입찰공고 API 호출

3. data/raw/seoul_bid_sample.csv
   -> API에서 받은 원천 데이터 저장

4. src/preprocess/clean_bid_data.py
   -> 원천 데이터 정제
   -> 서울 자치구 추출
   -> 품목군 분류

5. data/processed/seoul_bid_cleaned.csv
   -> 정제된 데이터 저장

6. src/features/build_opportunity_matrix.py
   -> 자치구 x 품목군 매트릭스 생성
   -> 공고 수, 금액, 최근성 점수 계산

7. outputs/tables/seoul_opportunity_matrix.csv
   -> 핵심 분석표 저장

8. outputs/tables/seoul_top_items_by_district.csv
   -> 자치구별 추천 품목 TOP3 저장

9. src/visualization/plot_heatmap.py
   -> 히트맵 이미지 생성

10. outputs/figures/seoul_opportunity_heatmap.png
    -> 시각화 결과 저장

11. outputs/reports/seoul_sample_summary.md
    -> 사람이 읽는 요약 리포트 저장

12. streamlit_review.py
    -> 위 결과물을 화면에서 확인하는 점검 페이지
```

## 2. 디버깅할 때 보는 순서

문제가 생기면 아래 순서로 확인하면 됩니다.

### 1단계: API가 되는지 확인

```bash
python -m src.collect.test_api
```

봐야 할 파일:

```text
src/api/procurement_api.py
```

확인할 것:

- `KEY EXISTS: True`가 나오는지
- `status_code: 200`이 나오는지
- `resultCode: 00` 또는 정상 응답인지

### 2단계: 서울 샘플 수집 실행

```bash
python -m src.collect.build_seoul_sample
```

봐야 할 파일:

```text
src/collect/build_seoul_sample.py
```

확인할 것:

- `수집 성공` 메시지가 나오는지
- `data/raw/seoul_bid_sample.csv`가 생성되는지

### 3단계: 정제 결과 확인

봐야 할 파일:

```text
data/processed/seoul_bid_cleaned.csv
```

중요 컬럼:

```text
district
bid_title
agency_name
item_category
estimated_amount
posted_date
```

확인할 것:

- `district`에 강남구, 마포구, 종로구 같은 자치구가 들어갔는지
- `item_category`가 전부 `기타`로만 나오지 않는지
- `estimated_amount`가 숫자로 변환됐는지

### 4단계: 분석표 확인

봐야 할 파일:

```text
outputs/tables/seoul_opportunity_matrix.csv
```

확인할 것:

- `district`
- `item_category`
- `bid_count`
- `amount_sum`
- `opportunity_score`

이 파일이 현재 프로젝트의 핵심 결과표입니다.

### 5단계: Streamlit으로 보기

```bash
python -m streamlit run streamlit_review.py
```

브라우저 주소:

```text
http://localhost:8501
```

## 3. 주요 파일별 역할

| 파일 | 역할 | 수정할 때 기준 |
| --- | --- | --- |
| `src/api/procurement_api.py` | 조달청 API 호출 | API 파라미터, 조회 기간, 페이지 오류 수정 |
| `src/collect/fetch_bid_data.py` | 원천 입찰공고 수집 | raw/processed 저장만 필요할 때 사용 |
| `src/collect/build_seoul_sample.py` | 서울 샘플 결과 생성 | 수집 기간, 페이지 수, 저장 파일명 수정 |
| `src/preprocess/clean_bid_data.py` | 데이터 정제 | 자치구 추출, 품목군 키워드, 금액 변환 수정 |
| `src/features/build_opportunity_matrix.py` | 핵심 매트릭스 생성 | 점수 산식, 대상 자치구, TOP N 수정 |
| `src/features/build_features.py` | 모델링용 feature 생성 | 인구/세대/낙찰 feature 추가 |
| `src/modeling/cluster_regions.py` | 향후 지역 클러스터링 | KMeans 등 모델 추가 |
| `src/recommendation/recommend_items.py` | 지역 입력 -> 품목 추천 | 지역별 추천 출력 수정 |
| `src/recommendation/recommend_regions.py` | 품목 입력 -> 지역 추천 | 품목별 추천 출력 수정 |
| `src/visualization/plot_heatmap.py` | 히트맵 생성 | 히트맵 스타일, 저장 경로 수정 |
| `streamlit_review.py` | 점검 화면 | 화면 구성, 표 표시, 설명 문구 수정 |
| `docs/project_status_guide.md` | 사람용 설명서 | 프로젝트 방향과 현재 상태 설명 수정 |

## 4. 지금 네가 판단하면 좋은 부분

아래 항목은 정답이 아니라 네 판단이 들어가야 합니다.

```text
1. 샘플 자치구가 적절한가?
2. 관악구/성동구/송파구를 꼭 살릴 것인가?
3. 품목군 이름이 마음에 드는가?
4. 품목군 키워드가 충분한가?
5. 점수 산식 50/30/20이 납득되는가?
6. 다음 단계로 인구/세대현황 API를 붙일 것인가?
7. 낙찰정보는 지금 붙일 것인가, 나중에 붙일 것인가?
```

## 5. 자주 볼 명령어

API 테스트:

```bash
python -m src.collect.test_api
```

서울 샘플 생성:

```bash
python -m src.collect.build_seoul_sample
```

점검 화면 실행:

```bash
python -m streamlit run streamlit_review.py
```

문법 검사:

```bash
python -m compileall src streamlit_review.py
```

## 6. 현재 프로젝트를 한 문장으로 말하면

```text
공공조달 입찰공고 데이터를 활용해 서울 주요 자치구별 공공수요 품목을 샘플링하고,
예비창업자와 창업상담가가 참고할 수 있는 사업 아이템·입지 판단 근거표를 만드는 중입니다.
```
