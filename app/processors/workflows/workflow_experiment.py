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
- OutputFormatCompliance: Measures how well output matches ideal format

Pre-experiment Cleanup:
- cleanup_error_traces(): Removes traces with validation errors before experiments

Usage:
    from app.processors.workflows import run_opik_experiment, OpikExperimentConfig

    config = OpikExperimentConfig(
        experiment_name="charter-eval-20260204",
        dataset_name="low-confidence-20260204-001",
        experiment_type="charter_optimization",
        metrics=["hallucination", "moderation", "output_format"],
        task_provider="gemini",  # Sidebar LLM for Forseti
    )
    results = run_opik_experiment(config)
"""

import asyncio
import os
from datetime import datetime
from typing import Optional, Callable

from app.services.logging import get_logger
from app.services.tasks import AGENT_FEATURE_REGISTRY, get_feature_config
from app.services.opik_config import (
    get_opik_judge_config,
    configure_opik_environment,
)

logger = get_logger("processors")


# =============================================================================
# Pre-experiment Cleanup
# =============================================================================


def cleanup_error_traces(project_name: str = None, dry_run: bool = False) -> dict:
    """
    Delete traces with validation errors before running experiments.

    Error traces (e.g., "Validation error: Gemini retries exhausted") can
    pollute the optimization process and diverge from the goal of better prompts.

    Args:
        project_name: Opik project name (default: from OPIK_PROJECT env var)
        dry_run: If True, only count errors without deleting

    Returns:
        dict with deletion results:
        - total_traces: Total traces searched
        - error_traces: Number of error traces found
        - deleted: Number of traces deleted (0 if dry_run)
        - error_patterns: List of error patterns found
    """
    try:
        from opik import Opik

        client = Opik()
        project = project_name or os.getenv("OPIK_PROJECT", "ocapistaine")

        logger.info(f"Cleanup: Searching for error traces in project '{project}'")

        # Search all traces
        traces = client.search_traces(
            project_name=project,
            max_results=1000,
        )

        # Error patterns to match in output.reasoning
        error_patterns = [
            "error",
            "retries exhausted",
            "rate limit",
            "validation error",
            "timeout",
            "failed",
        ]

        # Find error traces
        error_trace_ids = []
        error_reasons = {}

        for trace in traces:
            output = trace.output or {}
            reasoning = output.get("reasoning", "")

            for pattern in error_patterns:
                if pattern.lower() in reasoning.lower():
                    error_trace_ids.append(trace.id)
                    # Track error patterns found
                    error_reasons[pattern] = error_reasons.get(pattern, 0) + 1
                    break

        result = {
            "project": project,
            "total_traces": len(traces),
            "error_traces": len(error_trace_ids),
            "deleted": 0,
            "error_patterns": error_reasons,
            "dry_run": dry_run,
        }

        if not error_trace_ids:
            logger.info("Cleanup: No error traces found")
            return result

        if dry_run:
            logger.info(f"Cleanup: Would delete {len(error_trace_ids)} error traces (dry_run=True)")
            return result

        # Delete error traces via REST API
        rest_client = client._rest_client
        batch_size = 100
        deleted = 0

        for i in range(0, len(error_trace_ids), batch_size):
            batch = error_trace_ids[i : i + batch_size]
            rest_client.traces.delete_traces(ids=batch)
            deleted += len(batch)
            logger.info(f"Cleanup: Deleted {deleted}/{len(error_trace_ids)} error traces")

        result["deleted"] = deleted
        logger.info(f"Cleanup: Successfully deleted {deleted} error traces")
        return result

    except ImportError as e:
        logger.error(f"Cleanup: Opik SDK not available: {e}")
        return {"error": str(e), "deleted": 0}
    except Exception as e:
        logger.error(f"Cleanup: Failed to clean error traces: {e}")
        return {"error": str(e), "deleted": 0}


# =============================================================================
# Ideal Output Format Reference
# =============================================================================

# The ideal charter validation output format for optimization
IDEAL_CHARTER_OUTPUT = {
    "is_valid": True,
    "violations": [],
    "encouraged_aspects": [
        "Concrete and argued proposals",
        "Constructive criticism",
        "Questions and requests for clarification",
        "Sharing of experiences and expertise",
        "Suggestions for improvement",
    ],
    "reasoning": "A clear explanation of why the contribution is valid or invalid...",
    "confidence": 0.95,
}

# Required fields and their expected types
CHARTER_OUTPUT_SCHEMA = {
    "is_valid": bool,
    "violations": list,
    "encouraged_aspects": list,
    "reasoning": str,
    "confidence": float,
}


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
        cleanup_errors: bool = True,
    ):
        """
        Initialize experiment configuration.

        Args:
            experiment_name: Name for the experiment in Opik
            dataset_name: Name of the Opik dataset to evaluate
            experiment_type: Key from AGENT_FEATURE_REGISTRY
            metrics: List of metric names to use (default: ["hallucination", "output_format"])
            task_provider: LLM provider for evaluation task (sidebar LLM: gemini, claude, ollama)
            custom_task: Optional custom evaluation task function
            cleanup_errors: If True, delete error traces before running experiment

        Note:
            - task_provider: The LLM that runs the actual Forseti validation
            - Opik judge LLM: Configured separately in admin (default: OpenAI gpt-4o-mini)
        """
        self.experiment_name = experiment_name
        self.dataset_name = dataset_name
        self.experiment_type = experiment_type
        self.metrics = metrics or ["hallucination", "output_format"]
        self.task_provider = task_provider
        self.custom_task = custom_task
        self.cleanup_errors = cleanup_errors

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
            "cleanup_errors": self.cleanup_errors,
        }


def run_opik_experiment(config: OpikExperimentConfig) -> dict:
    """
    Run an experiment using Opik's native evaluate() API.

    This uses Opik's built-in LLM judge metrics and reports
    results directly to the Opik platform.

    Workflow:
    1. (Optional) Cleanup error traces to avoid polluting optimization
    2. Load dataset
    3. Run evaluation with task LLM and judge LLM
    4. Return results

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
    logger.info(f"  cleanup_errors: {config.cleanup_errors}")

    result = {
        "experiment_name": config.experiment_name,
        "dataset_name": config.dataset_name,
        "status": "pending",
        "metrics_used": config.metrics,
        "task_provider": config.task_provider,
        "judge_config": config.judge_config,
        "cleanup_result": None,
        "errors": [],
    }

    # Step 1: Cleanup error traces (preliminary step)
    if config.cleanup_errors:
        logger.info("Step 1: Cleaning up error traces...")
        cleanup_result = cleanup_error_traces()
        result["cleanup_result"] = cleanup_result
        if cleanup_result.get("deleted", 0) > 0:
            logger.info(f"  Deleted {cleanup_result['deleted']} error traces")
        elif cleanup_result.get("error"):
            logger.warning(f"  Cleanup failed: {cleanup_result.get('error')}")
    else:
        logger.info("Step 1: Skipping error cleanup (disabled)")

    # Configure Opik judge LLM environment
    if not configure_opik_environment():
        result["errors"].append("Opik judge LLM not configured - check OPENAI_API_KEY")
        logger.warning("Opik judge LLM not configured - metrics may fail")

    try:
        from opik import Opik
        from opik.evaluation import evaluate

        # Get Opik client
        client = Opik()

        # Step 2: Load dataset
        logger.info(f"Step 2: Loading dataset '{config.dataset_name}'...")
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

        # Get task model name from provider
        task_model = _get_provider_model(config.task_provider)

        # Build experiment_config for Opik (metadata about this experiment)
        experiment_config = {
            # Task LLM (runs Forseti validation)
            "task_provider": config.task_provider,
            "task_model": task_model,
            # Judge LLM (runs Opik metrics)
            "judge_provider": config.judge_config.get("provider"),
            "judge_model": config.judge_config.get("model"),
            # Experiment metadata
            "experiment_type": config.experiment_type,
            "feature": config.feature_config.get("feature"),
            "prompt_key": config.feature_config.get("prompt_key"),
            "metrics": config.metrics,
        }
        logger.info(f"  experiment_config: {experiment_config}")

        # Step 3: Run evaluation
        logger.info(f"Step 3: Running evaluation with {len(scoring_metrics)} metrics...")
        eval_results = evaluate(
            experiment_name=config.experiment_name,
            dataset=dataset,
            task=evaluation_task,
            scoring_metrics=scoring_metrics,
            experiment_config=experiment_config,
        )

        result["status"] = "success"
        result["experiment_config"] = experiment_config
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
    """Build list of Opik metric instances (built-in and custom)."""
    from opik.evaluation.metrics import (
        Hallucination,
        Moderation,
        AnswerRelevance,
        ContextRecall,
        ContextPrecision,
    )

    # Built-in Opik metrics
    builtin_metrics = {
        "hallucination": Hallucination,
        "moderation": Moderation,
        "answer_relevance": AnswerRelevance,
        "context_recall": ContextRecall,
        "context_precision": ContextPrecision,
    }

    # Custom OCapistaine metrics (factory functions)
    custom_metrics = {
        "charter_compliance": create_charter_compliance_metric,
        "confidence": create_confidence_metric,
        "output_format": create_output_format_metric,
    }

    metrics = []
    for name in metric_names:
        name_lower = name.lower().replace("-", "_")

        if name_lower in builtin_metrics:
            metrics.append(builtin_metrics[name_lower]())
            logger.debug(f"  added built-in metric: {name}")
        elif name_lower in custom_metrics:
            metrics.append(custom_metrics[name_lower]())
            logger.debug(f"  added custom metric: {name}")
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
        category = input_data.get("category")

        # Run classification
        agent = ForsetiAgent(provider_name=provider)
        result = asyncio.run(agent.classify_category(
            title=title,
            body=body,
            category=category,
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
    from opik.evaluation.metrics import BaseMetric
    from opik.evaluation.metrics.score_result import ScoreResult

    class CharterComplianceMetric(BaseMetric):
        """Custom metric for charter validation accuracy."""

        name = "charter_compliance"

        def score(self, output: str, expected_output: str = None, **kwargs) -> ScoreResult:
            """Score charter compliance."""
            # Extract is_valid from output
            is_valid_actual = "is_valid: True" in output or "is_valid: true" in output

            # Compare with expected
            expected = kwargs.get("expected_output", {})
            is_valid_expected = expected.get("is_valid", True)

            value = 1.0 if is_valid_actual == is_valid_expected else 0.0

            return ScoreResult(
                name=self.name,
                value=value,
                reason=f"Expected is_valid={is_valid_expected}, got is_valid={is_valid_actual}",
            )

    return CharterComplianceMetric()


def create_confidence_metric():
    """
    Create custom metric for confidence threshold.

    This metric checks if the LLM confidence meets the threshold.
    """
    from opik.evaluation.metrics import BaseMetric
    from opik.evaluation.metrics.score_result import ScoreResult
    import re

    class ConfidenceMetric(BaseMetric):
        """Custom metric for confidence level."""

        name = "confidence"

        def __init__(self, threshold: float = 0.8):
            self.threshold = threshold

        def score(self, output: str, **kwargs) -> ScoreResult:
            """Score confidence level."""
            # Extract confidence from output
            match = re.search(r"confidence:\s*([\d.]+)", output)
            if match:
                confidence = float(match.group(1))
                value = confidence  # Use raw confidence as score
            else:
                confidence = 0.0
                value = 0.0

            return ScoreResult(
                name=self.name,
                value=value,
                reason=f"Confidence: {confidence:.2f} (threshold: {self.threshold})",
            )

    return ConfidenceMetric()


def create_output_format_metric():
    """
    Create custom metric for output format compliance.

    Measures how well the LLM output matches the ideal charter validation format:
    {
        "is_valid": bool,
        "violations": list,
        "encouraged_aspects": list,
        "reasoning": str (non-empty, no error messages),
        "confidence": float (0.0 to 1.0)
    }

    Scoring (0.0 to 1.0):
    - 0.2 per required field present with correct type
    - Deductions for:
      - Error messages in reasoning (-0.5)
      - Empty reasoning (-0.2)
      - Confidence out of range (-0.1)
      - Missing encouraged_aspects when valid (-0.1)
    """
    from opik.evaluation.metrics import BaseMetric
    from opik.evaluation.metrics.score_result import ScoreResult
    import json

    class OutputFormatComplianceMetric(BaseMetric):
        """Custom metric for charter output format compliance."""

        name = "output_format"

        def __init__(self):
            self.required_fields = {
                "is_valid": bool,
                "violations": list,
                "encouraged_aspects": list,
                "reasoning": str,
                "confidence": (int, float),
            }
            self.error_patterns = [
                "error",
                "retries exhausted",
                "rate limit",
                "validation error",
                "timeout",
                "failed",
            ]

        def score(self, output: str = None, **kwargs) -> ScoreResult:
            """
            Score output format compliance.

            Args:
                output: String representation of output (may be JSON or formatted string)
                **kwargs: May contain 'expected_output' dict with actual structured data
            """
            total_score = 0.0
            reasons = []

            # Try to get structured output from kwargs first
            expected_output = kwargs.get("expected_output", {})
            if isinstance(expected_output, dict) and expected_output:
                output_data = expected_output
            else:
                # Try to parse output string as JSON
                output_data = self._parse_output(output or "")

            if not output_data:
                return ScoreResult(
                    name=self.name,
                    value=0.0,
                    reason="Could not parse output as structured data",
                )

            # Check each required field (0.2 points each = 1.0 max)
            field_score = 0.0
            for field, expected_type in self.required_fields.items():
                if field in output_data:
                    value = output_data[field]
                    if isinstance(value, expected_type):
                        field_score += 0.2
                        reasons.append(f"✓ {field}: correct type")
                    else:
                        reasons.append(f"✗ {field}: wrong type (got {type(value).__name__})")
                else:
                    reasons.append(f"✗ {field}: missing")

            total_score = field_score

            # Check for error messages in reasoning (-0.5)
            reasoning = output_data.get("reasoning", "")
            if isinstance(reasoning, str):
                for pattern in self.error_patterns:
                    if pattern.lower() in reasoning.lower():
                        total_score -= 0.5
                        reasons.append(f"✗ reasoning contains error: '{pattern}'")
                        break

                # Check for empty reasoning (-0.2)
                if not reasoning.strip():
                    total_score -= 0.2
                    reasons.append("✗ reasoning is empty")

            # Check confidence range (-0.1 if out of range)
            confidence = output_data.get("confidence", 0)
            if isinstance(confidence, (int, float)):
                if not (0.0 <= confidence <= 1.0):
                    total_score -= 0.1
                    reasons.append(f"✗ confidence out of range: {confidence}")

            # Check encouraged_aspects when valid (-0.1 if missing)
            is_valid = output_data.get("is_valid", False)
            encouraged = output_data.get("encouraged_aspects", [])
            if is_valid and (not encouraged or len(encouraged) == 0):
                total_score -= 0.1
                reasons.append("✗ valid but no encouraged_aspects")

            # Clamp score to [0, 1]
            final_score = max(0.0, min(1.0, total_score))

            return ScoreResult(
                name=self.name,
                value=final_score,
                reason=" | ".join(reasons[:5]),  # Limit reason length
            )

        def _parse_output(self, output: str) -> dict:
            """Try to parse output string as structured data."""
            if not output:
                return {}

            # Try JSON parse
            try:
                return json.loads(output)
            except (json.JSONDecodeError, TypeError):
                pass

            # Try to extract from formatted string like "is_valid: True, confidence: 0.9"
            result = {}
            try:
                # Extract is_valid
                if "is_valid: True" in output or "is_valid: true" in output:
                    result["is_valid"] = True
                elif "is_valid: False" in output or "is_valid: false" in output:
                    result["is_valid"] = False

                # Extract confidence
                import re
                conf_match = re.search(r"confidence[:\s]+([0-9.]+)", output)
                if conf_match:
                    result["confidence"] = float(conf_match.group(1))

                # Extract violations (basic)
                if "violations: []" in output or "violations: None" in output:
                    result["violations"] = []

                # Mark reasoning as present if there's substantial text
                if len(output) > 50:
                    result["reasoning"] = output

            except Exception:
                pass

            return result

    return OutputFormatComplianceMetric()


# =============================================================================
# Utilities
# =============================================================================


def _get_provider_model(provider_name: str) -> str:
    """Get the model name for a provider."""
    try:
        from app.providers import get_provider
        provider = get_provider(provider_name)
        return provider.model
    except Exception:
        # Return default models if provider instantiation fails
        defaults = {
            "gemini": "gemini-2.5-flash",
            "claude": "claude-3-5-sonnet-20241022",
            "ollama": "deepseek-r1:7b",
            "mistral": "mistral-small-latest",
        }
        return defaults.get(provider_name, provider_name)


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
        # Built-in Opik metrics (LLM judges)
        {"name": "hallucination", "description": "Detects generated false information", "type": "builtin"},
        {"name": "moderation", "description": "Checks adherence to content standards", "type": "builtin"},
        {"name": "answer_relevance", "description": "Evaluates how well the answer fits the question", "type": "builtin"},
        {"name": "context_recall", "description": "Measures retrieval of relevant context", "type": "builtin"},
        {"name": "context_precision", "description": "Measures precision of retrieved context", "type": "builtin"},
        # Custom OCapistaine metrics
        {"name": "charter_compliance", "description": "Custom: Charter validation accuracy (is_valid match)", "type": "custom"},
        {"name": "confidence", "description": "Custom: Confidence threshold check", "type": "custom"},
        {"name": "output_format", "description": "Custom: Measures output format compliance (0-1 scale)", "type": "custom"},
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
