# app/prompts/optimizer.py
"""
Prompt Optimization with Opik Agent Optimizer

Integrates opik-optimizer for automatic prompt improvement using:
- FewShotBayesianOptimizer - Select best examples for few-shot prompts
- MetaPromptOptimizer - LLM-generated prompt improvements
- EvolutionaryOptimizer - Genetic algorithm for prompt evolution

Usage:
    from app.prompts.optimizer import optimize_forseti_charter

    result = optimize_forseti_charter(
        dataset_name="forseti-charter-training",
        num_iterations=50,
    )
    print(f"Best prompt: {result.best_prompt}")
    print(f"Accuracy: {result.best_score:.2%}")
"""

from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass

from app.services import AgentLogger
from app.prompts.registry import get_registry
from app.prompts.constants import CATEGORIES

_logger = AgentLogger("prompt_optimizer")


@dataclass
class OptimizationResult:
    """Result of prompt optimization."""

    prompt_name: str
    best_prompt: str
    best_score: float
    iterations: int
    optimizer_type: str
    metadata: Dict[str, Any]


def get_optimizer(
    optimizer_type: str = "few_shot_bayesian",
    model: str = "gemini/gemini-2.0-flash",
    project_name: str = "forseti-optimization",
):
    """
    Get an Opik optimizer instance.

    Args:
        optimizer_type: One of "few_shot_bayesian", "meta_prompt", "evolutionary"
        model: LLM model for optimization
        project_name: Opik project name for tracking

    Returns:
        Optimizer instance
    """
    try:
        from opik_optimizer import (
            FewShotBayesianOptimizer,
            MetaPromptOptimizer,
            EvolutionaryOptimizer,
        )

        optimizers = {
            "few_shot_bayesian": FewShotBayesianOptimizer,
            "meta_prompt": MetaPromptOptimizer,
            "evolutionary": EvolutionaryOptimizer,
        }

        if optimizer_type not in optimizers:
            raise ValueError(f"Unknown optimizer: {optimizer_type}. Available: {list(optimizers.keys())}")

        optimizer_class = optimizers[optimizer_type]

        return optimizer_class(
            model=model,
            project_name=project_name,
        )

    except ImportError as e:
        _logger.error("OPTIMIZER_IMPORT_FAILED", error=str(e))
        raise ImportError("opik-optimizer not installed. Run: poetry add opik-optimizer")


def create_charter_metric() -> Callable:
    """
    Create a metric function for charter validation accuracy.

    Returns:
        Metric function that scores validation results
    """

    def charter_accuracy_metric(output: Dict[str, Any], expected: Dict[str, Any]) -> float:
        """
        Score charter validation accuracy.

        Args:
            output: Model output with is_valid, violations, etc.
            expected: Expected output from dataset

        Returns:
            Score between 0.0 and 1.0
        """
        score = 0.0
        weights = {
            "is_valid": 0.4,      # Most important
            "violations": 0.25,   # Important for rejection cases
            "category": 0.2,      # Category classification
            "confidence": 0.15,   # Calibration
        }

        # is_valid match
        if output.get("is_valid") == expected.get("is_valid"):
            score += weights["is_valid"]

        # Violations overlap (Jaccard similarity)
        out_violations = set(output.get("violations", []))
        exp_violations = set(expected.get("violations", []))
        if out_violations or exp_violations:
            intersection = len(out_violations & exp_violations)
            union = len(out_violations | exp_violations)
            if union > 0:
                score += weights["violations"] * (intersection / union)
        else:
            # Both empty = perfect match
            score += weights["violations"]

        # Category match
        if output.get("category") == expected.get("category"):
            score += weights["category"]

        # Confidence calibration (penalize overconfidence on wrong answers)
        confidence = output.get("confidence", 0.5)
        is_correct = output.get("is_valid") == expected.get("is_valid")
        if is_correct:
            score += weights["confidence"] * confidence
        else:
            score += weights["confidence"] * (1 - confidence)

        return score

    return charter_accuracy_metric


def create_validation_task(
    prompt_template: str,
    provider_name: str = "gemini",
    model: Optional[str] = None,
) -> Callable:
    """
    Create a task function for charter validation.

    Args:
        prompt_template: Prompt template with {title}, {body} placeholders
        provider_name: LLM provider
        model: Optional model override

    Returns:
        Task function for optimization
    """
    import json
    from app.providers import get_provider, Message

    provider = get_provider(provider_name, model=model, cache=False)

    async def validation_task(item: Dict[str, Any]) -> Dict[str, Any]:
        """Run validation on a single item."""
        input_data = item.get("input", item)

        # Format prompt
        prompt = prompt_template.format(
            title=input_data.get("title", ""),
            body=input_data.get("body", ""),
        )

        try:
            messages = [Message(role="user", content=prompt)]
            response = await provider.complete(messages, json_mode=True)
            content = response.content.strip()

            # Parse JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            return json.loads(content)

        except Exception as e:
            _logger.error("VALIDATION_TASK_ERROR", error=str(e))
            return {
                "is_valid": True,
                "violations": [],
                "confidence": 0.0,
                "reasoning": f"Error: {str(e)}",
            }

    return validation_task


def optimize_forseti_charter(
    dataset_name: str = "forseti-charter-training",
    prompt_name: str = "forseti.charter_validation",
    optimizer_type: str = "few_shot_bayesian",
    num_iterations: int = 50,
    model: str = "gemini/gemini-2.0-flash",
    save_to_opik: bool = True,
) -> OptimizationResult:
    """
    Optimize the Forseti charter validation prompt.

    Args:
        dataset_name: Opik dataset name for training
        prompt_name: Prompt to optimize
        optimizer_type: Optimizer type
        num_iterations: Number of optimization iterations
        model: LLM model for optimization
        save_to_opik: Whether to save optimized prompt to Opik

    Returns:
        OptimizationResult with best prompt and score
    """
    import opik

    _logger.info(
        "OPTIMIZATION_START",
        prompt=prompt_name,
        optimizer=optimizer_type,
        iterations=num_iterations,
    )

    # Get current prompt
    registry = get_registry()
    current_prompt = registry.get_prompt_template(prompt_name)

    # Get optimizer
    optimizer = get_optimizer(
        optimizer_type=optimizer_type,
        model=model,
        project_name="forseti-optimization",
    )

    # Get dataset
    client = opik.Opik()
    try:
        dataset = client.get_dataset(name=dataset_name)
    except Exception as e:
        _logger.error("DATASET_NOT_FOUND", name=dataset_name, error=str(e))
        raise ValueError(f"Dataset not found: {dataset_name}. Create it first with DatasetManager.")

    # Create metric
    metric = create_charter_metric()

    # Create task
    task = create_validation_task(current_prompt)

    # Run optimization
    try:
        result = optimizer.optimize(
            dataset=dataset,
            task=task,
            metric=metric,
            initial_prompt=current_prompt,
            num_iterations=num_iterations,
        )

        best_prompt = result.best_prompt
        best_score = result.best_score

        _logger.info(
            "OPTIMIZATION_COMPLETE",
            best_score=best_score,
            iterations=num_iterations,
        )

        # Save to Opik if requested
        if save_to_opik:
            from app.prompts.opik_sync import sync_prompt_to_opik

            sync_result = sync_prompt_to_opik(
                name=f"{prompt_name}.optimized",
                template=best_prompt,
                metadata={
                    "optimizer": optimizer_type,
                    "iterations": num_iterations,
                    "score": best_score,
                    "source_prompt": prompt_name,
                },
            )
            _logger.info("OPTIMIZED_PROMPT_SAVED", commit=sync_result.get("commit"))

        return OptimizationResult(
            prompt_name=prompt_name,
            best_prompt=best_prompt,
            best_score=best_score,
            iterations=num_iterations,
            optimizer_type=optimizer_type,
            metadata={
                "dataset": dataset_name,
                "model": model,
            },
        )

    except Exception as e:
        _logger.error("OPTIMIZATION_FAILED", error=str(e))
        raise


def run_prompt_experiment(
    prompt_name: str,
    dataset_name: str,
    experiment_name: Optional[str] = None,
    provider_name: str = "gemini",
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run an experiment with a specific prompt version.

    Args:
        prompt_name: Prompt to test
        dataset_name: Dataset for evaluation
        experiment_name: Optional experiment name
        provider_name: LLM provider
        model: Optional model override

    Returns:
        Experiment results with accuracy metrics
    """
    import opik
    from opik.evaluation import evaluate

    registry = get_registry()
    prompt_template = registry.get_prompt_template(prompt_name)

    # Create task
    task = create_validation_task(prompt_template, provider_name, model)

    # Create metric
    metric = create_charter_metric()

    # Get dataset
    client = opik.Opik()
    dataset = client.get_dataset(name=dataset_name)

    # Run experiment
    exp_name = experiment_name or f"{prompt_name}-{opik.datetime.now().isoformat()}"

    results = evaluate(
        experiment_name=exp_name,
        dataset=dataset,
        task=task,
        scoring_metrics=[metric],
    )

    _logger.info(
        "EXPERIMENT_COMPLETE",
        name=exp_name,
        prompt=prompt_name,
        dataset=dataset_name,
    )

    return {
        "experiment_name": exp_name,
        "prompt_name": prompt_name,
        "dataset_name": dataset_name,
        "results": results,
    }


# =============================================================================
# QUICK START FUNCTIONS
# =============================================================================

def quick_optimize(
    iterations: int = 20,
    optimizer: str = "meta_prompt",
) -> OptimizationResult:
    """
    Quick optimization with sensible defaults.

    Args:
        iterations: Number of iterations
        optimizer: Optimizer type

    Returns:
        OptimizationResult
    """
    return optimize_forseti_charter(
        dataset_name="forseti-charter-training",
        prompt_name="forseti.charter_validation",
        optimizer_type=optimizer,
        num_iterations=iterations,
        save_to_opik=True,
    )


def list_optimizers() -> List[str]:
    """List available optimizer types."""
    return ["few_shot_bayesian", "meta_prompt", "evolutionary"]
