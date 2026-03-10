# app/mockup/refine_view.py
"""
Query Refinement Test View

Streamlit UI component for testing OCapistaine query refinement + wording correction.
Loads test cases from refine_queries.json, runs QueryRefiner, compares against expected.

Features:
- Load test cases from mockup data
- Single query test with custom input
- Batch run all cases with summary stats
- Side-by-side expected vs actual comparison
- Tag/difficulty filtering
- Export results to Opik datasets
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

import streamlit as st

from app.services.logging import MockupLogger

_logger = MockupLogger("refine_view")

# Path to test data
_DATA_PATH = Path(__file__).parent / "data" / "refine_queries.json"


def _load_test_cases() -> list[dict]:
    """Load test cases from refine_queries.json."""
    if not _DATA_PATH.exists():
        return []
    with open(_DATA_PATH) as f:
        data = json.load(f)
    return data.get("test_cases", [])


_OPENAI_PROV = {"provider": "openai", "model_key": "gpt-4o-mini", "model_id": "gpt-4o-mini"}


def _run_refine(query: str, history: list[dict] | None = None) -> dict:
    """Run QueryRefiner on a single query with Opik tracing. Returns result dict."""
    from app.agents.ocapistaine.features.refine import QueryRefiner
    from app.agents.tracing import get_tracer

    start = time.time()
    try:
        refiner = QueryRefiner()
        if not refiner.available:
            return {"success": False, "error": "QueryRefiner unavailable (no OpenAI key)"}

        result = asyncio.run(refiner.refine(question=query, history=history))
        elapsed_ms = (time.time() - start) * 1000

        # Trace to Opik (mirrors OCapistaineAgent._trace_preprocess_spans)
        tracer = get_tracer()
        trace_input = {"original_query": query}
        if history:
            trace_input["history"] = history

        with tracer.start_trace(
            name="mockup_query_refine",
            input=trace_input,
            tags=["mockup", "query_refine", "ocapistaine"],
            provider_info=_OPENAI_PROV,
        ):
            if result.was_corrected:
                with tracer.span(
                    name="query_wording",
                    input={"original_query": result.original},
                    span_type="llm",
                    provider_info=_OPENAI_PROV,
                ) as wording_span:
                    wording_span.update(output={
                        "corrected_query": result.query,
                        "corrections": result.corrections,
                        "corrections_count": len(result.corrections),
                    })

            if result.was_refined:
                with tracer.span(
                    name="query_refine",
                    input={"original_query": result.original},
                    span_type="llm",
                    provider_info=_OPENAI_PROV,
                ) as refine_span:
                    refine_span.update(output={
                        "refined_query": result.query,
                        "original_length": len(result.original),
                        "refined_length": len(result.query),
                        "detected_category": result.category,
                    })

        return {
            "success": True,
            "output": result.query,
            "corrections": result.corrections,
            "category": result.category,
            "was_refined": result.was_refined,
            "was_corrected": result.was_corrected,
            "elapsed_ms": elapsed_ms,
        }
    except Exception as e:
        elapsed_ms = (time.time() - start) * 1000
        _logger.error("REFINE_ERROR", error=str(e))
        return {"success": False, "error": str(e), "elapsed_ms": elapsed_ms}


def _score_result(result: dict, test_case: dict) -> dict:
    """Score a single result against expected output. Returns score dict."""
    import unicodedata

    def _strip(s: str) -> str:
        return "".join(
            c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
        ).lower().strip().rstrip("?").strip()

    if not result.get("success"):
        return {"total": 0.0, "correction": 0.0, "meaning": 0.0, "quality": 0.0}

    output = result["output"]
    expected_query = test_case.get("expected_query", "")
    expected_corrections = test_case.get("expected_corrections", [])
    actual_corrections = result.get("corrections", [])

    # Correction accuracy
    correction_score = 0.0
    if expected_corrections:
        matched = 0
        for exp in expected_corrections:
            parts = exp.split("\u2192")  # →
            if len(parts) == 2:
                target = parts[1].strip().lower()
                if target in output.lower():
                    matched += 1
        recall = matched / len(expected_corrections)
        extra = max(0, len(actual_corrections) - len(expected_corrections))
        precision = 1.0 - min(extra * 0.2, 0.5)
        correction_score = recall * 0.7 + precision * 0.3
    else:
        correction_score = 1.0 if not actual_corrections else 0.5

    # Quality: compare with expected
    quality_score = 0.0
    if expected_query:
        if _strip(output) == _strip(expected_query):
            quality_score = 1.0
        else:
            exp_words = {w for w in _strip(expected_query).split() if len(w) > 3}
            out_words = {w for w in _strip(output).split() if len(w) > 3}
            if exp_words:
                quality_score = len(exp_words & out_words) / len(exp_words)

    total = correction_score * 0.5 + quality_score * 0.5
    return {
        "total": round(total, 2),
        "correction": round(correction_score, 2),
        "quality": round(quality_score, 2),
    }


def refine_test_view(user_id: str) -> None:
    """Render the query refinement testing view."""
    st.subheader("🔍 Query Refinement Test (OCapistaine)")
    st.markdown(
        "Test the **query refiner** pre-processing step: wording correction + semantic expansion. "
        "Uses `gpt-4o-mini` (~$0.0001/query)."
    )

    # Mode selection
    mode = st.radio(
        "Mode",
        options=["test_cases", "single_query", "batch_run"],
        format_func=lambda x: {
            "test_cases": "📋 Browse Test Cases",
            "single_query": "✏️ Single Query Test",
            "batch_run": "🚀 Batch Run All",
        }[x],
        horizontal=True,
        key="refine_mode",
    )

    st.markdown("---")

    if mode == "test_cases":
        _test_cases_view(user_id)
    elif mode == "single_query":
        _single_query_view(user_id)
    elif mode == "batch_run":
        _batch_run_view(user_id)


def _test_cases_view(user_id: str) -> None:
    """Browse and run individual test cases."""
    cases = _load_test_cases()
    if not cases:
        st.warning("No test cases found in `refine_queries.json`")
        return

    # Tag filter
    all_tags = sorted({t for c in cases for t in c.get("tags", [])})
    col1, col2 = st.columns(2)
    with col1:
        tag_filter = st.multiselect("Filter by tag", options=all_tags, default=[], key="refine_tag_filter")
    with col2:
        difficulty_filter = st.selectbox(
            "Difficulty",
            options=["all", "easy", "medium", "hard"],
            key="refine_difficulty_filter",
        )

    # Apply filters
    filtered = cases
    if tag_filter:
        filtered = [c for c in filtered if any(t in c.get("tags", []) for t in tag_filter)]
    if difficulty_filter != "all":
        filtered = [c for c in filtered if c.get("difficulty") == difficulty_filter]

    st.info(f"**{len(filtered)}** / {len(cases)} test cases")

    # Display each case
    for case in filtered:
        case_id = case["id"]
        tags = " ".join(f"`{t}`" for t in case.get("tags", []))
        difficulty = case.get("difficulty", "?")
        diff_icon = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}.get(difficulty, "⚪")

        with st.expander(f"{diff_icon} **{case_id}** — `{case['original_query']}` {tags}", expanded=False):
            col_in, col_exp = st.columns(2)
            with col_in:
                st.markdown("**Input:**")
                st.code(case["original_query"])
                if case.get("history"):
                    st.markdown("**History:**")
                    for h in case["history"]:
                        role_icon = "👤" if h["role"] == "user" else "🤖"
                        st.caption(f"{role_icon} {h['content'][:80]}...")
            with col_exp:
                st.markdown("**Expected:**")
                if case.get("expected_query"):
                    st.code(case["expected_query"])
                if case.get("expected_corrections"):
                    for c in case["expected_corrections"]:
                        st.caption(f"  ✏️ {c}")
                if case.get("expected_category"):
                    st.caption(f"  📁 {case['expected_category']}")

            if case.get("notes"):
                st.caption(f"📝 {case['notes']}")

            # Run button
            if st.button("▶️ Run", key=f"run_{case_id}"):
                with st.spinner("Refining..."):
                    result = _run_refine(case["original_query"], case.get("history"))

                if result.get("success"):
                    score = _score_result(result, case)
                    _display_refine_result(result, case, score)
                    # Cache result
                    st.session_state[f"refine_result_{case_id}"] = (result, score)
                else:
                    st.error(f"Error: {result.get('error')}")

            # Show cached result if exists
            cached = st.session_state.get(f"refine_result_{case_id}")
            if cached and not st.session_state.get(f"_just_ran_{case_id}"):
                result, score = cached
                _display_refine_result(result, case, score)


def _single_query_view(user_id: str) -> None:
    """Test a single custom query."""
    st.markdown("Enter a query to test refinement:")

    query = st.text_input("Query", value="van praet ecole", key="refine_single_input")

    use_history = st.checkbox("Include conversation history", value=False, key="refine_use_history")
    history = None
    if use_history:
        history_text = st.text_area(
            "History (JSON array of {role, content})",
            value='[{"role": "user", "content": "Que propose Passons à l\'Action sur la culture ?"}, '
            '{"role": "assistant", "content": "Passons à l\'Action propose de rénover la salle des fêtes..."}]',
            height=100,
            key="refine_history_input",
        )
        try:
            history = json.loads(history_text)
        except json.JSONDecodeError:
            st.warning("Invalid JSON for history")
            history = None

    if st.button("▶️ Refine", type="primary", key="refine_single_btn"):
        if not query.strip():
            st.warning("Enter a query first")
            return

        with st.spinner("Refining..."):
            result = _run_refine(query, history)

        if result.get("success"):
            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Original:**")
                st.code(query)
            with col2:
                st.markdown("**Refined:**")
                st.code(result["output"])

            # Corrections
            if result.get("corrections"):
                st.markdown("**Corrections:**")
                for c in result["corrections"]:
                    st.markdown(f"  ✏️ `{c}`")

            # Category
            if result.get("category"):
                st.markdown(f"**Category:** 📁 `{result['category']}`")

            # Flags
            flags = []
            if result.get("was_corrected"):
                flags.append("✏️ Corrected")
            if result.get("was_refined"):
                flags.append("🔄 Refined")
            if result.get("category"):
                flags.append(f"📁 {result['category']}")
            if not result.get("was_corrected") and not result.get("was_refined"):
                flags.append("✅ No change")

            elapsed = result.get("elapsed_ms", 0)
            st.caption(f"{' | '.join(flags)} | ⏱️ {elapsed:.0f}ms")
        else:
            st.error(f"Error: {result.get('error')}")


def _batch_run_view(user_id: str) -> None:
    """Run all test cases in batch and display summary."""
    cases = _load_test_cases()
    if not cases:
        st.warning("No test cases found")
        return

    # Filter options
    all_tags = sorted({t for c in cases for t in c.get("tags", [])})
    tag_filter = st.multiselect("Filter by tag", options=all_tags, default=[], key="batch_tag_filter")
    if tag_filter:
        cases = [c for c in cases if any(t in c.get("tags", []) for t in tag_filter)]

    st.info(f"**{len(cases)}** test cases to run")

    # Cost estimate
    est_cost = len(cases) * 0.0001
    st.caption(f"Estimated cost: ~${est_cost:.4f} (gpt-4o-mini)")

    if st.button("🚀 Run Batch", type="primary", key="batch_run_btn"):
        results = []
        progress = st.progress(0, text="Running...")

        for i, case in enumerate(cases):
            progress.progress((i + 1) / len(cases), text=f"Running {case['id']}...")
            result = _run_refine(case["original_query"], case.get("history"))
            score = _score_result(result, case) if result.get("success") else None
            results.append({"case": case, "result": result, "score": score})

        progress.empty()

        # Store in session
        st.session_state["batch_results"] = results

    # Display results if available
    results = st.session_state.get("batch_results")
    if not results:
        return

    _display_batch_summary(results)


def _display_refine_result(result: dict, case: dict, score: dict) -> None:
    """Display a single refinement result with comparison."""
    col_got, col_score = st.columns([3, 1])
    with col_got:
        st.markdown("**Got:**")
        st.code(result["output"])
        if result.get("corrections"):
            corr_str = ", ".join(f"`{c}`" for c in result["corrections"])
            st.caption(f"Corrections: {corr_str}")
        if result.get("category"):
            expected_cat = case.get("expected_category")
            cat_match = ""
            if expected_cat:
                cat_match = " ✅" if result["category"] == expected_cat else f" ❌ expected {expected_cat}"
            st.caption(f"📁 Category: **{result['category']}**{cat_match}")
    with col_score:
        total = score["total"]
        color = "🟢" if total >= 0.8 else "🟡" if total >= 0.5 else "🔴"
        st.metric("Score", f"{total:.0%}", help=f"Correction: {score['correction']:.0%} | Quality: {score['quality']:.0%}")
        st.caption(f"{color} corr={score['correction']:.0%} qual={score['quality']:.0%}")

    elapsed = result.get("elapsed_ms", 0)
    flags = []
    if result.get("was_corrected"):
        flags.append("✏️ Corrected")
    if result.get("was_refined"):
        flags.append("🔄 Refined")
    if result.get("category"):
        flags.append(f"📁 {result['category']}")
    st.caption(f"{' | '.join(flags) or '✅ No change'} | ⏱️ {elapsed:.0f}ms")


def _display_batch_summary(results: list[dict]) -> None:
    """Display summary of batch run results."""
    st.markdown("---")
    st.markdown("### Batch Results")

    # Aggregate stats
    total = len(results)
    successes = [r for r in results if r["result"].get("success")]
    failures = [r for r in results if not r["result"].get("success")]
    scores = [r["score"]["total"] for r in results if r["score"]]

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total", total)
    with col2:
        st.metric("Success", len(successes))
    with col3:
        avg_score = sum(scores) / len(scores) if scores else 0
        st.metric("Avg Score", f"{avg_score:.0%}")
    with col4:
        avg_ms = sum(r["result"].get("elapsed_ms", 0) for r in successes) / len(successes) if successes else 0
        st.metric("Avg Latency", f"{avg_ms:.0f}ms")

    if failures:
        st.error(f"{len(failures)} failures")

    # Score distribution by difficulty
    st.markdown("#### By difficulty")
    for diff in ["easy", "medium", "hard"]:
        diff_results = [r for r in results if r["case"].get("difficulty") == diff and r["score"]]
        if diff_results:
            diff_scores = [r["score"]["total"] for r in diff_results]
            avg = sum(diff_scores) / len(diff_scores)
            icon = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}[diff]
            st.caption(f"{icon} **{diff}**: {avg:.0%} avg ({len(diff_results)} cases)")

    # Score distribution by tag
    st.markdown("#### By tag")
    all_tags = sorted({t for r in results for t in r["case"].get("tags", [])})
    for tag in all_tags:
        tag_results = [r for r in results if tag in r["case"].get("tags", []) and r["score"]]
        if tag_results:
            tag_scores = [r["score"]["total"] for r in tag_results]
            avg = sum(tag_scores) / len(tag_scores)
            color = "🟢" if avg >= 0.8 else "🟡" if avg >= 0.5 else "🔴"
            st.caption(f"{color} `{tag}`: {avg:.0%} ({len(tag_results)})")

    # Detailed results table
    st.markdown("#### Details")
    for r in results:
        case = r["case"]
        result = r["result"]
        score = r["score"]

        if not result.get("success"):
            st.markdown(f"🔴 **{case['id']}** — Error: {result.get('error', '?')}")
            continue

        total_score = score["total"] if score else 0
        color = "🟢" if total_score >= 0.8 else "🟡" if total_score >= 0.5 else "🔴"

        with st.expander(
            f"{color} **{case['id']}** — {total_score:.0%} | `{case['original_query']}`",
            expanded=(total_score < 0.5),
        ):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Expected:**")
                st.code(case.get("expected_query", "(none)"))
            with col2:
                st.markdown("**Got:**")
                st.code(result["output"])

            if result.get("corrections"):
                st.caption("Corrections: " + ", ".join(f"`{c}`" for c in result["corrections"]))
            if case.get("expected_corrections"):
                st.caption("Expected: " + ", ".join(f"`{c}`" for c in case["expected_corrections"]))

            st.caption(
                f"corr={score['correction']:.0%} qual={score['quality']:.0%} "
                f"| ⏱️ {result.get('elapsed_ms', 0):.0f}ms"
            )
