"""Learning package."""

from .evaluator import run_baseline_evaluation
from .gold import (
    count_active_learning_queue,
    count_gold_labels,
    freeze_gold_set,
    list_active_learning_queue,
    list_gold_labels,
    list_gold_snapshots,
    seed_active_learning_queue,
    seed_active_learning_from_errors,
    seed_apartment_unit_hard_samples,
    seed_decision_calibration_review_queue,
    seed_decision_minority_label_review_queue,
    seed_label_consistency_relabel_queue,
    seed_semantic_disambiguation_review_queue,
    seed_unit_commercial_review_queue,
    upsert_gold_label,
)
from .shadow import run_baseline_shadow
from .supervised_baseline import (
    build_decision_inference_feature_row,
    build_decision_inference_frame,
    compare_decision_baseline_against_current,
    export_decision_training_dataset,
    run_decision_baseline_pipeline,
    summarize_decision_training_dataset_balance,
    train_decision_baseline,
)
from .trainer import run_baseline_training

__all__ = [
    "run_baseline_training",
    "run_baseline_evaluation",
    "run_baseline_shadow",
    "build_decision_inference_feature_row",
    "build_decision_inference_frame",
    "compare_decision_baseline_against_current",
    "export_decision_training_dataset",
    "run_decision_baseline_pipeline",
    "summarize_decision_training_dataset_balance",
    "train_decision_baseline",
    "upsert_gold_label",
    "list_gold_labels",
    "list_gold_snapshots",
    "freeze_gold_set",
    "seed_active_learning_queue",
    "seed_active_learning_from_errors",
    "seed_apartment_unit_hard_samples",
    "seed_decision_calibration_review_queue",
    "seed_decision_minority_label_review_queue",
    "seed_label_consistency_relabel_queue",
    "seed_semantic_disambiguation_review_queue",
    "seed_unit_commercial_review_queue",
    "list_active_learning_queue",
    "count_gold_labels",
    "count_active_learning_queue",
]
