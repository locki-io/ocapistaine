"""
RAG Model Evaluation — Opik Experiment Runner

Creates an Opik dataset from curated test questions, then runs
opik.evaluate() for each model configuration. Results are tracked
as experiments in Opik for comparison.

Metrics:
    - AnswerRelevance (Opik built-in): Does the answer address the question?
    - Hallucination (Opik built-in): Is the answer grounded in context?
    - rag_confidence (custom): Self-reported retrieval confidence
    - response_quality (custom): Length, source count, French quality heuristics

Usage:
    poetry run python scripts/eval_rag_models.py
    poetry run python scripts/eval_rag_models.py --models ollama_llama3.2,mistral_small
    poetry run python scripts/eval_rag_models.py --questions factual_person,overview_elections
    poetry run python scripts/eval_rag_models.py --dry-run  # preview without running
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import argparse
import time
from datetime import datetime

from app.services.logging import get_logger

logger = get_logger("evaluation")

# =============================================================================
# TEST QUESTIONS — curated dataset for RAG evaluation
# =============================================================================

TEST_QUESTIONS = {
    # --- Factual retrieval (specific person/fact) ---
    "factual_person": {
        "question": "Qui sont les colistiers de Didier Guillon ?",
        "mode": "chat",
        "expected_keywords": ["Passons à l'Action", "Guillon"],
        "category": "factual",
    },
    "factual_tete_liste": {
        "question": "Qui est la tête de liste de S'unir pour Audierne-Esquibien ?",
        "mode": "chat",
        "expected_keywords": ["Van Praët", "Michel"],
        "category": "factual",
    },
    # --- Thematic search (topic across sources) ---
    "thematic_economy": {
        "question": "Que proposent les listes sur l'économie locale et le commerce ?",
        "mode": "chat",
        "expected_keywords": ["économie", "commerce", "centre"],
        "category": "thematic",
    },
    "thematic_school": {
        "question": "Quelles sont les propositions concernant les écoles et la jeunesse ?",
        "mode": "chat",
        "expected_keywords": ["école", "jeunesse", "éducation"],
        "category": "thematic",
    },
    # --- Overview / panoramic ---
    "overview_elections": {
        "question": "Que sais-tu sur les élections municipales d'Audierne 2026 ?",
        "mode": "chat",
        "expected_keywords": ["Audierne", "2026", "liste"],
        "category": "overview",
    },
    "overview_lists": {
        "question": "Quelles sont les listes candidates aux municipales ?",
        "mode": "chat",
        "expected_keywords": ["Audierne", "liste"],
        "category": "overview",
    },
    # --- Comparison mode ---
    "compare_economy": {
        "question": "Que proposent les listes sur l'économie locale ?",
        "mode": "compare",
        "lists": ["audierne2026", "paa", "ca", "spae", "csnf"],
        "expected_keywords": ["économie"],
        "category": "compare",
    },
    "compare_environment": {
        "question": "Comparez les propositions environnementales des listes.",
        "mode": "compare",
        "lists": ["audierne2026", "paa", "ca", "spae"],
        "expected_keywords": ["environnement"],
        "category": "compare",
    },
    # --- Edge cases ---
    "edge_no_answer": {
        "question": "Quel est le budget de la commune pour 2025 ?",
        "mode": "chat",
        "expected_keywords": ["budget"],
        "category": "edge",
    },
    "edge_council": {
        "question": "Quels sujets ont été discutés au conseil municipal de janvier 2026 ?",
        "mode": "chat",
        "expected_keywords": ["conseil", "janvier"],
        "category": "edge",
    },
}

# =============================================================================
# MODEL CONFIGURATIONS TO TEST
# =============================================================================

MODEL_CONFIGS = {
    "ollama_llama3.2": {
        "provider": "ollama",
        "model_key": "llama3.2:latest",
        "label": "Ollama llama3.2",
    },
    "claude_haiku": {
        "provider": "claude",
        "model_key": "haiku",
        "label": "Claude Haiku 4.5",
    },
    "mistral_small": {
        "provider": "mistral",
        "model_key": "small",
        "label": "Mistral Small",
    },
    "openai_gpt4o_mini": {
        "provider": "openai",
        "model_key": "gpt-4o-mini",
        "label": "OpenAI gpt-4o-mini",
    },
}


# =============================================================================
# OPIK DATASET CREATION
# =============================================================================


def create_opik_dataset(questions: dict, dataset_name: str) -> str:
    """
    Create an Opik dataset from test questions.

    Each item has:
        - input: question text + metadata
        - expected_output: expected keywords for validation

    Returns:
        dataset_name if created successfully
    """
    from opik import Opik

    client = Opik()

    # Delete existing dataset with same name (idempotent)
    try:
        existing = client.get_dataset(name=dataset_name)
        if existing:
            client.delete_dataset(name=dataset_name)
            logger.info(f"Deleted existing dataset: {dataset_name}")
    except Exception:
        pass

    dataset = client.create_dataset(
        name=dataset_name,
        description=f"RAG evaluation questions ({len(questions)} items)",
    )

    items = []
    for qid, qconfig in questions.items():
        item = {
            "input": {
                "question_id": qid,
                "question": qconfig["question"],
                "mode": qconfig["mode"],
                "category": qconfig.get("category", "general"),
            },
            "expected_output": {
                "keywords": qconfig.get("expected_keywords", []),
            },
        }
        if qconfig["mode"] == "compare":
            item["input"]["lists"] = qconfig.get("lists", [])
        items.append(item)

    dataset.insert(items)
    logger.info(f"Created dataset '{dataset_name}' with {len(items)} items")
    return dataset_name


# =============================================================================
# EVALUATION TASK FACTORIES (one per model)
# =============================================================================


def create_rag_eval_task(provider: str, model_id: str):
    """
    Create an Opik evaluation task function for a specific model.

    The task runs OCapistaineAgent.chat() or .compare() and returns
    results formatted for Opik metrics.
    """

    def evaluation_task(dataset_item: dict) -> dict:
        """Run RAG query and return results for Opik scoring."""
        from app.agents.ocapistaine import OCapistaineAgent

        input_data = dataset_item.get("input", {})
        question = input_data["question"]
        mode = input_data.get("mode", "chat")
        lists = input_data.get("lists", [])

        agent = OCapistaineAgent(
            provider_name=provider,
            model_override=model_id,
        )

        loop = asyncio.new_event_loop()
        try:
            if mode == "compare" and lists:
                result = loop.run_until_complete(
                    agent.compare(question=question, list_names=lists)
                )
            else:
                result = loop.run_until_complete(
                    agent.chat(question=question)
                )
        finally:
            loop.close()

        result_dict = result.to_dict()
        response = result_dict["response"]
        sources = result_dict.get("sources", [])

        # Build context from sources for Opik RAG metrics
        context = []
        for s in sources:
            title = s.get("title", "")
            doc_id = s.get("doc_id", "")
            list_name = s.get("list_name", "")
            context.append(f"{title} ({list_name}) [{doc_id}]")

        return {
            # Standard Opik fields for built-in metrics
            "input": question,
            "output": response,
            "context": context if context else ["No sources retrieved"],
            # Custom fields for custom metrics
            "confidence": result_dict.get("confidence", 0),
            "sources_count": len(sources),
            "model": result_dict.get("model", ""),
            "response_length": len(response),
            "mode": mode,
            "question_id": input_data.get("question_id", ""),
        }

    return evaluation_task


# =============================================================================
# CUSTOM OPIK METRICS
# =============================================================================


def create_rag_confidence_metric():
    """Custom metric: agent self-reported confidence score."""
    from opik.evaluation.metrics import base_metric, score_result

    class RAGConfidence(base_metric.BaseMetric):
        name = "rag_confidence"

        def score(self, output: str, confidence: float = 0, **kwargs) -> score_result.ScoreResult:
            return score_result.ScoreResult(
                name=self.name,
                value=confidence,
                reason=f"Agent confidence: {confidence:.1%}",
            )

    return RAGConfidence()


def create_source_coverage_metric():
    """Custom metric: number of sources retrieved (normalized 0-1)."""
    from opik.evaluation.metrics import base_metric, score_result

    class SourceCoverage(base_metric.BaseMetric):
        name = "source_coverage"

        def score(self, output: str, sources_count: int = 0, **kwargs) -> score_result.ScoreResult:
            # Normalize: 0 sources = 0, 5+ sources = 1.0
            normalized = min(sources_count / 5.0, 1.0)
            return score_result.ScoreResult(
                name=self.name,
                value=normalized,
                reason=f"{sources_count} sources retrieved",
            )

    return SourceCoverage()


def create_keyword_match_metric():
    """Custom metric: checks if expected keywords appear in the response."""
    from opik.evaluation.metrics import base_metric, score_result

    class KeywordMatch(base_metric.BaseMetric):
        name = "keyword_match"

        def score(self, output: str, expected_output: dict = None, **kwargs) -> score_result.ScoreResult:
            if not expected_output:
                return score_result.ScoreResult(name=self.name, value=1.0, reason="No keywords to check")

            keywords = expected_output.get("keywords", [])
            if not keywords:
                return score_result.ScoreResult(name=self.name, value=1.0, reason="No keywords to check")

            output_lower = output.lower()
            matches = sum(1 for kw in keywords if kw.lower() in output_lower)
            score_val = matches / len(keywords)

            return score_result.ScoreResult(
                name=self.name,
                value=score_val,
                reason=f"{matches}/{len(keywords)} keywords found",
            )

    return KeywordMatch()


def create_response_quality_metric():
    """Custom metric: response length and basic quality heuristics."""
    from opik.evaluation.metrics import base_metric, score_result

    class ResponseQuality(base_metric.BaseMetric):
        name = "response_quality"

        def score(self, output: str, **kwargs) -> score_result.ScoreResult:
            length = len(output)

            # Score based on response characteristics
            score_val = 0.0
            reasons = []

            # Length: too short is bad, 200-2000 chars is ideal
            if length < 50:
                score_val += 0.0
                reasons.append("too short")
            elif length < 200:
                score_val += 0.3
                reasons.append("short")
            elif length < 2000:
                score_val += 0.5
                reasons.append("good length")
            else:
                score_val += 0.4
                reasons.append("long")

            # Contains French structure markers
            if any(marker in output for marker in ["**", "- ", "### ", "1. "]):
                score_val += 0.2
                reasons.append("structured")

            # Not an error message
            if not any(err in output.lower() for err in ["erreur", "error", "failed"]):
                score_val += 0.3
                reasons.append("no errors")
            else:
                reasons.append("contains error")

            return score_result.ScoreResult(
                name=self.name,
                value=min(score_val, 1.0),
                reason=", ".join(reasons),
            )

    return ResponseQuality()


# =============================================================================
# MAIN EVALUATION
# =============================================================================


def build_metrics(use_judge: bool = True) -> list:
    """Build the metrics list for evaluation."""
    metrics = [
        create_rag_confidence_metric(),
        create_source_coverage_metric(),
        create_keyword_match_metric(),
        create_response_quality_metric(),
    ]

    if use_judge:
        try:
            from opik.evaluation.metrics import AnswerRelevance, Hallucination

            metrics.append(AnswerRelevance())
            metrics.append(Hallucination())
            logger.info("Opik judge metrics enabled (AnswerRelevance, Hallucination)")
        except Exception as e:
            logger.warning(f"Opik judge metrics unavailable: {e}")

    return metrics


def run_evaluation(
    models: dict,
    questions: dict,
    use_judge: bool = True,
    dry_run: bool = False,
):
    """Run Opik experiments for each model."""
    from opik.evaluation import evaluate
    from app.providers.config import get_model_id

    timestamp = datetime.now().strftime("%Y%m%d-%H%M")

    # Step 1: Create dataset
    dataset_name = f"rag-eval-{timestamp}"
    print(f"\n  Dataset: {dataset_name} ({len(questions)} questions)")

    if dry_run:
        print("\n  DRY RUN — would test these models:")
        for mid, mconf in models.items():
            model_full = get_model_id(mconf["provider"], mconf["model_key"])
            print(f"    - {mconf['label']} ({model_full})")
        print(f"\n  With {len(questions)} questions and {4 + (2 if use_judge else 0)} metrics")
        return

    dataset_name = create_opik_dataset(questions, dataset_name)

    # Step 2: Build metrics
    scoring_metrics = build_metrics(use_judge=use_judge)
    print(f"  Metrics: {[m.name for m in scoring_metrics]}")

    # Step 3: Run experiment per model
    from opik import Opik

    client = Opik()
    dataset = client.get_dataset(name=dataset_name)

    results_summary = {}

    for model_id, model_config in models.items():
        provider = model_config["provider"]
        model_key = model_config["model_key"]
        label = model_config["label"]
        model_full = get_model_id(provider, model_key)

        experiment_name = f"rag-{model_id}-{timestamp}"

        print(f"\n{'='*60}")
        print(f"  Experiment: {experiment_name}")
        print(f"  Model: {label} ({model_full})")
        print(f"{'='*60}")

        # Create evaluation task for this model
        eval_task = create_rag_eval_task(provider, model_full)

        # Run Opik evaluate
        start = time.time()
        try:
            eval_result = evaluate(
                experiment_name=experiment_name,
                dataset=dataset,
                task=eval_task,
                scoring_metrics=scoring_metrics,
                experiment_config={
                    "provider": provider,
                    "model": model_full,
                    "label": label,
                    "questions_count": len(questions),
                    "timestamp": timestamp,
                },
            )
            elapsed = time.time() - start

            results_summary[model_id] = {
                "label": label,
                "model": model_full,
                "experiment_name": experiment_name,
                "elapsed_s": round(elapsed, 1),
                "status": "success",
            }
            print(f"  Completed in {elapsed:.1f}s")

        except Exception as e:
            elapsed = time.time() - start
            results_summary[model_id] = {
                "label": label,
                "model": model_full,
                "experiment_name": experiment_name,
                "elapsed_s": round(elapsed, 1),
                "status": "error",
                "error": str(e),
            }
            print(f"  ERROR: {e}")

    # Step 4: Summary
    print(f"\n{'='*60}")
    print("  EXPERIMENTS COMPLETE")
    print(f"{'='*60}")
    print(f"\n  Dataset: {dataset_name}")
    print(f"  View results in Opik dashboard\n")

    for mid, summary in results_summary.items():
        status = "OK" if summary["status"] == "success" else "FAIL"
        print(f"  [{status}] {summary['label']:<22} {summary['elapsed_s']:>6.1f}s  {summary['experiment_name']}")

    print(f"\n  Compare experiments in Opik: filter by dataset '{dataset_name}'")


def main():
    parser = argparse.ArgumentParser(description="RAG Model Evaluation via Opik")
    parser.add_argument(
        "--models",
        type=str,
        default=None,
        help="Comma-separated model IDs (e.g. ollama_llama3.2,mistral_small)",
    )
    parser.add_argument(
        "--questions",
        type=str,
        default=None,
        help="Comma-separated question IDs (e.g. factual_person,overview_elections)",
    )
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help="Skip Opik judge metrics (AnswerRelevance, Hallucination) — faster, no OpenAI needed",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would run without executing",
    )
    args = parser.parse_args()

    # Select models
    if args.models:
        model_keys = [m.strip() for m in args.models.split(",")]
        models = {k: MODEL_CONFIGS[k] for k in model_keys if k in MODEL_CONFIGS}
        if not models:
            print(f"No valid models. Available: {', '.join(MODEL_CONFIGS.keys())}")
            sys.exit(1)
    else:
        models = MODEL_CONFIGS

    # Select questions
    if args.questions:
        q_keys = [q.strip() for q in args.questions.split(",")]
        questions = {k: TEST_QUESTIONS[k] for k in q_keys if k in TEST_QUESTIONS}
        if not questions:
            print(f"No valid questions. Available: {', '.join(TEST_QUESTIONS.keys())}")
            sys.exit(1)
    else:
        questions = TEST_QUESTIONS

    print(f"\n  OCapistaine RAG Evaluation — {datetime.now():%Y-%m-%d %H:%M}")
    print(f"  Models: {', '.join(m['label'] for m in models.values())}")
    print(f"  Questions: {len(questions)}")
    print(f"  Judge metrics: {'disabled' if args.no_judge else 'enabled'}")

    run_evaluation(
        models=models,
        questions=questions,
        use_judge=not args.no_judge,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
