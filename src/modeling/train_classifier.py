"""
item_category_detail ML 분류기 훈련

데이터: data/processed/bid_cleaned_national.csv (100,083건)
레이블: classify_item_detail(bid_title) 결과 (키워드 규칙 적용값)
       — 기타/미분류는 훈련에서 제외, 모델이 예측할 대상

특징: TF-IDF (char n-gram 2~4) + LogisticRegression
저장: models/item_classifier.pkl

실행:
    python -m src.modeling.train_classifier
"""

from pathlib import Path

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer

from src.preprocess.classify_agency import classify_item_detail

DATA_PATH  = Path("data/processed/bid_cleaned_national.csv")
MODEL_PATH = Path("models/item_classifier.pkl")

EXCLUDE_LABEL = "기타/미분류"
CONFIDENCE_THRESHOLD = 0.55  # item_classifier.py와 동일하게 유지


def load_training_data() -> pd.DataFrame:
    print(f"데이터 로드: {DATA_PATH}")
    df = pd.read_csv(DATA_PATH, encoding="utf-8-sig", low_memory=False)

    title_col = "bid_title" if "bid_title" in df.columns else None
    if title_col is None:
        raise ValueError("bid_title 컬럼 없음")

    print("키워드 규칙으로 레이블 생성 중...")
    df["_label"] = df[title_col].fillna("").apply(classify_item_detail)

    labeled = df[df["_label"] != EXCLUDE_LABEL].copy()
    print(f"레이블 건수: {len(labeled):,} / 전체 {len(df):,} "
          f"(제외 {len(df) - len(labeled):,}건 = {(len(df) - len(labeled)) / len(df) * 100:.1f}%)")

    print("\n카테고리 분포:")
    dist = labeled["_label"].value_counts()
    for cat, cnt in dist.items():
        print(f"  {cat:<20} {cnt:>6}건")

    return labeled[["bid_title", "_label"]].dropna()


def train(df: pd.DataFrame) -> Pipeline:
    X = df["bid_title"].tolist()
    y = df["_label"].tolist()

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.15, random_state=42, stratify=y
    )

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 4),
            max_features=80_000,
            sublinear_tf=True,
        )),
        ("clf", LogisticRegression(
            max_iter=1000,
            C=5.0,
            solver="lbfgs",
        )),
    ])

    print(f"\n훈련 시작 | 훈련 {len(X_train):,}건 / 검증 {len(X_test):,}건")
    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)
    acc = (pd.Series(y_pred) == pd.Series(y_test)).mean()
    print(f"\n검증 정확도: {acc:.4f} ({acc*100:.2f}%)")
    print("\n분류 보고서:")
    print(classification_report(y_test, y_pred, zero_division=0))

    # confidence 분포 확인
    proba = pipeline.predict_proba(X_test)
    max_proba = proba.max(axis=1)
    above = (max_proba >= CONFIDENCE_THRESHOLD).mean()
    print(f"\nconfidence >= {CONFIDENCE_THRESHOLD}: {above*100:.1f}% (이 비율만 실제 예측에 활용됨)")

    return pipeline


def main():
    df = load_training_data()
    model = train(df)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"\n모델 저장 완료: {MODEL_PATH}")

    # 기타/미분류 적용 시뮬레이션
    from src.preprocess.classify_agency import classify_item_detail as rule_classify
    full_df = pd.read_csv(DATA_PATH, encoding="utf-8-sig", low_memory=False)
    full_df["_label"] = full_df["bid_title"].fillna("").apply(rule_classify)
    unclassified = full_df[full_df["_label"] == EXCLUDE_LABEL]["bid_title"].fillna("").tolist()

    if unclassified:
        proba = model.predict_proba(unclassified)
        max_proba = proba.max(axis=1)
        classes = model.classes_
        preds = [classes[p.argmax()] if p.max() >= CONFIDENCE_THRESHOLD else EXCLUDE_LABEL
                 for p in proba]

        rescued = sum(1 for p in preds if p != EXCLUDE_LABEL)
        print(f"\n기타/미분류 {len(unclassified):,}건 중 ML 재분류 가능: {rescued:,}건 ({rescued/len(unclassified)*100:.1f}%)")
        print("→ 예상 최종 기타/미분류 비율: "
              f"{(len(unclassified) - rescued) / len(full_df) * 100:.1f}%")

        # 재분류 결과 샘플
        print("\n재분류 샘플 (상위 10건):")
        for title, pred in zip(unclassified[:10], preds[:10]):
            print(f"  [{pred}] {title[:60]}")


if __name__ == "__main__":
    main()
