# app/processors/mockup_processor.py
"""
Mockup Processor - Charter Validation Testing Workflow

Generates and processes mock contributions to test and improve Forseti 461's
charter validation prompts. Part of the Business Logic Layer (Apache 2.0).

Workflow:
1. Load/generate mock contributions (text-based or LLM mutations)
2. Run batch validation with Forseti
3. Store results in Redis
4. Export to Opik datasets for prompt optimization
5. Calculate accuracy metrics

Data location: app/mockup/data/contributions.json
Redis key: contribution_mockup:forseti461:charter:{date}:{id}
"""

import asyncio
import time
from datetime import date
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field

from app.logging.domains import ProcessorLogger
from app.mockup.generator import (
    ContributionGenerator,
    MockContribution,
    load_contributions,
    save_contributions,
    generate_variations,
)
from app.mockup.storage import (
    ValidationRecord,
    MockupStorage,
    get_storage,
)
from app.mockup.dataset import (
    DatasetManager,
    get_dataset_manager,
    DATASET_TRAINING,
    DATASET_VALIDATION,
    DATASET_TEST,
)
from app.mockup.llm_mutations import (
    LLMMutator,
    MutationType,
    check_ollama_available,
)

# Opik experiment integration (optional)
try:
    from opik import Opik
    from opik.evaluation import evaluate
    from opik.evaluation.metrics import BaseMetric
    OPIK_AVAILABLE = True
except ImportError:
    OPIK_AVAILABLE = False
    Opik = None
    evaluate = None
    BaseMetric = object


class CharterAccuracyMetric(BaseMetric):
    """
    Opik metric for charter validation accuracy.

    Compares Forseti's validation result against expected ground truth.
    Score: 1.0 if match, 0.0 if mismatch.
    """

    name = "charter_accuracy"

    def score(self, output: Dict[str, Any], expected_output: Dict[str, Any], **kwargs) -> float:
        """Calculate accuracy score."""
        actual_valid = output.get("is_valid", True)
        expected_valid = expected_output.get("is_valid", True)
        return 1.0 if actual_valid == expected_valid else 0.0


class ViolationDetectionMetric(BaseMetric):
    """
    Opik metric for violation detection recall.

    Measures how well Forseti detects injected violations.
    Score: ratio of detected violations to expected violations.
    """

    name = "violation_detection"

    def score(self, output: Dict[str, Any], metadata: Dict[str, Any], **kwargs) -> float:
        """Calculate violation detection score."""
        violations_injected = metadata.get("violations_injected", [])
        if not violations_injected:
            # No violations expected - score based on not finding false positives
            violations_found = output.get("violations", [])
            return 1.0 if not violations_found else 0.5

        # Check if any violations were detected
        violations_found = output.get("violations", [])
        if not violations_found and not output.get("is_valid", True):
            # Marked invalid but no specific violations - partial credit
            return 0.5

        return 1.0 if violations_found else 0.0


class ConfidenceCalibrationMetric(BaseMetric):
    """
    Opik metric for confidence calibration.

    Higher confidence should correlate with correct predictions.
    Score: confidence if correct, 1-confidence if incorrect.
    """

    name = "confidence_calibration"

    def score(self, output: Dict[str, Any], expected_output: Dict[str, Any], **kwargs) -> float:
        """Calculate confidence calibration score."""
        confidence = output.get("confidence", 0.5)
        actual_valid = output.get("is_valid", True)
        expected_valid = expected_output.get("is_valid", True)

        if actual_valid == expected_valid:
            return confidence  # High confidence + correct = good
        else:
            return 1.0 - confidence  # High confidence + wrong = bad


@dataclass
class MockupWorkflowConfig:
    """Configuration for mockup processor workflow."""

    # Generation settings
    num_variations: int = 5
    include_violations: bool = True
    use_llm: bool = True
    llm_model: str = "mistral:latest"

    # Storage settings
    save_to_json: bool = True
    save_to_redis: bool = True

    # Dataset settings
    create_dataset: bool = True
    dataset_name: Optional[str] = None
    train_val_test_split: bool = False
    train_ratio: float = 0.7
    val_ratio: float = 0.15

    # Experiment settings
    run_experiment: bool = False
    experiment_name: Optional[str] = None  # Auto-generated if None
    experiment_metrics: List[str] = field(default_factory=lambda: [
        "charter_accuracy", "violation_detection", "confidence_calibration"
    ])


@dataclass
class ExperimentResult:
    """Result of an Opik experiment run."""

    experiment_name: str = ""
    experiment_id: Optional[str] = None
    dataset_name: str = ""
    samples_evaluated: int = 0

    # Aggregate scores
    charter_accuracy: Optional[float] = None
    violation_detection: Optional[float] = None
    confidence_calibration: Optional[float] = None

    # Detailed breakdown
    true_positives: int = 0  # Invalid correctly rejected
    true_negatives: int = 0  # Valid correctly accepted
    false_positives: int = 0  # Valid incorrectly rejected
    false_negatives: int = 0  # Invalid incorrectly accepted (worst)

    precision: Optional[float] = None
    recall: Optional[float] = None
    f1_score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_name": self.experiment_name,
            "experiment_id": self.experiment_id,
            "dataset_name": self.dataset_name,
            "samples_evaluated": self.samples_evaluated,
            "charter_accuracy": self.charter_accuracy,
            "violation_detection": self.violation_detection,
            "confidence_calibration": self.confidence_calibration,
            "true_positives": self.true_positives,
            "true_negatives": self.true_negatives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "precision": self.precision,
            "recall": self.recall,
            "f1_score": self.f1_score,
        }


@dataclass
class MockupWorkflowResult:
    """Result of a mockup processor workflow run."""

    # Generation results
    contributions_generated: int = 0
    contributions_loaded: int = 0

    # Validation results
    validations_run: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    matches_expected: int = 0
    accuracy: Optional[float] = None

    # Storage results
    saved_to_json: int = 0
    saved_to_redis: int = 0

    # Dataset results
    dataset_name: Optional[str] = None
    dataset_items: int = 0
    opik_synced: bool = False

    # Experiment results
    experiment: Optional[ExperimentResult] = None

    # Timing
    total_time_ms: int = 0

    # Errors
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contributions_generated": self.contributions_generated,
            "contributions_loaded": self.contributions_loaded,
            "validations_run": self.validations_run,
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "matches_expected": self.matches_expected,
            "accuracy": self.accuracy,
            "saved_to_json": self.saved_to_json,
            "saved_to_redis": self.saved_to_redis,
            "dataset_name": self.dataset_name,
            "dataset_items": self.dataset_items,
            "opik_synced": self.opik_synced,
            "experiment": self.experiment.to_dict() if self.experiment else None,
            "total_time_ms": self.total_time_ms,
            "errors": self.errors,
        }


class MockupProcessor:
    """
    Processor for charter validation testing workflow.

    Generates mock contributions, runs validation, stores results,
    and exports to Opik for prompt optimization.

    Usage:
        processor = MockupProcessor()

        # Generate and validate
        result = await processor.run_workflow(
            constat_factuel="Le parking du port est plein...",
            idees_ameliorations="Créer un parking relais...",
            validate_func=forseti.validate,
            config=MockupWorkflowConfig(use_llm=True),
        )

        # Load existing and validate
        result = await processor.validate_existing(
            validate_func=forseti.validate,
            source_filter=["framaforms", "mock"],
        )
    """

    def __init__(self):
        """Initialize the mockup processor."""
        self._logger = ProcessorLogger("mockup")
        self._storage = get_storage()
        self._dataset_manager = get_dataset_manager()

    async def check_dependencies(self) -> Dict[str, bool]:
        """
        Check if all dependencies are available.

        Returns:
            Dict with status of each dependency
        """
        self._logger.log_process_start("mockup", "dependency_check")

        status = {
            "redis": False,
            "ollama": False,
            "opik": False,
        }

        # Check Redis
        try:
            from app.data.redis_client import health_check
            status["redis"] = health_check()
        except Exception:
            pass

        # Check Ollama
        try:
            status["ollama"] = await check_ollama_available()
        except Exception:
            pass

        # Check Opik
        status["opik"] = self._dataset_manager.opik_enabled

        self._logger.info("DEPENDENCIES", **status)
        return status

    async def run_workflow(
        self,
        constat_factuel: str,
        idees_ameliorations: str = "",
        category: Optional[str] = None,
        validate_func: Optional[Callable] = None,
        config: Optional[MockupWorkflowConfig] = None,
    ) -> MockupWorkflowResult:
        """
        Run the full mockup workflow: generate, validate, store, export.

        Args:
            constat_factuel: Factual observation text
            idees_ameliorations: Improvement ideas text
            category: Contribution category
            validate_func: Forseti validation function (title, body, category) -> dict
            config: Workflow configuration

        Returns:
            MockupWorkflowResult with all metrics
        """
        config = config or MockupWorkflowConfig()
        result = MockupWorkflowResult()
        start_time = time.time()

        self._logger.log_process_start(
            "mockup",
            "workflow",
            input_size=len(constat_factuel) + len(idees_ameliorations),
        )

        try:
            # Step 1: Generate variations
            self._logger.info("STEP", step="generate", use_llm=config.use_llm)

            variations = generate_variations(
                constat_factuel=constat_factuel,
                idees_ameliorations=idees_ameliorations,
                category=category,
                num_variations=config.num_variations,
                include_violations=config.include_violations,
                use_llm=config.use_llm,
                llm_model=config.llm_model,
            )
            result.contributions_generated = len(variations)

            # Convert to MockContribution objects
            contributions = [MockContribution.from_dict(v) for v in variations]

            # Step 2: Save to JSON
            if config.save_to_json:
                self._logger.info("STEP", step="save_json")
                result.saved_to_json = self._save_to_json(contributions)

            # Step 3: Run validation (if validate_func provided)
            if validate_func:
                self._logger.info("STEP", step="validate")
                validation_results = await self._run_validation(
                    contributions, validate_func
                )

                result.validations_run = len(validation_results)
                result.valid_count = sum(1 for r in validation_results if r.is_valid)
                result.invalid_count = result.validations_run - result.valid_count
                result.matches_expected = sum(
                    1 for r in validation_results
                    if r.matches_expected() is True
                )
                if result.validations_run > 0:
                    with_expected = [r for r in validation_results if r.expected_valid is not None]
                    if with_expected:
                        result.accuracy = result.matches_expected / len(with_expected)

                # Step 4: Save to Redis
                if config.save_to_redis:
                    self._logger.info("STEP", step="save_redis")
                    result.saved_to_redis = self._storage.save_batch(validation_results)

                # Step 5: Export to Opik dataset
                if config.create_dataset:
                    self._logger.info("STEP", step="export_dataset")
                    dataset_result = self._export_to_dataset(
                        validation_results, config
                    )
                    result.dataset_name = dataset_result.get("name")
                    result.dataset_items = dataset_result.get("items", 0)
                    result.opik_synced = dataset_result.get("synced", False)

            else:
                # Just save without validation
                if config.save_to_redis:
                    records = self._contributions_to_records(contributions)
                    result.saved_to_redis = self._storage.save_batch(records)

        except Exception as e:
            self._logger.error("WORKFLOW_ERROR", error=str(e))
            result.errors.append(str(e))

        result.total_time_ms = int((time.time() - start_time) * 1000)

        self._logger.log_process_complete(
            "mockup",
            "workflow_result",
            output_size=result.contributions_generated,
            latency_ms=result.total_time_ms,
        )

        return result

    async def validate_existing(
        self,
        validate_func: Callable,
        source_filter: Optional[List[str]] = None,
        category_filter: Optional[List[str]] = None,
        limit: Optional[int] = None,
        config: Optional[MockupWorkflowConfig] = None,
    ) -> MockupWorkflowResult:
        """
        Validate existing contributions from JSON file.

        Args:
            validate_func: Forseti validation function
            source_filter: Filter by source types
            category_filter: Filter by categories
            limit: Maximum contributions to validate
            config: Workflow configuration

        Returns:
            MockupWorkflowResult with validation metrics
        """
        config = config or MockupWorkflowConfig()
        result = MockupWorkflowResult()
        start_time = time.time()

        self._logger.log_process_start("mockup", "validate_existing")

        try:
            # Load contributions
            generator = load_contributions()
            contributions = generator.contributions
            result.contributions_loaded = len(contributions)

            # Apply filters
            if source_filter:
                contributions = [c for c in contributions if c.source in source_filter]
            if category_filter:
                contributions = [c for c in contributions if c.category in category_filter]
            if limit:
                contributions = contributions[:limit]

            self._logger.info(
                "LOADED",
                total=result.contributions_loaded,
                filtered=len(contributions),
            )

            # Run validation
            validation_results = await self._run_validation(contributions, validate_func)

            result.validations_run = len(validation_results)
            result.valid_count = sum(1 for r in validation_results if r.is_valid)
            result.invalid_count = result.validations_run - result.valid_count
            result.matches_expected = sum(
                1 for r in validation_results
                if r.matches_expected() is True
            )

            with_expected = [r for r in validation_results if r.expected_valid is not None]
            if with_expected:
                result.accuracy = result.matches_expected / len(with_expected)

            # Save results
            if config.save_to_redis:
                result.saved_to_redis = self._storage.save_batch(validation_results)

            if config.create_dataset:
                dataset_result = self._export_to_dataset(validation_results, config)
                result.dataset_name = dataset_result.get("name")
                result.dataset_items = dataset_result.get("items", 0)
                result.opik_synced = dataset_result.get("synced", False)

        except Exception as e:
            self._logger.error("VALIDATE_EXISTING_ERROR", error=str(e))
            result.errors.append(str(e))

        result.total_time_ms = int((time.time() - start_time) * 1000)

        self._logger.log_process_complete(
            "mockup",
            "validate_existing_result",
            output_size=result.validations_run,
            latency_ms=result.total_time_ms,
        )

        return result

    async def _run_validation(
        self,
        contributions: List[MockContribution],
        validate_func: Callable,
    ) -> List[ValidationRecord]:
        """Run validation on contributions and create records."""
        today = date.today().isoformat()
        records = []

        for i, contrib in enumerate(contributions):
            item_start = time.time()

            try:
                # Call validation function
                result = validate_func(contrib.title, contrib.body, contrib.category)

                record = ValidationRecord(
                    id=contrib.id,
                    date=today,
                    title=contrib.title,
                    body=contrib.body,
                    category=contrib.category,
                    constat_factuel=contrib.constat_factuel,
                    idees_ameliorations=contrib.idees_ameliorations,
                    is_valid=result.get("is_valid", True),
                    violations=result.get("violations", []),
                    encouraged_aspects=result.get("encouraged_aspects", []),
                    confidence=result.get("confidence", 0.0),
                    reasoning=result.get("reasoning", ""),
                    suggested_category=result.get("category"),
                    category_confidence=result.get("category_confidence", 0.0),
                    source=contrib.source,
                    expected_valid=contrib.expected_valid,
                    parent_id=contrib.parent_id,
                    similarity_to_parent=contrib.similarity_to_parent,
                    distance_from_parent=contrib.distance_from_parent,
                    violations_injected=contrib.violations_injected or [],
                    execution_time_ms=int((time.time() - item_start) * 1000),
                    trace_id=result.get("trace_id"),
                )
                records.append(record)

                self._logger.debug(
                    "VALIDATION",
                    id=contrib.id[:8],
                    valid=record.is_valid,
                    expected=contrib.expected_valid,
                    match=record.matches_expected(),
                )

            except Exception as e:
                self._logger.error(
                    "VALIDATION_ERROR",
                    id=contrib.id[:8],
                    error=str(e),
                )

        return records

    def _save_to_json(self, contributions: List[MockContribution]) -> int:
        """Save contributions to JSON file."""
        try:
            generator = load_contributions()
            existing_ids = {c.id for c in generator.contributions}

            added = 0
            for contrib in contributions:
                if contrib.id not in existing_ids:
                    generator.contributions.append(contrib)
                    added += 1

            save_contributions(generator)

            self._logger.info("SAVE_JSON", added=added, total=len(generator.contributions))
            return added

        except Exception as e:
            self._logger.error("SAVE_JSON_ERROR", error=str(e))
            return 0

    def _contributions_to_records(
        self, contributions: List[MockContribution]
    ) -> List[ValidationRecord]:
        """Convert contributions to validation records (without validation)."""
        today = date.today().isoformat()
        records = []

        for contrib in contributions:
            record = ValidationRecord(
                id=contrib.id,
                date=today,
                title=contrib.title,
                body=contrib.body,
                category=contrib.category,
                constat_factuel=contrib.constat_factuel,
                idees_ameliorations=contrib.idees_ameliorations,
                is_valid=contrib.expected_valid if contrib.expected_valid is not None else True,
                violations=[],
                encouraged_aspects=[],
                confidence=0.0,
                reasoning="Not validated",
                source=contrib.source,
                expected_valid=contrib.expected_valid,
                parent_id=contrib.parent_id,
                similarity_to_parent=contrib.similarity_to_parent,
                violations_injected=contrib.violations_injected or [],
            )
            records.append(record)

        return records

    def _export_to_dataset(
        self,
        records: List[ValidationRecord],
        config: MockupWorkflowConfig,
    ) -> Dict[str, Any]:
        """Export validation records to Opik dataset."""
        dataset_name = config.dataset_name or f"forseti-charter-{date.today().isoformat()}"

        try:
            self._dataset_manager.create_charter_dataset(dataset_name)

            items = [r.to_opik_item() for r in records]
            self._dataset_manager.add_items(dataset_name, items)

            synced = False
            if self._dataset_manager.opik_enabled:
                sync_result = self._dataset_manager.sync_to_opik(dataset_name)
                synced = bool(sync_result)

            # Optionally create train/val/test split
            if config.train_val_test_split:
                self._dataset_manager.create_train_val_test_split(
                    train_ratio=config.train_ratio,
                    val_ratio=config.val_ratio,
                    test_ratio=1 - config.train_ratio - config.val_ratio,
                )

            self._logger.info(
                "EXPORT_DATASET",
                name=dataset_name,
                items=len(items),
                synced=synced,
            )

            return {
                "name": dataset_name,
                "items": len(items),
                "synced": synced,
            }

        except Exception as e:
            self._logger.error("EXPORT_DATASET_ERROR", error=str(e))
            return {"name": dataset_name, "items": 0, "synced": False}

    def get_statistics(self, date_str: Optional[str] = None) -> Dict[str, Any]:
        """Get statistics from stored validations."""
        return self._storage.get_statistics(date_str)

    async def run_experiment(
        self,
        dataset_name: str,
        validate_func: Callable,
        experiment_name: Optional[str] = None,
        metrics: Optional[List[str]] = None,
    ) -> ExperimentResult:
        """
        Run an Opik experiment to evaluate Forseti's charter validation.

        This creates a tracked experiment in Opik that:
        1. Loads the dataset (from local or Opik)
        2. Runs Forseti validation on each item
        3. Scores results using charter-specific metrics
        4. Records all results for comparison over time

        Args:
            dataset_name: Name of the Opik dataset to evaluate
            validate_func: Forseti validation function (title, body, category) -> dict
            experiment_name: Name for this experiment (auto-generated if None)
            metrics: List of metric names to use

        Returns:
            ExperimentResult with all scores and breakdowns
        """
        if not OPIK_AVAILABLE:
            self._logger.warning("OPIK_NOT_AVAILABLE", message="Install opik to run experiments")
            return ExperimentResult(experiment_name=experiment_name or "unavailable")

        experiment_name = experiment_name or f"forseti-charter-{date.today().isoformat()}"
        metrics = metrics or ["charter_accuracy", "violation_detection", "confidence_calibration"]

        self._logger.log_process_start("mockup", "experiment", dataset=dataset_name)

        result = ExperimentResult(
            experiment_name=experiment_name,
            dataset_name=dataset_name,
        )

        try:
            client = Opik()
            dataset = client.get_dataset(name=dataset_name)

            # Create evaluation task that wraps Forseti
            def evaluation_task(dataset_item: Dict[str, Any]) -> Dict[str, Any]:
                input_data = dataset_item.get("input", {})

                # Call Forseti validation
                validation_result = validate_func(
                    input_data.get("title", ""),
                    input_data.get("body", ""),
                    input_data.get("category"),
                )

                return {
                    "input": input_data,
                    "output": {
                        "is_valid": validation_result.get("is_valid", True),
                        "violations": validation_result.get("violations", []),
                        "encouraged_aspects": validation_result.get("encouraged_aspects", []),
                        "confidence": validation_result.get("confidence", 0.0),
                        "reasoning": validation_result.get("reasoning", ""),
                        "category": validation_result.get("category"),
                    },
                    "expected_output": dataset_item.get("expected_output", {}),
                    "metadata": dataset_item.get("metadata", {}),
                }

            # Build metrics list
            scoring_metrics = []
            if "charter_accuracy" in metrics:
                scoring_metrics.append(CharterAccuracyMetric())
            if "violation_detection" in metrics:
                scoring_metrics.append(ViolationDetectionMetric())
            if "confidence_calibration" in metrics:
                scoring_metrics.append(ConfidenceCalibrationMetric())

            # Run the experiment
            eval_results = evaluate(
                experiment_name=experiment_name,
                dataset=dataset,
                task=evaluation_task,
                scoring_metrics=scoring_metrics,
            )

            # Extract results
            result.experiment_id = getattr(eval_results, "experiment_id", None)
            result.samples_evaluated = len(eval_results.test_results) if hasattr(eval_results, "test_results") else 0

            # Calculate aggregate scores from test results
            self._calculate_experiment_scores(result, eval_results)

            self._logger.info(
                "EXPERIMENT_COMPLETE",
                name=experiment_name,
                samples=result.samples_evaluated,
                accuracy=result.charter_accuracy,
                f1=result.f1_score,
            )

        except Exception as e:
            self._logger.error("EXPERIMENT_ERROR", error=str(e))
            result.experiment_name = f"{experiment_name} (failed)"

        return result

    def _calculate_experiment_scores(
        self, result: ExperimentResult, eval_results: Any
    ) -> None:
        """Calculate aggregate scores from Opik evaluation results."""
        if not hasattr(eval_results, "test_results"):
            return

        accuracy_scores = []
        violation_scores = []
        calibration_scores = []

        for test_result in eval_results.test_results:
            output = test_result.get("output", {})
            expected = test_result.get("expected_output", {})
            metadata = test_result.get("metadata", {})

            actual_valid = output.get("is_valid", True)
            expected_valid = expected.get("is_valid", True)

            # Accuracy
            accuracy_scores.append(1.0 if actual_valid == expected_valid else 0.0)

            # Confusion matrix (for invalid = positive class)
            if not expected_valid:  # Expected invalid
                if not actual_valid:
                    result.true_positives += 1
                else:
                    result.false_negatives += 1  # Missed violation!
            else:  # Expected valid
                if actual_valid:
                    result.true_negatives += 1
                else:
                    result.false_positives += 1

            # Violation detection
            violations_injected = metadata.get("violations_injected", [])
            if violations_injected:
                violations_found = output.get("violations", [])
                violation_scores.append(1.0 if violations_found or not actual_valid else 0.0)

            # Calibration
            confidence = output.get("confidence", 0.5)
            if actual_valid == expected_valid:
                calibration_scores.append(confidence)
            else:
                calibration_scores.append(1.0 - confidence)

        # Aggregate scores
        if accuracy_scores:
            result.charter_accuracy = sum(accuracy_scores) / len(accuracy_scores)
        if violation_scores:
            result.violation_detection = sum(violation_scores) / len(violation_scores)
        if calibration_scores:
            result.confidence_calibration = sum(calibration_scores) / len(calibration_scores)

        # Precision, Recall, F1
        tp, fp, fn = result.true_positives, result.false_positives, result.false_negatives
        if tp + fp > 0:
            result.precision = tp / (tp + fp)
        if tp + fn > 0:
            result.recall = tp / (tp + fn)
        if result.precision and result.recall:
            result.f1_score = 2 * (result.precision * result.recall) / (result.precision + result.recall)

    async def run_daily_experiment(
        self,
        validate_func: Callable,
        source_filter: Optional[List[str]] = None,
    ) -> ExperimentResult:
        """
        Run a daily experiment using today's validations.

        Convenience method that:
        1. Exports today's Redis validations to a dataset
        2. Runs an Opik experiment
        3. Returns the results for tracking

        Args:
            validate_func: Forseti validation function
            source_filter: Filter contributions by source

        Returns:
            ExperimentResult
        """
        today = date.today().isoformat()
        dataset_name = f"forseti-charter-{today}"
        experiment_name = f"forseti-daily-{today}"

        self._logger.info("DAILY_EXPERIMENT", date=today)

        # Export today's data to dataset
        self._dataset_manager.create_charter_dataset(dataset_name)
        count = self._dataset_manager.add_from_redis(
            dataset_name=dataset_name,
            date_str=today,
            source_filter=source_filter,
        )

        if count == 0:
            self._logger.warning("NO_DATA", message="No validations for today")
            return ExperimentResult(
                experiment_name=experiment_name,
                dataset_name=dataset_name,
            )

        # Sync to Opik
        if self._dataset_manager.opik_enabled:
            self._dataset_manager.sync_to_opik(dataset_name)

        # Run experiment
        return await self.run_experiment(
            dataset_name=dataset_name,
            validate_func=validate_func,
            experiment_name=experiment_name,
        )


# Convenience function for running the workflow
async def run_mockup_workflow(
    constat_factuel: str,
    idees_ameliorations: str = "",
    category: Optional[str] = None,
    validate_func: Optional[Callable] = None,
    use_llm: bool = True,
    llm_model: str = "mistral:latest",
    num_variations: int = 5,
    include_violations: bool = True,
) -> MockupWorkflowResult:
    """
    Convenience function to run the mockup workflow.

    Args:
        constat_factuel: Factual observation
        idees_ameliorations: Improvement ideas
        category: Contribution category
        validate_func: Forseti validation function
        use_llm: Use LLM for mutations
        llm_model: Ollama model name
        num_variations: Number of variations to generate
        include_violations: Include violation mutations

    Returns:
        MockupWorkflowResult
    """
    processor = MockupProcessor()
    config = MockupWorkflowConfig(
        num_variations=num_variations,
        include_violations=include_violations,
        use_llm=use_llm,
        llm_model=llm_model,
    )

    return await processor.run_workflow(
        constat_factuel=constat_factuel,
        idees_ameliorations=idees_ameliorations,
        category=category,
        validate_func=validate_func,
        config=config,
    )
