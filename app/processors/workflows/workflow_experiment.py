"""
Experiment Workflow

Runs prompt optimization experiments using Opik's native evaluation API.

Two LLMs are used:
1. **Evaluation Task LLM** - The sidebar/session LLM (Gemini, Claude, Ollama, etc.)
   that runs the actual Forseti agent validation
2. **Opik Judge LLM** - OpenAI gpt-4o-mini by default (configurable in admin)
   that runs Opik's built-in metrics (Hallucination, Moderation, etc.)

Opik Built-in Metrics (LLM Judges):
- Hallucination: Detects generated false information
- Moderation: Checks adherence to content standards
- AnswerRelevance: Evaluates how well the answer fits the question
- ContextRecall: Measures retrieval of relevant context
- ContextPrecision: Measures precision of retrieved context

Custom Metrics:
- CharterCompliance: Custom metric for charter validation
- CategoryAccuracy: Custom metric for category classification

Usage:
    from app.processors.workflows import run_opik_experiment, OpikExperimentConfig

    config = OpikExperimentConfig(
        experiment_name="charter-eval-20260204",
        dataset_name="low-confidence-20260204-001",
        experiment_type="charter_optimization",
        metrics=["hallucination", "moderation"],
        task_provider="gemini",  # Sidebar LLM for Forseti
    )
    results = run_opik_experiment(config)
"""

import asyncio
from datetime import datetime
from typing import Optional, Callable

from app.services.logging import get_logger
from app.services.tasks import AGENT_FEATURE_REGISTRY, get_feature_config
from app.services.opik_config import (
    get_opik_judge_config,
    configure_opik_environment,
)

logger = get_logger("processors")


# Available Opik built-in metrics
OPIK_METRICS = {
    "hallucination": "Hallucination",
    "moderation": "Moderation",
    "answer_relevance": "AnswerRelevance",
    "context_recall": "ContextRecall",
    "context_precision": "ContextPrecision",
}


class OpikExperimentConfig:
    """Configuration for an Opik evaluation experiment."""

    def __init__(
        self,
        experiment_name: str,
        dataset_name: str,
        experiment_type: str,
        metrics: Optional[list[str]] = None,
        task_provider: str = "gemini",
        custom_task: Optional[Callable] = None,
    ):
        """
        Initialize experiment configuration.

        Args:
            experiment_name: Name for the experiment in Opik
            dataset_name: Name of the Opik dataset to evaluate
            experiment_type: Key from AGENT_FEATURE_REGISTRY
            metrics: List of metric names to use (default: ["hallucination"])
            task_provider: LLM provider for evaluation task (sidebar LLM: gemini, claude, ollama)
            custom_task: Optional custom evaluation task function

        Note:
            - task_provider: The LLM that runs the actual Forseti validation
            - Opik judge LLM: Configured separately in admin (default: OpenAI gpt-4o-mini)
        """
        self.experiment_name = experiment_name
        self.dataset_name = dataset_name
        self.experiment_type = experiment_type
        self.metrics = metrics or ["hallucination"]
        self.task_provider = task_provider
        self.custom_task = custom_task

        # Get feature config
        self.feature_config = get_feature_config(experiment_type)
        if not self.feature_config:
            raise ValueError(f"Unknown experiment type: {experiment_type}")

        # Get Opik judge config
        self.judge_config = get_opik_judge_config()

    def to_dict(self) -> dict:
        return {
            "experiment_name": self.experiment_name,
            "dataset_name": self.dataset_name,
            "experiment_type": self.experiment_type,
            "metrics": self.metrics,
            "task_provider": self.task_provider,  # Sidebar LLM for Forseti
            "judge_provider": self.judge_config.get("provider"),  # Opik judge LLM
            "judge_model": self.judge_config.get("model"),
            "feature": self.feature_config.get("feature"),
        }


def run_opik_experiment(config: OpikExperimentConfig) -> dict:
    """
    Run an experiment using Opik's native evaluate() API.

    This uses Opik's built-in LLM judge metrics and reports
    results directly to the Opik platform.

    Two LLMs:
    - Task LLM (config.task_provider): Runs Forseti validation
    - Judge LLM (from Redis db=5): Runs Opik metrics (Hallucination, etc.)

    Args:
        config: OpikExperimentConfig with experiment parameters

    Returns:
        dict with experiment results and metrics
    """
    logger.info(f"Starting Opik experiment: {config.experiment_name}")
    logger.info(f"  dataset: {config.dataset_name}")
    logger.info(f"  metrics: {config.metrics}")
    logger.info(f"  experiment_type: {config.experiment_type}")
    logger.info(f"  task_provider (Forseti): {config.task_provider}")
    logger.info(f"  judge_provider (Opik): {config.judge_config.get('provider')} / {config.judge_config.get('model')}")

    result = {
        "experiment_name": config.experiment_name,
        "dataset_name": config.dataset_name,
        "status": "pending",
        "metrics_used": config.metrics,
        "task_provider": config.task_provider,
        "judge_config": config.judge_config,
        "errors": [],
    }

    # Configure Opik judge LLM environment
    if not configure_opik_environment():
        result["errors"].append("Opik judge LLM not configured - check OPENAI_API_KEY")
        logger.warning("Opik judge LLM not configured - metrics may fail")

    try:
        from opik import Opik
        from opik.evaluation import evaluate

        # Get Opik client
        client = Opik()

        # Get dataset
        logger.info(f"  loading dataset: {config.dataset_name}")
        dataset = client.get_dataset(name=config.dataset_name)

        if not dataset:
            result["status"] = "failed"
            result["errors"].append(f"Dataset not found: {config.dataset_name}")
            return result

        # Build evaluation task
        evaluation_task = config.custom_task or _create_evaluation_task(config)

        # Build metrics list
        scoring_metrics = _build_metrics(config.metrics)
        logger.info(f"  using {len(scoring_metrics)} metrics")

        # Run evaluation
        logger.info(f"  running evaluation...")
        eval_results = evaluate(
            experiment_name=config.experiment_name,
            dataset=dataset,
            task=evaluation_task,
            scoring_metrics=scoring_metrics,
        )

        result["status"] = "success"
        result["eval_results"] = _format_eval_results(eval_results)
        logger.info(f"  experiment complete: {config.experiment_name}")

    except ImportError as e:
        result["status"] = "failed"
        result["errors"].append(f"Opik SDK not available: {e}")
        logger.error(f"Opik SDK import error: {e}")

    except Exception as e:
        result["status"] = "failed"
        result["errors"].append(str(e))
        logger.error(f"Experiment failed: {e}")

    return result


def _build_metrics(metric_names: list[str]) -> list:
    """Build list of Opik metric instances."""
    from opik.evaluation.metrics import (
        Hallucination,
        Moderation,
        AnswerRelevance,
        ContextRecall,
        ContextPrecision,
    )

    metric_classes = {
        "hallucination": Hallucination,
        "moderation": Moderation,
        "answer_relevance": AnswerRelevance,
        "context_recall": ContextRecall,
        "context_precision": ContextPrecision,
    }

    metrics = []
    for name in metric_names:
        name_lower = name.lower().replace("-", "_")
        if name_lower in metric_classes:
            metrics.append(metric_classes[name_lower]())
            logger.debug(f"  added metric: {name}")
        else:
            logger.warning(f"  unknown metric: {name}")

    return metrics


def _create_evaluation_task(config: OpikExperimentConfig) -> Callable:
    """Create evaluation task function based on experiment type.

    The task uses config.task_provider (sidebar LLM) to run Forseti.
    """
    if config.experiment_type == "charter_optimization":
        return _create_charter_task(config.task_provider)
    elif config.experiment_type == "category_optimization":
        return _create_category_task(config.task_provider)
    else:
        return _create_generic_task(config.task_provider)


def _create_charter_task(provider: str) -> Callable:
    """Create evaluation task for charter validation."""

    def evaluation_task(dataset_item: dict) -> dict:
        """Run Forseti charter validation on dataset item."""
        from app.agents.forseti import ForsetiAgent

        input_data = dataset_item.get("input", {})
        title = input_data.get("title", "")
        body = input_data.get("body", "")

        # Run validation
        agent = ForsetiAgent(provider_name=provider)
        result = asyncio.run(agent.validate_charter(title=title, body=body))

        # Format for Opik metrics
        # input: the question/prompt sent to the LLM
        # output: the LLM response
        # context: optional context for RAG metrics
        return {
            "input": f"Validate charter compliance for:\nTitle: {title}\nBody: {body}",
            "output": f"is_valid: {result.is_valid}, confidence: {result.confidence}, violations: {result.violations}",
            "context": [body] if body else None,  # For context-based metrics
            # Additional fields for custom metrics
            "is_valid": result.is_valid,
            "confidence": result.confidence,
            "violations": result.violations,
            "reasoning": result.reasoning,
        }

    return evaluation_task


def _create_category_task(provider: str) -> Callable:
    """Create evaluation task for category classification."""

    def evaluation_task(dataset_item: dict) -> dict:
        """Run Forseti category classification on dataset item."""
        from app.agents.forseti import ForsetiAgent

        input_data = dataset_item.get("input", {})
        title = input_data.get("title", "")
        body = input_data.get("body", "")
        current_category = input_data.get("category")

        # Run classification
        agent = ForsetiAgent(provider_name=provider)
        result = asyncio.run(agent.classify_category(
            title=title,
            body=body,
            current_category=current_category,
        ))

        return {
            "input": f"Classify category for:\nTitle: {title}\nBody: {body}",
            "output": f"category: {result.category}, confidence: {result.confidence}",
            "context": [body] if body else None,
            # Additional fields
            "category": result.category,
            "confidence": result.confidence,
            "reasoning": result.reasoning,
        }

    return evaluation_task


def _create_generic_task(provider: str) -> Callable:
    """Create generic evaluation task."""

    def evaluation_task(dataset_item: dict) -> dict:
        """Generic pass-through task."""
        input_data = dataset_item.get("input", {})
        expected = dataset_item.get("expected_output", {})

        return {
            "input": str(input_data),
            "output": str(expected),
        }

    return evaluation_task


def _format_eval_results(eval_results) -> dict:
    """Format Opik evaluation results for logging."""
    try:
        return {
            "experiment_name": getattr(eval_results, "experiment_name", None),
            "average_scores": getattr(eval_results, "average_scores", {}),
            "num_items": getattr(eval_results, "num_items", 0),
        }
    except Exception:
        return {"raw": str(eval_results)}


# =============================================================================
# Custom Metrics for OCapistaine
# =============================================================================


def create_charter_compliance_metric():
    """
    Create custom metric for charter compliance evaluation.

    This metric checks if the LLM output correctly identifies
    charter violations and encouraged aspects.
    """
    from opik.evaluation.metrics import BaseMetric, score_result

    class CharterComplianceMetric(BaseMetric):
        """Custom metric for charter validation accuracy."""

        name = "charter_compliance"

        def score(self, output: str, expected_output: str = None, **kwargs) -> score_result:
            """Score charter compliance."""
            # Extract is_valid from output
            is_valid_actual = "is_valid: True" in output or "is_valid: true" in output

            # Compare with expected
            expected = kwargs.get("expected_output", {})
            is_valid_expected = expected.get("is_valid", True)

            score = 1.0 if is_valid_actual == is_valid_expected else 0.0

            return score_result(
                name=self.name,
                value=score,
                reason=f"Expected is_valid={is_valid_expected}, got is_valid={is_valid_actual}",
            )

    return CharterComplianceMetric()


def create_confidence_metric():
    """
    Create custom metric for confidence threshold.

    This metric checks if the LLM confidence meets the threshold.
    """
    from opik.evaluation.metrics import BaseMetric, score_result
    import re

    class ConfidenceMetric(BaseMetric):
        """Custom metric for confidence level."""

        name = "confidence"

        def __init__(self, threshold: float = 0.8):
            self.threshold = threshold

        def score(self, output: str, **kwargs) -> score_result:
            """Score confidence level."""
            # Extract confidence from output
            match = re.search(r"confidence:\s*([\d.]+)", output)
            if match:
                confidence = float(match.group(1))
                score = confidence  # Use raw confidence as score
                meets_threshold = confidence >= self.threshold
            else:
                confidence = 0.0
                score = 0.0
                meets_threshold = False

            return score_result(
                name=self.name,
                value=score,
                reason=f"Confidence: {confidence:.2f} (threshold: {self.threshold})",
            )

    return ConfidenceMetric()


# =============================================================================
# Utilities
# =============================================================================


def list_experiment_types() -> list[dict]:
    """List all available experiment types from AGENT_FEATURE_REGISTRY."""
    return [
        {
            "type": exp_type,
            "agent": config["agent"],
            "feature": config["feature"],
            "prompt_key": config.get("prompt_key"),
            "description": config.get("description"),
        }
        for exp_type, config in AGENT_FEATURE_REGISTRY.items()
    ]


def list_available_metrics() -> list[dict]:
    """List all available Opik metrics."""
    return [
        {"name": "hallucination", "description": "Detects generated false information"},
        {"name": "moderation", "description": "Checks adherence to content standards"},
        {"name": "answer_relevance", "description": "Evaluates how well the answer fits the question"},
        {"name": "context_recall", "description": "Measures retrieval of relevant context"},
        {"name": "context_precision", "description": "Measures precision of retrieved context"},
        {"name": "charter_compliance", "description": "Custom: Charter validation accuracy"},
        {"name": "confidence", "description": "Custom: Confidence threshold check"},
    ]


def get_experiment_filters(experiment_type: str) -> dict:
    """
    Get available filters for an experiment type.

    Returns filter options based on the feature's span structure.
    """
    config = get_feature_config(experiment_type)
    if not config:
        return {}

    span_name = config["feature"]

    return {
        "span_name": span_name,
        "filters": {
            "correctness": {
                "field": "feedback_scores.Correctness",
                "operators": ["<", "<=", ">", ">=", "="],
                "description": "Filter by Correctness feedback score",
            },
            "added_to_dataset": {
                "field": "feedback_scores.added_to_dataset",
                "operators": ["exists", "not_exists"],
                "description": "Filter by whether span was added to a dataset",
            },
            "type": {
                "field": "type",
                "values": ["llm", "general", "tool"],
                "description": "Filter by span type",
            },
        },
        "example_filter": f'name = "{span_name}" AND feedback_scores.Correctness < 0.7 AND type = "llm"',
    }
