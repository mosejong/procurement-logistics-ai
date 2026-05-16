"""
공고명 → item_category_detail ML 추론 모듈

학습된 TF-IDF + LogisticRegression 모델을 로드해 카테고리를 예측합니다.
키워드 규칙이 '기타/미분류'를 반환한 경우에만 이 모듈이 개입합니다.

모델 파일: models/item_classifier.pkl  (train_classifier.py로 생성)
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "item_classifier.pkl"

_model = None
_model_lock = threading.Lock()
_load_attempted = False


def _load_model():
    """모델을 한 번만 로드합니다 (thread-safe lazy load)."""
    global _model, _load_attempted
    if _load_attempted:
        return
    with _model_lock:
        if _load_attempted:
            return
        _load_attempted = True
        if not MODEL_PATH.exists():
            return
        try:
            import joblib
            _model = joblib.load(MODEL_PATH)
        except Exception:
            _model = None


def is_available() -> bool:
    """모델이 로드 가능한 상태인지 확인합니다."""
    _load_model()
    return _model is not None


def predict(text: str, confidence_threshold: float = 0.55) -> Optional[str]:
    """
    공고명 텍스트로 카테고리를 예측합니다.

    confidence_threshold 미만이면 None 반환 → 키워드 규칙 fallback 유지.
    """
    _load_model()
    if _model is None or not text or not text.strip():
        return None
    try:
        proba = _model.predict_proba([text])[0]
        max_idx = proba.argmax()
        confidence = proba[max_idx]
        if confidence < confidence_threshold:
            return None
        return _model.classes_[max_idx]
    except Exception:
        return None
