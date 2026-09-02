"""
Tests for the prediction package.

Verifies:
  1. All prediction modules can be imported without side effects.
  2. Detector correctly identifies binary classification problems.
  3. Preprocessing produces valid train/test splits.
  4. Full train → predict pipeline works end-to-end.
  5. Existing SQL pipeline is NOT affected.
"""

import os
import sys
import sqlite3
import tempfile

import numpy as np
import pandas as pd
import pytest

# Ensure the backend directory is on the path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def churn_dataframe():
    """Create a small synthetic churn dataset as a DataFrame."""
    np.random.seed(42)
    n = 200
    return pd.DataFrame({
        "RowNumber": range(1, n + 1),
        "CustomerId": np.random.randint(10000000, 99999999, size=n),
        "Surname": [f"Name_{i}" for i in range(n)],
        "CreditScore": np.random.randint(300, 850, size=n),
        "Geography": np.random.choice(["France", "Germany", "Spain"], size=n),
        "Gender": np.random.choice(["Male", "Female"], size=n),
        "Age": np.random.randint(18, 92, size=n),
        "Tenure": np.random.randint(0, 10, size=n),
        "Balance": np.random.uniform(0, 250000, size=n).round(2),
        "NumOfProducts": np.random.randint(1, 5, size=n),
        "HasCrCard": np.random.choice([0, 1], size=n),
        "IsActiveMember": np.random.choice([0, 1], size=n),
        "EstimatedSalary": np.random.uniform(10000, 200000, size=n).round(2),
        "Exited": np.random.choice([0, 1], size=n, p=[0.8, 0.2]),
    })


@pytest.fixture
def churn_table_in_db(churn_dataframe, temp_database):
    """Write the synthetic churn data into a temp SQLite database."""
    conn = sqlite3.connect(temp_database)
    churn_dataframe.to_sql("churn_modelling", conn, index=False, if_exists="replace")
    conn.close()
    return "churn_modelling"


# ─────────────────────────────────────────────────────────────
# 1. Import tests — prediction package must not crash on import
# ─────────────────────────────────────────────────────────────

class TestImports:
    """Verify all prediction modules can be imported cleanly."""

    def test_import_schemas(self):
        from prediction import schemas
        assert hasattr(schemas, "DetectionResult")
        assert hasattr(schemas, "PredictionResult")

    def test_import_detector(self):
        from prediction import detector
        assert callable(detector.detect)

    def test_import_preprocessing(self):
        from prediction import preprocessing
        assert callable(preprocessing.prepare_training_data)
        assert callable(preprocessing.prepare_inference_data)

    def test_import_models(self):
        from prediction import models
        assert callable(models.create_model)
        assert "random_forest" in models.MODEL_REGISTRY

    def test_import_evaluator(self):
        from prediction import evaluator
        assert callable(evaluator.evaluate)

    def test_import_trainer(self):
        from prediction import trainer
        assert callable(trainer.train_all)
        assert callable(trainer.load_artifact)

    def test_import_predictor(self):
        from prediction import predictor
        assert callable(predictor.predict)
        assert callable(predictor.find_rows_by_filter)

    def test_import_service(self):
        from prediction import service
        assert callable(service.detect_problem)
        assert callable(service.train_models)
        assert callable(service.predict_rows)

    def test_import_package(self):
        import prediction
        assert prediction is not None


# ─────────────────────────────────────────────────────────────
# 2. Detector tests
# ─────────────────────────────────────────────────────────────

class TestDetector:
    """Test prediction problem detection."""

    def test_detects_churn_target(self, churn_dataframe):
        from prediction.detector import detect
        result = detect(churn_dataframe, "churn_modelling")
        assert result.is_suitable is True
        assert result.target_column == "Exited"
        assert result.problem_type == "classification"

    def test_identifies_id_columns(self, churn_dataframe):
        from prediction.detector import detect
        result = detect(churn_dataframe, "churn_modelling")
        assert "CustomerId" in result.id_columns
        assert "RowNumber" in result.id_columns

    def test_identifies_drop_columns(self, churn_dataframe):
        from prediction.detector import detect
        result = detect(churn_dataframe, "churn_modelling")
        assert "Surname" in result.drop_columns

    def test_rejects_empty_dataframe(self):
        from prediction.detector import detect
        df = pd.DataFrame()
        result = detect(df, "empty_table")
        assert result.is_suitable is False
        assert "Insufficient" in result.reason

    def test_rejects_no_target(self):
        from prediction.detector import detect
        df = pd.DataFrame({"a": [1, 2, 3] * 20, "b": [4, 5, 6] * 20})
        result = detect(df, "no_target")
        assert result.is_suitable is False

    def test_explicit_target_hint(self, churn_dataframe):
        from prediction.detector import detect
        result = detect(churn_dataframe, "test", target_hint="Exited")
        assert result.target_column == "Exited"


# ─────────────────────────────────────────────────────────────
# 3. Preprocessing tests
# ─────────────────────────────────────────────────────────────

class TestPreprocessing:
    """Test feature preparation."""

    def test_prepare_training_data(self, churn_dataframe):
        from prediction.detector import detect
        from prediction.preprocessing import prepare_training_data

        detection = detect(churn_dataframe, "test")
        prepared, preprocessor = prepare_training_data(churn_dataframe, detection)

        assert len(prepared.X_train) > 0
        assert len(prepared.X_test) > 0
        assert len(prepared.feature_names) > 0
        # ID and surname columns should not be in features
        for fname in prepared.feature_names:
            assert "customerid" not in fname.lower()
            assert "surname" not in fname.lower()
            assert "rownumber" not in fname.lower()

    def test_no_nan_in_output(self, churn_dataframe):
        from prediction.detector import detect
        from prediction.preprocessing import prepare_training_data
        import numpy as np

        # Introduce some NaNs to test imputation
        churn_dataframe.loc[0, "CreditScore"] = np.nan
        churn_dataframe.loc[1, "Geography"] = np.nan
        
        detection = detect(churn_dataframe, "test")
        prepared, preprocessor = prepare_training_data(churn_dataframe, detection)

        assert not np.isnan(prepared.X_train).any()
        assert not np.isnan(prepared.X_test).any()


# ─────────────────────────────────────────────────────────────
# 4. End-to-end pipeline test
# ─────────────────────────────────────────────────────────────

class TestEndToEnd:
    """Full train → predict pipeline on synthetic data."""

    def test_train_and_predict(self, churn_dataframe):
        from prediction.detector import detect
        from prediction.preprocessing import prepare_training_data
        from prediction.models import create_model
        from prediction.evaluator import evaluate
        from prediction.predictor import predict
        from prediction.schemas import TrainedModelArtifact

        detection = detect(churn_dataframe, "test")
        prepared, preprocessor = prepare_training_data(churn_dataframe, detection)

        model = create_model()
        model.fit(prepared.X_train, prepared.y_train)

        # Evaluate
        eval_result = evaluate(model, prepared.X_test, prepared.y_test)
        assert eval_result.accuracy > 0  # It's random data, just check it runs
        assert 0 <= eval_result.roc_auc <= 1

        # Build artifact manually (without saving to disk)
        importances = list(zip(
            prepared.feature_names,
            [round(float(v), 4) for v in model.feature_importances_],
        ))
        artifact = TrainedModelArtifact(
            model=model,
            preprocessor=preprocessor,
            feature_names=prepared.feature_names,
            target_column=detection.target_column,
            table_name="test",
            evaluation=eval_result,
            feature_importances=sorted(importances, key=lambda x: x[1], reverse=True),
        )

        # Predict on first 3 rows
        result = predict(churn_dataframe, artifact, row_indices=[0, 1, 2])
        assert result.count == 3
        for pred in result.predictions:
            assert pred.prediction in (0, 1)
            assert 0 <= pred.probability <= 1
            assert pred.risk in ("Low", "Medium", "High")
            assert len(pred.feature_impacts) > 0

    def test_train_all_models(self, churn_dataframe):
        from prediction.trainer import train_all

        # This will train all models in the MODEL_REGISTRY and save them to disk
        experiment = train_all(churn_dataframe, "test", selection_metric="roc_auc")

        assert len(experiment.models) == 3
        assert len(experiment.training_results) == 3
        assert experiment.best_model_key is not None
        assert experiment.selection_metric == "roc_auc"

        # Check the results format
        results_by_key = {r["model_key"]: r for r in experiment.training_results}
        for key in ["logistic_regression", "random_forest", "gradient_boosting"]:
            assert key in results_by_key
            res = results_by_key[key]
            assert res["training_status"] == "SUCCESS"
            assert res["prediction_capability"] is True
            assert res["probability_capability"] is True
            assert 0 <= res["accuracy"] <= 1
            assert 0 <= res["roc_auc"] <= 1
            assert "confusion_matrix" in res

    def test_model_selection_and_loading(self, churn_dataframe):
        from prediction.trainer import train_all, load_artifact
        from prediction.detector import detect

        detection = detect(churn_dataframe, "test")
        
        # Train and select best based on f1_score
        experiment = train_all(churn_dataframe, "test", target_col=detection.target_column, selection_metric="f1_score")
        
        best_key = experiment.best_model_key
        assert best_key is not None
        
        # Verify the saved model can be loaded
        loaded_artifact = load_artifact("test", detection.target_column)
        assert loaded_artifact is not None
        
        # It should be the best model type
        results_by_key = {r["model_key"]: r for r in experiment.training_results}
        best_model_name = results_by_key[best_key]["model_name"]
        assert loaded_artifact.model_type == best_model_name
        
        # Loaded model should produce valid predictions
        from prediction.predictor import predict
        result = predict(churn_dataframe, loaded_artifact, row_indices=[0, 1])
        assert result.count == 2
        assert len(result.predictions) == 2


# ─────────────────────────────────────────────────────────────
# 5. Non-interference test
# ─────────────────────────────────────────────────────────────

class TestNonInterference:
    """Verify prediction does not interfere with the existing SQL pipeline."""

    def test_sql_validator_still_works(self, temp_database):
        """The existing SQL validator must still function normally."""
        conn = sqlite3.connect(temp_database)
        conn.execute("CREATE TABLE sales (name TEXT, amount REAL)")
        conn.execute("INSERT INTO sales VALUES ('Widget', 100)")
        conn.commit()
        conn.close()

        from agents.validator import run as validate
        result = validate("SELECT name, amount FROM sales;")
        assert result["valid"] is True

    def test_router_classifies_analytical_correctly(self):
        """BI/SQL questions must route to ANALYTICAL."""
        from agents.router import run as route
        
        analytical_queries = [
            "Show total sales by country",
            "What is the average order size?",
            "What was the revenue last year?",
            "What are my top products?",
            "Which product has the highest sales?",
            "How many customers do we have?",
            "Show revenue by country",
            "What is total revenue?",
            "Compare Q1 and Q2 performance",
            "What is the average credit score?",
            "How many products does each customer have?",
            "Show me the balance distribution",
        ]
        for q in analytical_queries:
            result = route(q)
            assert result == "ANALYTICAL", f"Query '{q}' was misrouted as {result}"

    def test_router_classifies_prediction_correctly(self):
        """Prediction questions must route to PREDICTIVE."""
        from agents.router import run as route
        
        predictive_queries = [
            # Direct
            "Will customer 123 churn?",
            "Predict churn for this user",
            "Predict customer churn",
            # Probabilistic language
            "Which customers are likely to churn?",
            "Who is most likely to leave?",
            "What is the probability this customer will leave?",
            # Risk language
            "Which customers are at high risk of leaving?",
            "Show high risk customers",
            "Find customers at risk of churning",
            # Natural phrasing
            "Who might leave soon?",
            "Identify customers about to exit",
            "List customers likely to cancel",
            # Retention / attrition
            "Who should we focus on for retention?",
            "Show the attrition forecast",
        ]
        for q in predictive_queries:
            result = route(q)
            assert result == "PREDICTIVE", f"Query '{q}' was misrouted as {result}"

    def test_app_imports_without_error(self):
        """The main FastAPI app must still import cleanly."""
        from main import app
        assert app is not None
        assert app.title == "Agentic AI BI System"

# ─────────────────────────────────────────────────────────────
# 6. Predictor tests (STEP 7 specific)
# ─────────────────────────────────────────────────────────────

class TestPredictor:
    """Detailed tests for the prediction service output formatting and logic."""

    @pytest.fixture(autouse=True)
    def mock_load_table(self, monkeypatch, churn_dataframe):
        """Mock _load_table to avoid database dependency in Predictor tests."""
        import prediction.service
        
        # We also need a version that can return the corrupted df for that one test
        self.mock_df = churn_dataframe.copy()
        
        def mock_loader(table_name):
            return self.mock_df
            
        monkeypatch.setattr(prediction.service, "_load_table", mock_loader)

    def test_single_and_batch_prediction(self, churn_dataframe):
        from prediction.trainer import train_all
        from prediction.service import predict_rows
        
        # Train once
        train_all(churn_dataframe, "test_pred")
        
        # Test Single Prediction (e.g. by customer ID)
        customer_id = churn_dataframe.iloc[0]["CustomerId"]
        res_single = predict_rows("test_pred", customer_id=customer_id)
        assert res_single.count == 1
        assert res_single.predictions[0].customer_id == customer_id
        
        # Test Batch Prediction
        res_batch = predict_rows("test_pred", filters={"Geography": "France"})
        assert res_batch.count > 1
        assert len(res_batch.predictions) == res_batch.count

    def test_probability_and_risk_classification(self, churn_dataframe):
        from prediction.service import predict_rows
        from prediction.trainer import train_all
        
        train_all(churn_dataframe, "test_pred_risk")
        
        # Default thresholds: High=0.75, Medium=0.45
        res = predict_rows("test_pred_risk")
        for p in res.predictions:
            assert 0.0 <= p.probability <= 1.0
            if p.probability >= 0.75:
                assert p.risk == "High"
            elif p.probability >= 0.45:
                assert p.risk == "Medium"
            else:
                assert p.risk == "Low"

        # Custom configurable thresholds
        custom_thresholds = {"High": 0.9, "Medium": 0.5}
        res_custom = predict_rows("test_pred_risk", risk_thresholds=custom_thresholds)
        for p in res_custom.predictions:
            if p.probability >= 0.9:
                assert p.risk == "High"
            elif p.probability >= 0.5:
                assert p.risk == "Medium"
            else:
                assert p.risk == "Low"

    def test_ranking_by_probability(self, churn_dataframe):
        from prediction.service import predict_rows
        from prediction.trainer import train_all
        
        train_all(churn_dataframe, "test_pred_rank")
        
        res = predict_rows("test_pred_rank", rank_by_probability=True)
        probs = [p.probability for p in res.predictions]
        # Ensure it is strictly descending
        assert all(probs[i] >= probs[i+1] for i in range(len(probs)-1))

    def test_missing_or_invalid_feature_handling(self, churn_dataframe):
        from prediction.trainer import train_all
        from prediction.service import predict_rows
        
        # Train on normal data
        train_all(churn_dataframe, "test_pred_missing")
        
        # Corrupt the mocked dataframe by appending a bad row
        corrupt_row = pd.DataFrame([{
            "RowNumber": 999,
            "CustomerId": 99999999,
            "Surname": "Missing",
            "CreditScore": None,       # Missing numeric
            "Geography": "Atlantis",   # Unknown category
            "Gender": None,            # Missing category
            "Age": -10,                # Invalid
            "Tenure": 5,
            "Balance": 0.0,
            "NumOfProducts": 1,
            "HasCrCard": 0,
            "IsActiveMember": 0,
            "EstimatedSalary": 0.0,
            "Exited": 0,
        }])
        self.mock_df = pd.concat([churn_dataframe, corrupt_row], ignore_index=True)
        
        # Predict on the corrupted record
        res = predict_rows("test_pred_missing", customer_id=99999999)
        assert res.count == 1
        
        # It should survive and output a valid probability/risk thanks to robust preprocessing
        pred = res.predictions[0]
        assert 0.0 <= pred.probability <= 1.0
        assert pred.risk in ("High", "Medium", "Low")
        assert pred.prediction in (0, 1)

# ─────────────────────────────────────────────────────────────
# 7. Explainability tests (STEP 10 specific)
# ─────────────────────────────────────────────────────────────

class TestExplainability:
    """Tests for the LLM explanation generation logic."""

    def test_explanation_avoids_causal_claims_in_prompt(self, monkeypatch):
        from agents import ml_agent
        from prediction.schemas import PredictionResult, PredictionRow
        
        # Mock the LLM call to just return the prompt so we can inspect it
        def mock_call_llm(prompt, expect_json=False):
            return prompt
            
        monkeypatch.setattr(ml_agent, "call_llm", mock_call_llm)
        
        # Build a dummy prediction result
        dummy_row = PredictionRow(
            customer_id=123,
            prediction=1,
            probability=0.85,
            risk="High",
            row_data={"Age": 45, "Balance": 100000},
            feature_impacts=[
                {"feature": "Age", "importance": 0.4, "value": 45},
                {"feature": "Balance", "importance": 0.3, "value": 100000},
            ]
        )
        dummy_result = PredictionResult(
            predictions=[dummy_row],
            model_accuracy=0.9,
            target_column="Exited",
            table_name="churn",
            count=1
        )
        
        prompt_output = ml_agent._generate_explanation("Will customer 123 churn?", dummy_result)
        
        # Verify the prompt strictly instructs the LLM not to make causal claims
        assert "Do NOT make causal claims" in prompt_output
        assert "Factors contributing most to this model prediction include" in prompt_output
        assert "FACTORS CONTRIBUTING TO PREDICTION:" in prompt_output
        assert "TOP FACTORS INFLUENCING" not in prompt_output

    def test_explanation_fallback_formatting(self, monkeypatch):
        from agents import ml_agent
        from prediction.schemas import PredictionResult, PredictionRow
        
        # Mock the LLM call to throw an exception to trigger the fallback
        def mock_call_llm_fail(prompt, expect_json=False):
            raise ValueError("LLM is down")
            
        monkeypatch.setattr(ml_agent, "call_llm", mock_call_llm_fail)
        
        dummy_row = PredictionRow(
            customer_id=123,
            prediction=1,
            probability=0.85,
            risk="High",
            row_data={"Age": 45, "Balance": 100000},
            feature_impacts=[
                {"feature": "Age", "importance": 0.4, "value": 45},
                {"feature": "Balance", "importance": 0.3, "value": 100000},
            ]
        )
        dummy_result = PredictionResult(
            predictions=[dummy_row],
            model_accuracy=0.9,
            target_column="Exited",
            table_name="churn",
            count=1
        )
        
        fallback_output = ml_agent._generate_explanation("Will customer 123 churn?", dummy_result)
        
        # Verify the fallback uses associative rather than causal language
        assert "Factors contributing most to this model prediction:" in fallback_output
        assert "The top factors are:" not in fallback_output
        assert "Age, Balance" in fallback_output
