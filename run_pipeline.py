"""
전체 데이터 파이프라인 단일 실행 스크립트

역할:
    수집부터 소비층 점수 산출까지 전 단계를 순서대로 실행합니다.
    각 단계가 완료되면 체크포인트 파일에 현재 단계를 기록해,
    중간에 실패하더라도 해당 단계부터 재실행할 수 있습니다.

파이프라인 단계:
    1. collect      - 조달청 API에서 자치구별 입찰공고 수집 → data/raw/
    2. classify     - 기관명/공고명 분류 (agency_type, item_category_detail) → data/processed/
    3. features     - opportunity_matrix, feature_table 생성 → outputs/tables/
    4. competition  - 소상공인 점포 기반 경쟁 포화도 산출 → outputs/tables/
    5. consumer_fit - 행안부 연령 인구 기반 소비층 적합도 산출 → outputs/tables/

실행:
    python run_pipeline.py                        # 전체 실행 (또는 체크포인트 이어서)
    python run_pipeline.py --from-step classify   # classify 단계부터 강제 재시작
    python run_pipeline.py --from-step features
    python run_pipeline.py --from-step competition
    python run_pipeline.py --from-step consumer_fit
    python run_pipeline.py --force-recollect      # 기존 raw 파일 삭제 후 재수집

체크포인트 파일: logs/pipeline_checkpoint.txt
로그 파일:      logs/pipeline_YYYYMMDD_HHMMSS.log
"""

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

CHECKPOINT_FILE = LOG_DIR / "pipeline_checkpoint.txt"
LOG_FILE = LOG_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# ── 로거 설정 ──────────────────────────────────────────────────────
def setup_logger() -> logging.Logger:
    logger = logging.getLogger("pipeline")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S")

    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


log = setup_logger()

# ── 체크포인트 ─────────────────────────────────────────────────────
STEPS = ["collect", "classify", "features", "competition", "consumer_fit", "done"]


def read_checkpoint() -> str:
    if CHECKPOINT_FILE.exists():
        return CHECKPOINT_FILE.read_text(encoding="utf-8").strip()
    return "collect"


def write_checkpoint(step: str) -> None:
    CHECKPOINT_FILE.write_text(step, encoding="utf-8")
    log.info("[체크포인트] %s", step)


# ── 각 단계 함수 ───────────────────────────────────────────────────

def step_collect() -> bool:
    log.info("=" * 60)
    log.info("STEP 1/5  수집  (2년치 서울 25개 구)")
    log.info("=" * 60)

    # 이미 raw 데이터가 있으면 건너뜀
    raw = ROOT / "data" / "raw" / "seoul_bid_sample.csv"
    if raw.exists():
        size = raw.stat().st_size
        log.info("기존 raw 파일 존재 (%d bytes) — 수집 건너뜀", size)
        log.info("재수집이 필요하면 %s 를 삭제 후 재실행", raw)
        return True

    try:
        from src.collect.build_seoul_sample import _collect_all_districts
        from src.features.build_opportunity_matrix import TARGET_DISTRICTS
        from src.utils.file_handler import save_csv
        from src.config.settings import DATA_RAW_DIR

        df = _collect_all_districts(TARGET_DISTRICTS)
        if df.empty:
            log.error("수집 결과 0건 — API 키·네트워크 확인 필요")
            return False

        save_csv(df, f"{DATA_RAW_DIR}/seoul_bid_sample.csv")
        log.info("수집 완료: %d건", len(df))
        return True

    except Exception as e:
        log.exception("수집 실패: %s", e)
        return False


def step_classify() -> bool:
    log.info("=" * 60)
    log.info("STEP 2/5  분류  (agency_type + item_category_detail)")
    log.info("=" * 60)

    try:
        import pandas as pd
        from src.preprocess.clean_bid_data import clean_bid_data
        from src.preprocess.classify_agency import apply_classifications, print_classification_report
        from src.utils.file_handler import save_csv

        raw_path = ROOT / "data" / "raw" / "seoul_bid_sample.csv"
        if not raw_path.exists():
            log.error("raw 파일 없음: %s", raw_path)
            return False

        df_raw = pd.read_csv(raw_path, encoding="utf-8-sig")
        log.info("raw 로드: %d건", len(df_raw))

        cleaned = clean_bid_data(df_raw)
        log.info("정제 완료: %d건", len(cleaned))
        save_csv(cleaned, "data/processed/seoul_bid_cleaned.csv")

        classified = apply_classifications(cleaned)
        save_csv(classified, "data/processed/seoul_bid_classified.csv")
        log.info("분류 완료: %d건", len(classified))

        print_classification_report(classified)

        # 검수 기준: 기타/미분류 20% 이하
        etc_rate = (classified["item_category_detail"] == "기타/미분류").sum() / len(classified) * 100
        if etc_rate > 20:
            log.warning("[!] item_category_detail 기타/미분류 %.1f%% — 키워드 보완 필요", etc_rate)
        else:
            log.info("[OK] 기타/미분류 %.1f%% (목표 20%% 이하)", etc_rate)

        return True

    except Exception as e:
        log.exception("분류 실패: %s", e)
        return False


def step_features() -> bool:
    log.info("=" * 60)
    log.info("STEP 3/5  피처  (opportunity_matrix + feature_table)")
    log.info("=" * 60)

    try:
        import pandas as pd
        from src.features.build_opportunity_matrix import (
            TARGET_DISTRICTS, build_opportunity_matrix, summarize_top_items_by_district,
        )
        from src.collect.fetch_population_data import load_population_reference
        from src.features.build_features import build_feature_table
        from src.utils.file_handler import save_csv

        # classified(item_category_detail 포함)를 읽어 신 분류기 기준으로 matrix 생성
        classified_path = ROOT / "data" / "processed" / "seoul_bid_classified.csv"
        src_path = classified_path if classified_path.exists() else ROOT / "data" / "processed" / "seoul_bid_cleaned.csv"
        cleaned = pd.read_csv(src_path, encoding="utf-8-sig")
        log.info("matrix 입력: %s", src_path.name)

        matrix = build_opportunity_matrix(cleaned, TARGET_DISTRICTS)
        save_csv(matrix, "outputs/tables/seoul_opportunity_matrix.csv")
        log.info("opportunity_matrix: %d행", len(matrix))

        top_items = summarize_top_items_by_district(matrix, top_n=5)
        save_csv(top_items, "outputs/tables/seoul_top_items_by_district.csv")

        population = load_population_reference()
        feature_table = build_feature_table(matrix, population)
        save_csv(feature_table, "outputs/tables/seoul_feature_table.csv")
        log.info("feature_table: %d행", len(feature_table))

        return True

    except Exception as e:
        log.exception("피처 생성 실패: %s", e)
        return False


def step_competition() -> bool:
    log.info("=" * 60)
    log.info("STEP 4/5  경쟁  (competition_matrix)")
    log.info("=" * 60)

    try:
        from src.features.build_competition_matrix import build_competition_matrix
        from src.features.build_opportunity_matrix import TARGET_DISTRICTS
        from src.utils.file_handler import save_csv

        matrix = build_competition_matrix(TARGET_DISTRICTS)
        if matrix.empty:
            log.warning("경쟁 데이터 없음 — 소상공인 API 확인 필요 (건너뜀)")
            return True  # 선택 단계이므로 실패해도 파이프라인 계속

        save_csv(matrix, "outputs/tables/seoul_competition_matrix.csv")
        log.info("competition_matrix: %d행", len(matrix))
        return True

    except Exception as e:
        log.exception("경쟁 매트릭스 실패 (건너뜀): %s", e)
        return True  # 선택 단계


def step_consumer_fit() -> bool:
    log.info("=" * 60)
    log.info("STEP 5/5  소비층  (consumer_fit_score)")
    log.info("=" * 60)

    try:
        from src.features.build_consumer_fit import build_consumer_fit_score
        from src.utils.file_handler import save_csv

        result = build_consumer_fit_score()
        if result.empty:
            log.warning("연령 데이터 없음 — 행안부 API 확인 필요 (건너뜀)")
            return True

        save_csv(result, "outputs/tables/seoul_consumer_fit.csv")
        log.info("consumer_fit: %d행", len(result))
        return True

    except Exception as e:
        log.exception("소비층 점수 실패 (건너뜀): %s", e)
        return True


# ── 메인 ──────────────────────────────────────────────────────────

STEP_FUNCS = {
    "collect":      step_collect,
    "classify":     step_classify,
    "features":     step_features,
    "competition":  step_competition,
    "consumer_fit": step_consumer_fit,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-step", choices=list(STEP_FUNCS.keys()), default=None,
                        help="특정 단계부터 재시작 (기본: 체크포인트 또는 처음부터)")
    parser.add_argument("--force-recollect", action="store_true",
                        help="기존 raw 파일을 무시하고 재수집")
    args = parser.parse_args()

    start_time = time.time()
    log.info("파이프라인 시작")
    log.info("로그 파일: %s", LOG_FILE)

    # 시작 단계 결정
    if args.from_step:
        start_step = args.from_step
        log.info("강제 시작 단계: %s", start_step)
    else:
        start_step = read_checkpoint()
        if start_step == "done":
            log.info("이미 완료 상태. --from-step 으로 재실행하세요.")
            return
        log.info("체크포인트에서 재개: %s", start_step)

    if args.force_recollect:
        raw = ROOT / "data" / "raw" / "seoul_bid_sample.csv"
        if raw.exists():
            raw.unlink()
            log.info("기존 raw 파일 삭제 (재수집 모드)")
        start_step = "collect"

    # 단계 실행
    step_list = list(STEP_FUNCS.keys())
    start_idx = step_list.index(start_step)

    for step in step_list[start_idx:]:
        write_checkpoint(step)
        success = STEP_FUNCS[step]()
        if not success:
            log.error("파이프라인 중단: %s 단계 실패", step)
            log.error("재실행: python run_pipeline.py --from-step %s", step)
            sys.exit(1)

    write_checkpoint("done")
    elapsed = time.time() - start_time
    log.info("=" * 60)
    log.info("파이프라인 완료  (소요: %.0f초 / %.1f분)", elapsed, elapsed / 60)
    log.info("=" * 60)
    log.info("결과 파일:")
    log.info("  data/processed/seoul_bid_classified.csv")
    log.info("  outputs/tables/seoul_opportunity_matrix.csv")
    log.info("  outputs/tables/seoul_top_items_by_district.csv")
    log.info("  outputs/tables/seoul_feature_table.csv")
    log.info("  outputs/tables/seoul_competition_matrix.csv")
    log.info("  outputs/tables/seoul_consumer_fit.csv")
    log.info("Streamlit: streamlit run streamlit_review.py")


if __name__ == "__main__":
    main()
