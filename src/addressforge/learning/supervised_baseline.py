from __future__ import annotations

import json
import os
import pickle
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import logsumexp

from addressforge.core.common import canonicalize_unit_number, create_run, fetch_all, finish_run
from addressforge.core.config import ADDRESSFORGE_MODEL_ARTIFACT_DIR, ADDRESSFORGE_WORKSPACE_NAME

DECISION_LABELS = ("accept", "review", "reject")

_CATEGORICAL_FEATURES = (
    "pattern",
    "unit_source",
    "decision_reason",
    "task_type",
    "sample_pool",
)

_NUMERIC_FEATURES = (
    "confidence",
    "reference_score",
    "reference_candidate_count",
    "reference_has_unit_hint",
    "gps_conflict",
    "parser_disagreement",
    "street_number_present",
    "street_name_present",
    "unit_present",
    "explicit_unit_hint",
    "residential_unit_hint",
    "commercial_unit_hint",
    "geographic_modifier_only",
    "double_number_pattern",
    "bare_trailing_unit_city_pattern",
    "numbered_road_name",
    "building_type_multi_unit",
    "building_type_commercial",
    "raw_text_length",
)


def _artifact_dir() -> Path:
    return Path(os.getenv("ADDRESSFORGE_MODEL_ARTIFACT_DIR", ADDRESSFORGE_MODEL_ARTIFACT_DIR)).expanduser()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def _extract_sample_pool(notes: Any) -> str:
    notes_text = str(notes or "")
    marker = "[sample_pool="
    start = notes_text.lower().find(marker)
    if start < 0:
        return ""
    remainder = notes_text[start + len(marker) :]
    end = remainder.find("]")
    if end < 0:
        return ""
    return remainder[:end].strip().lower()


def _normalize_task_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized.startswith(("calibration_", "unit_boost_", "hard_correction_")):
        return "review"
    return normalized or "unknown"


def _reference_candidate_count(reference_json: dict[str, Any]) -> int:
    for key in ("candidates", "matches", "reference_candidates"):
        value = reference_json.get(key)
        if isinstance(value, list):
            return len(value)
    return 0


def _reference_has_unit_hint(reference_json: dict[str, Any]) -> int:
    candidates = reference_json.get("candidates")
    if not isinstance(candidates, list):
        candidates = reference_json.get("matches")
    if not isinstance(candidates, list):
        return 0
    for item in candidates:
        if not isinstance(item, dict):
            continue
        if canonicalize_unit_number(item.get("unit_number")):
            return 1
        if canonicalize_unit_number((item.get("canonical") or {}).get("unit_number")):
            return 1
    return 0


def _normalize_label_decision(label_json: dict[str, Any]) -> str:
    decision = str(label_json.get("decision") or "").strip().lower()
    if decision == "correct":
        return "accept"
    return decision


def _extract_decision_training_feature_row(row: dict[str, Any]) -> dict[str, Any] | None:
    label_json = _json_dict(row.get("label_json"))
    gold_decision = _normalize_label_decision(label_json)
    if gold_decision not in DECISION_LABELS:
        return None

    validation_json = _json_dict(row.get("validation_json"))
    parser_json = _json_dict(row.get("parser_json"))
    reference_json = _json_dict(row.get("reference_json"))
    hints = validation_json.get("hints") if isinstance(validation_json.get("hints"), dict) else {}
    best_candidate = parser_json.get("best_candidate") if isinstance(parser_json.get("best_candidate"), dict) else {}
    parsed = best_candidate.get("parsed") if isinstance(best_candidate.get("parsed"), dict) else {}
    feature_vector = parsed.get("feature_vector") if isinstance(parsed.get("feature_vector"), dict) else {}
    building_type = str(
        label_json.get("building_type")
        or label_json.get("structure_type")
        or row.get("building_type")
        or ""
    ).strip().lower()
    raw_text = str(row.get("raw_address_text") or "")

    features: dict[str, Any] = {
        "label": gold_decision,
        "source_id": str(row.get("source_id") or ""),
        "raw_address_text": raw_text,
        "current_decision": str(row.get("decision") or "").strip().lower(),
        "pattern": str(feature_vector.get("pattern") or parsed.get("unit_source") or "").strip().lower(),
        "unit_source": str(parsed.get("unit_source") or "").strip().lower(),
        "decision_reason": str(validation_json.get("reason") or "").strip().lower(),
        "task_type": _normalize_task_type(row.get("task_type")),
        "sample_pool": _extract_sample_pool(row.get("notes")),
        "confidence": _safe_float(validation_json.get("confidence"), 0.0),
        "reference_score": _safe_float(hints.get("reference_score"), 0.0),
        "reference_candidate_count": float(_reference_candidate_count(reference_json)),
        "reference_has_unit_hint": float(_reference_has_unit_hint(reference_json)),
        "gps_conflict": 1.0 if bool(hints.get("gps_conflict")) else 0.0,
        "parser_disagreement": 1.0 if bool(hints.get("parser_disagreement")) else 0.0,
        "street_number_present": 1.0 if str(parsed.get("street_number") or "").strip() else 0.0,
        "street_name_present": 1.0 if str(parsed.get("street_name") or "").strip() else 0.0,
        "unit_present": 1.0 if canonicalize_unit_number(parsed.get("unit_number")) else 0.0,
        "explicit_unit_hint": 1.0 if bool(feature_vector.get("has_explicit_unit_hint")) else 0.0,
        "residential_unit_hint": 1.0 if bool(feature_vector.get("has_residential_unit_hint")) else 0.0,
        "commercial_unit_hint": 1.0 if bool(feature_vector.get("has_commercial_unit_hint") or feature_vector.get("is_commercial")) else 0.0,
        "geographic_modifier_only": 1.0 if bool(feature_vector.get("has_geographic_modifier_only")) else 0.0,
        "double_number_pattern": 1.0 if bool(feature_vector.get("has_double_number_pattern")) else 0.0,
        "bare_trailing_unit_city_pattern": 1.0 if bool(feature_vector.get("has_bare_trailing_unit_city_pattern")) else 0.0,
        "numbered_road_name": 1.0 if bool(feature_vector.get("is_numbered_road_name")) else 0.0,
        "building_type_multi_unit": 1.0 if building_type == "multi_unit" else 0.0,
        "building_type_commercial": 1.0 if building_type == "commercial" else 0.0,
        "raw_text_length": float(len(raw_text.strip())),
    }
    return features


def collect_decision_training_dataset(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT
            g.source_id,
            g.label_json,
            g.task_type,
            g.notes,
            acr.raw_address_text,
            acr.decision,
            acr.building_type,
            acr.validation_json,
            acr.parser_json,
            acr.reference_json
        FROM gold_label g
        JOIN (
            SELECT source_id, MAX(gold_label_id) AS latest_gold_label_id
            FROM gold_label
            WHERE workspace_name = %s
              AND review_status = 'accepted'
              AND label_source = 'human'
            GROUP BY source_id
        ) latest
          ON latest.latest_gold_label_id = g.gold_label_id
        JOIN address_cleaning_result acr
          ON acr.workspace_name = g.workspace_name
         AND CAST(acr.raw_id AS CHAR) = g.source_id
        WHERE g.workspace_name = %s
          AND g.review_status = 'accepted'
          AND g.label_source = 'human'
        ORDER BY g.gold_label_id ASC
        """,
        (workspace_name, workspace_name),
    )
    dataset: list[dict[str, Any]] = []
    for row in rows:
        feature_row = _extract_decision_training_feature_row(row)
        if feature_row is not None:
            dataset.append(feature_row)
    return dataset


def _vectorize_dataset(rows: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, list[str], dict[str, list[str]]]:
    categorical_values: dict[str, list[str]] = {}
    for feature_name in _CATEGORICAL_FEATURES:
        values = sorted({str(row.get(feature_name) or "") for row in rows})
        categorical_values[feature_name] = values

    feature_names = list(_NUMERIC_FEATURES)
    for feature_name in _CATEGORICAL_FEATURES:
        for value in categorical_values[feature_name]:
            feature_names.append(f"{feature_name}={value}")

    matrix: list[list[float]] = []
    labels: list[int] = []
    label_index = {label: idx for idx, label in enumerate(DECISION_LABELS)}

    for row in rows:
        matrix_row = [_safe_float(row.get(feature_name), 0.0) for feature_name in _NUMERIC_FEATURES]
        for feature_name in _CATEGORICAL_FEATURES:
            current_value = str(row.get(feature_name) or "")
            for value in categorical_values[feature_name]:
                matrix_row.append(1.0 if current_value == value else 0.0)
        matrix.append(matrix_row)
        labels.append(label_index[str(row["label"])])

    return np.asarray(matrix, dtype=float), np.asarray(labels, dtype=int), feature_names, categorical_values


def export_decision_training_dataset(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    *,
    artifact_name: str = "decision_baseline_dataset",
) -> dict[str, Any]:
    rows = collect_decision_training_dataset(workspace_name)
    matrix, labels, feature_names, categorical_values = _vectorize_dataset(rows)
    artifact_dir = _artifact_dir()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"{workspace_name}_{artifact_name}.json"
    payload = {
        "workspace_name": workspace_name,
        "sample_count": len(rows),
        "feature_count": len(feature_names),
        "label_counts": dict(Counter(row["label"] for row in rows)),
        "feature_names": feature_names,
        "categorical_values": categorical_values,
        "rows": rows,
        "matrix_shape": [int(matrix.shape[0]), int(matrix.shape[1]) if matrix.ndim == 2 else 0],
        "labels": [DECISION_LABELS[index] for index in labels.tolist()],
    }
    artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"artifact_path": str(artifact_path), "sample_count": len(rows), "feature_count": len(feature_names)}


def _rows_to_tabular_frame(rows: list[dict[str, Any]]) -> tuple[pd.DataFrame, np.ndarray]:
    frame_rows: list[dict[str, Any]] = []
    labels: list[int] = []
    label_index = {label: idx for idx, label in enumerate(DECISION_LABELS)}
    for row in rows:
        frame_row: dict[str, Any] = {}
        for feature_name in _NUMERIC_FEATURES:
            frame_row[feature_name] = _safe_float(row.get(feature_name), 0.0)
        for feature_name in _CATEGORICAL_FEATURES:
            frame_row[feature_name] = str(row.get(feature_name) or "")
        frame_rows.append(frame_row)
        labels.append(label_index[str(row["label"])])
    return pd.DataFrame(frame_rows), np.asarray(labels, dtype=int)


def _predict_with_model_payload(
    model_payload: dict[str, Any],
    rows: list[dict[str, Any]],
) -> tuple[np.ndarray, list[str]]:
    model_type = str(model_payload.get("model_type") or "")
    present_labels = list(model_payload.get("present_labels") or [])
    if not present_labels:
        present_labels = [label for label in DECISION_LABELS if label in {str(row["label"]) for row in rows}]
    if model_type == "catboost":
        frame, _ = _rows_to_tabular_frame(rows)
        feature_names = list(model_payload.get("feature_names") or [*list(_NUMERIC_FEATURES), *list(_CATEGORICAL_FEATURES)])
        estimator = model_payload["estimator"]
        preds = np.asarray(estimator.predict(frame[feature_names]), dtype=int).reshape(-1)
        return preds, present_labels
    matrix, _labels, _feature_names, _categorical_values = _vectorize_dataset(rows)
    preds = _predict_with_softmax_model(model_payload, matrix)
    return preds, present_labels


def compare_decision_baseline_against_current(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    *,
    model_name: str = "decision_supervised_baseline",
    model_version: str = "v1",
    artifact_name: str = "decision_baseline_compare",
    example_limit: int = 25,
) -> dict[str, Any]:
    metadata_path = _artifact_dir() / f"{workspace_name}_{model_name}_{model_version}.json"
    model_path = _artifact_dir() / f"{workspace_name}_{model_name}_{model_version}.pkl"
    if not metadata_path.exists() or not model_path.exists():
        raise FileNotFoundError(f"Baseline artifacts not found for {workspace_name}:{model_name}:{model_version}")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    with model_path.open("rb") as fh:
        model_payload = pickle.load(fh)
    rows = collect_decision_training_dataset(workspace_name)
    pred_indices, present_labels = _predict_with_model_payload(model_payload, rows)
    gold_indices = np.asarray([present_labels.index(str(row["label"])) for row in rows], dtype=int)
    model_predictions = [present_labels[int(index)] for index in pred_indices.tolist()]
    heuristic_predictions = [str(row.get("current_decision") or "").strip().lower() or "unknown" for row in rows]
    heuristic_indices = np.asarray(
        [present_labels.index(pred) if pred in present_labels else -1 for pred in heuristic_predictions],
        dtype=int,
    )

    model_accuracy = round(float(np.mean(pred_indices == gold_indices)), 4)
    model_macro_f1 = _macro_f1(gold_indices, pred_indices, len(present_labels))
    valid_heuristic_mask = heuristic_indices >= 0
    heuristic_accuracy = round(float(np.mean(heuristic_indices[valid_heuristic_mask] == gold_indices[valid_heuristic_mask])), 4) if np.any(valid_heuristic_mask) else 0.0
    heuristic_macro_f1 = _macro_f1(gold_indices[valid_heuristic_mask], heuristic_indices[valid_heuristic_mask], len(present_labels)) if np.any(valid_heuristic_mask) else 0.0

    disagreements: list[dict[str, Any]] = []
    for row, model_pred, heuristic_pred in zip(rows, model_predictions, heuristic_predictions):
        if model_pred == heuristic_pred:
            continue
        disagreements.append(
            {
                "source_id": row.get("source_id"),
                "raw_address_text": row.get("raw_address_text"),
                "gold_label": row.get("label"),
                "model_prediction": model_pred,
                "heuristic_prediction": heuristic_pred,
                "pattern": row.get("pattern"),
                "decision_reason": row.get("decision_reason"),
                "confidence": row.get("confidence"),
            }
        )
        if len(disagreements) >= example_limit:
            break

    payload = {
        "workspace_name": workspace_name,
        "model_name": model_name,
        "model_version": model_version,
        "model_type": metadata.get("model_type"),
        "sample_count": len(rows),
        "present_labels": present_labels,
        "model_accuracy": model_accuracy,
        "model_macro_f1": model_macro_f1,
        "heuristic_accuracy": heuristic_accuracy,
        "heuristic_macro_f1": heuristic_macro_f1,
        "disagreement_examples": disagreements,
    }
    artifact_path = _artifact_dir() / f"{workspace_name}_{artifact_name}_{model_version}.json"
    artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"artifact_path": str(artifact_path), **payload}


def run_decision_baseline_pipeline(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    *,
    model_name: str = "decision_supervised_baseline",
    model_version: str = "v1",
) -> dict[str, Any]:
    balance = summarize_decision_training_dataset_balance(
        workspace_name,
        artifact_name=f"{model_name}_{model_version}_balance",
    )
    dataset = export_decision_training_dataset(
        workspace_name,
        artifact_name=f"{model_name}_{model_version}_dataset",
    )
    training = train_decision_baseline(
        workspace_name,
        model_name=model_name,
        model_version=model_version,
    )
    comparison = compare_decision_baseline_against_current(
        workspace_name,
        model_name=model_name,
        model_version=model_version,
        artifact_name=f"{model_name}_compare",
    )
    payload = {
        "workspace_name": workspace_name,
        "model_name": model_name,
        "model_version": model_version,
        "balance": balance,
        "dataset": dataset,
        "training": training,
        "comparison": comparison,
    }
    artifact_path = _artifact_dir() / f"{workspace_name}_{model_name}_{model_version}_pipeline.json"
    artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"artifact_path": str(artifact_path), **payload}


def summarize_decision_training_dataset_balance(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    *,
    artifact_name: str = "decision_baseline_balance",
) -> dict[str, Any]:
    rows = collect_decision_training_dataset(workspace_name)
    label_counts = Counter(str(row["label"]) for row in rows)
    task_type_counts = Counter(str(row.get("task_type") or "") for row in rows)
    sample_pool_counts = Counter(str(row.get("sample_pool") or "") for row in rows if str(row.get("sample_pool") or ""))
    sample_count = len(rows)
    label_ratios = {
        label: round(float(count / sample_count), 4) if sample_count else 0.0
        for label, count in sorted(label_counts.items())
    }
    minority_ratio = min(label_ratios.values()) if label_ratios else 0.0
    warnings: list[str] = []
    if label_counts.get("review", 0) < 20:
        warnings.append("review_label_count_is_low")
    if label_counts.get("reject", 0) == 0:
        warnings.append("reject_label_count_is_zero")
    if minority_ratio < 0.05:
        warnings.append("decision_label_distribution_is_highly_imbalanced")

    payload = {
        "workspace_name": workspace_name,
        "sample_count": sample_count,
        "label_counts": dict(label_counts),
        "label_ratios": label_ratios,
        "task_type_counts": dict(task_type_counts),
        "sample_pool_counts": dict(sample_pool_counts),
        "warnings": warnings,
    }
    artifact_dir = _artifact_dir()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"{workspace_name}_{artifact_name}.json"
    artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"artifact_path": str(artifact_path), **payload}


def _macro_f1(y_true: np.ndarray, y_pred: np.ndarray, class_count: int) -> float:
    scores: list[float] = []
    for label_index in range(class_count):
        tp = int(np.sum((y_true == label_index) & (y_pred == label_index)))
        fp = int(np.sum((y_true != label_index) & (y_pred == label_index)))
        fn = int(np.sum((y_true == label_index) & (y_pred != label_index)))
        precision = 0.0 if (tp + fp) <= 0 else tp / (tp + fp)
        recall = 0.0 if (tp + fn) <= 0 else tp / (tp + fn)
        score = 0.0 if (precision + recall) <= 0 else (2.0 * precision * recall) / (precision + recall)
        scores.append(score)
    return round(float(sum(scores) / max(len(scores), 1)), 4)


def _per_label_metrics(y_true: np.ndarray, y_pred: np.ndarray, label_names: list[str]) -> dict[str, dict[str, float]]:
    metrics: dict[str, dict[str, float]] = {}
    for label_index, label_name in enumerate(label_names):
        tp = int(np.sum((y_true == label_index) & (y_pred == label_index)))
        fp = int(np.sum((y_true != label_index) & (y_pred == label_index)))
        fn = int(np.sum((y_true == label_index) & (y_pred != label_index)))
        support = int(np.sum(y_true == label_index))
        precision = 0.0 if (tp + fp) <= 0 else tp / (tp + fp)
        recall = 0.0 if (tp + fn) <= 0 else tp / (tp + fn)
        f1 = 0.0 if (precision + recall) <= 0 else (2.0 * precision * recall) / (precision + recall)
        metrics[label_name] = {
            "support": support,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }
    return metrics


def _confusion_matrix(y_true: np.ndarray, y_pred: np.ndarray, class_count: int) -> list[list[int]]:
    matrix = [[0 for _ in range(class_count)] for _ in range(class_count)]
    for truth, pred in zip(y_true.tolist(), y_pred.tolist()):
        matrix[int(truth)][int(pred)] += 1
    return matrix


def _train_softmax_baseline(
    X_train: np.ndarray,
    y_train: np.ndarray,
    *,
    class_count: int,
) -> dict[str, Any]:
    if X_train.ndim != 2:
        raise ValueError("X_train must be a 2D matrix.")
    feature_count = int(X_train.shape[1])
    y_onehot = np.eye(class_count, dtype=float)[y_train]
    class_counter = Counter(int(item) for item in y_train.tolist())
    class_weights = np.asarray(
        [
            float(len(y_train)) / max(float(class_count * class_counter.get(class_index, 1)), 1.0)
            for class_index in range(class_count)
        ],
        dtype=float,
    )
    sample_weights = class_weights[y_train].reshape(-1, 1)

    def _loss(flat_params: np.ndarray) -> tuple[float, np.ndarray]:
        weight_size = feature_count * class_count
        weights = flat_params[:weight_size].reshape(feature_count, class_count)
        bias = flat_params[weight_size:].reshape(1, class_count)
        logits = X_train @ weights + bias
        log_probs = logits - logsumexp(logits, axis=1, keepdims=True)
        probs = np.exp(log_probs)
        loss = -np.sum(sample_weights * y_onehot * log_probs) / max(float(np.sum(sample_weights)), 1.0)
        loss += 0.001 * float(np.sum(weights * weights))

        grad_logits = (sample_weights * (probs - y_onehot)) / max(float(np.sum(sample_weights)), 1.0)
        grad_w = X_train.T @ grad_logits + (0.002 * weights)
        grad_b = np.sum(grad_logits, axis=0, keepdims=True)
        grad = np.concatenate([grad_w.reshape(-1), grad_b.reshape(-1)])
        return float(loss), grad

    initial = np.zeros(feature_count * class_count + class_count, dtype=float)
    result = minimize(
        fun=lambda params: _loss(params)[0],
        x0=initial,
        jac=lambda params: _loss(params)[1],
        method="L-BFGS-B",
        options={"maxiter": 1000},
    )
    if not result.success:
        raise RuntimeError(f"Softmax baseline training failed: {result.message}")

    weight_size = feature_count * class_count
    weights = result.x[:weight_size].reshape(feature_count, class_count)
    bias = result.x[weight_size:]
    return {
        "model_type": "softmax_regression",
        "weights": weights,
        "bias": bias,
        "iterations": int(result.nit),
        "final_loss": round(float(result.fun), 6),
    }


def _predict_with_softmax_model(model_payload: dict[str, Any], X: np.ndarray) -> np.ndarray:
    feature_mean = np.asarray(model_payload.get("feature_mean") or np.zeros(X.shape[1]), dtype=float)
    feature_std = np.asarray(model_payload.get("feature_std") or np.ones(X.shape[1]), dtype=float)
    X_scaled = (X - feature_mean) / feature_std
    weights = np.asarray(model_payload["weights"], dtype=float)
    bias = np.asarray(model_payload["bias"], dtype=float).reshape(1, -1)
    logits = X_scaled @ weights + bias
    return np.argmax(logits, axis=1)


def train_decision_baseline(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    *,
    model_name: str = "decision_supervised_baseline",
    model_version: str = "v1",
) -> dict[str, Any]:
    rows = collect_decision_training_dataset(workspace_name)
    if len(rows) < 20:
        raise ValueError("Not enough accepted human-gold rows to train a decision baseline.")

    matrix, labels, feature_names, categorical_values = _vectorize_dataset(rows)
    tabular_frame, _ = _rows_to_tabular_frame(rows)
    catboost_feature_names = [*list(_NUMERIC_FEATURES), *list(_CATEGORICAL_FEATURES)]
    present_label_indices = sorted(set(int(index) for index in labels.tolist()))
    if len(present_label_indices) < 2:
        raise ValueError("Decision baseline needs at least two decision labels in accepted human gold.")
    present_labels = [DECISION_LABELS[index] for index in present_label_indices]
    label_remap = {old_index: new_index for new_index, old_index in enumerate(present_label_indices)}
    remapped_labels = np.asarray([label_remap[int(index)] for index in labels.tolist()], dtype=int)
    indices = np.arange(len(rows))
    eval_mask = (indices % 5) == 0
    if int(np.sum(eval_mask)) < 5 or int(np.sum(~eval_mask)) < 10:
        eval_mask = np.zeros(len(rows), dtype=bool)
        eval_mask[-max(5, len(rows) // 5) :] = True

    X_train = matrix[~eval_mask]
    y_train = remapped_labels[~eval_mask]
    X_eval = matrix[eval_mask]
    y_eval = remapped_labels[eval_mask]
    frame_train = tabular_frame.iloc[~eval_mask].reset_index(drop=True)
    frame_eval = tabular_frame.iloc[eval_mask].reset_index(drop=True)
    feature_mean = np.mean(X_train, axis=0)
    feature_std = np.std(X_train, axis=0)
    feature_std = np.where(feature_std <= 1e-8, 1.0, feature_std)
    X_train_scaled = (X_train - feature_mean) / feature_std
    X_eval_scaled = (X_eval - feature_mean) / feature_std

    run_id = create_run(
        "ml_train",
        notes=f"decision baseline {workspace_name}:{model_name}:{model_version}",
    )
    try:
        model_payload: dict[str, Any]
        fallback_reason = ""
        try:
            from catboost import CatBoostClassifier, Pool

            model = CatBoostClassifier(
                loss_function="MultiClass",
                iterations=300,
                depth=6,
                learning_rate=0.08,
                random_seed=42,
                auto_class_weights="Balanced",
                verbose=False,
            )
            train_pool = Pool(
                frame_train[catboost_feature_names],
                y_train,
                cat_features=list(_CATEGORICAL_FEATURES),
            )
            model.fit(train_pool)
            train_pred = np.asarray(model.predict(frame_train[catboost_feature_names]), dtype=int).reshape(-1)
            eval_pred = np.asarray(model.predict(frame_eval[catboost_feature_names]), dtype=int).reshape(-1)
            feature_importance = model.get_feature_importance(
                data=train_pool,
                prettified=False,
            )
            model_payload = {
                "model_type": "catboost",
                "estimator": model,
                "feature_names": catboost_feature_names,
                "categorical_feature_names": list(_CATEGORICAL_FEATURES),
                "feature_importance": {
                    name: round(float(score), 6)
                    for name, score in zip(catboost_feature_names, feature_importance.tolist())
                },
            }
        except Exception as exc:
            fallback_reason = f"catboost_unavailable_or_failed: {exc}"
            softmax_model = _train_softmax_baseline(X_train_scaled, y_train, class_count=len(present_labels))
            softmax_model["feature_mean"] = feature_mean.tolist()
            softmax_model["feature_std"] = feature_std.tolist()
            train_pred = _predict_with_softmax_model(softmax_model, X_train)
            eval_pred = _predict_with_softmax_model(softmax_model, X_eval)
            model_payload = softmax_model

        metrics = {
            "train_accuracy": round(float(np.mean(train_pred == y_train)), 4),
            "train_macro_f1": _macro_f1(y_train, train_pred, len(present_labels)),
            "eval_accuracy": round(float(np.mean(eval_pred == y_eval)), 4),
            "eval_macro_f1": _macro_f1(y_eval, eval_pred, len(present_labels)),
            "train_sample_count": int(X_train.shape[0]),
            "eval_sample_count": int(X_eval.shape[0]),
            "train_per_label": _per_label_metrics(y_train, train_pred, present_labels),
            "eval_per_label": _per_label_metrics(y_eval, eval_pred, present_labels),
            "eval_confusion_matrix": _confusion_matrix(y_eval, eval_pred, len(present_labels)),
        }

        artifact_dir = _artifact_dir()
        artifact_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = artifact_dir / f"{workspace_name}_{model_name}_{model_version}.json"
        model_path = artifact_dir / f"{workspace_name}_{model_name}_{model_version}.pkl"
        metadata = {
            "workspace_name": workspace_name,
            "model_name": model_name,
            "model_version": model_version,
            "sample_count": len(rows),
            "feature_names": feature_names,
            "categorical_values": categorical_values,
            "catboost_feature_names": catboost_feature_names,
            "label_counts": dict(Counter(row["label"] for row in rows)),
            "present_labels": present_labels,
            "model_type": model_payload.get("model_type"),
            "fallback_reason": fallback_reason,
            "feature_importance": model_payload.get("feature_importance"),
            "metrics": metrics,
        }
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        with model_path.open("wb") as fh:
            pickle.dump(model_payload, fh)
        finish_run(run_id, "completed", notes=f"eval_macro_f1={metrics['eval_macro_f1']}")
        return {
            "run_id": run_id,
            "metadata_path": str(metadata_path),
            "model_path": str(model_path),
            "model_type": model_payload.get("model_type"),
            "metrics": metrics,
        }
    except Exception as exc:
        finish_run(run_id, "failed", notes=str(exc))
        raise


__all__ = [
    "DECISION_LABELS",
    "compare_decision_baseline_against_current",
    "collect_decision_training_dataset",
    "export_decision_training_dataset",
    "run_decision_baseline_pipeline",
    "summarize_decision_training_dataset_balance",
    "train_decision_baseline",
    "_extract_decision_training_feature_row",
    "_vectorize_dataset",
]
