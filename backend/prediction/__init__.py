"""
Prediction Package

Modular binary classification pipeline for the Voice BI system.

Public API (import from ``prediction.service``):
  - detect_problem(table_name) → DetectionResult
  - train_models(table_name)   → dict with metrics
  - predict_rows(table_name)   → PredictionResult

Internal modules:
  - detector.py      – Prediction problem detection
  - preprocessing.py – Feature engineering / encoding
  - models.py        – Model registry (estimator factories)
  - trainer.py       – Training orchestration + persistence
  - evaluator.py     – Classification metrics
  - predictor.py     – Inference engine
  - schemas.py       – Shared dataclass types
  - service.py       – High-level facade (single entry point)
"""
