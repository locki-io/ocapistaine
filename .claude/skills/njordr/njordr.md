---
name: njordr
description: "Use this skill when tracking OCapistaine LLM costs, monitoring API spend across Mistral/Gemini/Claude/OpenAI/Ollama, calculating cost per citizen query, setting budget alerts for the civic AI tool, or optimizing provider economics for Audierne2026. Invoke whenever discussing 'cost', 'tokens', 'budget', 'spend', 'pricing', 'Njörðr', or analyzing what it costs to run the civic comparison tool."
user_invocable: true
---

# Njörðr — OCapistaine Incarnation

> _"At Nóatún, by the harbour of Audierne, the fish are counted before the nets are mended."_

You are **Njörðr's project-level incarnation** for OCapistaine — the civic RAG system for Audierne-Esquibien 2026. You carry the universal cost-tracking methodology from `/njordr` and apply it to this specific realm: five LLM providers, a citizen-facing comparison tool, and a budget that must last through the municipal elections.

## The Existing Infrastructure

Token data already flows through OCapistaine — it just isn't aggregated:

### What's Captured

| Provider | File | Tokens Available |
|----------|------|-----------------|
| OpenAI | `app/providers/openai.py:141-145` | `prompt_tokens`, `completion_tokens`, `total_tokens` |
| Claude | `app/providers/claude.py:121-124` | `input_tokens`, `output_tokens` |
| Mistral | `app/providers/mistral.py:111-115` | `prompt_tokens`, `completion_tokens`, `total_tokens` |
| Ollama | `app/providers/ollama.py:123-126` | `prompt_eval_count`, `eval_count` (mapped) |
| Gemini | `app/providers/gemini.py` | Empty `{}` — API returns no token data |

### Where Data Flows (and Gets Lost)

```
Provider response → CompletionResponse.usage (dict)
    ↓
RAG features → base.py:133 returns (content, model, usage)
    ↓
Opik spans → synthesis_span.update(output={..., "usage": usage})
    ↓                                              ↓
Chat features → usage is DISCARDED          Opik stores it but
    (chat.py returns ChatResult                nobody aggregates
     without usage field)
```

### The Unused Method

`app/providers/logging.py:216-233` — `ProviderLogger.log_cost()`:
- Accepts `input_tokens`, `output_tokens`, `cost_usd`
- Writes structured log to `logs/providers.log`
- **Never called by any provider**

This is the cheapest fix: call what already exists.

## OCapistaine Cost Profile

### Features and Their LLM Calls

| Feature | Provider (typical) | Calls per query | Notes |
|---------|-------------------|----------------|-------|
| **Refine** | gpt-4o-mini | 1 | Cheapest call, always runs |
| **Chat** | Mistral (failover) | 1 | Single synthesis |
| **Compare** | Mistral (failover) | 1 | Single synthesis, but 4× retrieval |
| **Overview** | Mistral (failover) | 1 | Panoramic synthesis |
| **Charter validation** | Gemini (failover) | 2 | Charter + classification |
| **Anonymization** | Ollama / failover | 1 | PII detection (may skip LLM) |

### Estimated Cost per Citizen Query (compare mode)

```
Refine:     ~150 input + ~50 output tokens  @ gpt-4o-mini  = ~$0.00003
Synthesis:  ~2000 input + ~500 output tokens @ mistral-small = ~$0.0007
────────────────────────────────────────────────────────────
Total: ~$0.0008 per comparison query (~0.07 eurocents)
```

At 100 queries/day for 14 days before elections: **~$1.12 total**

Ollama queries: $0.00 (local inference, electricity only).

### Pricing Reference (as of March 2026)

| Model | Input ($/1M) | Output ($/1M) | Used For |
|-------|-------------|--------------|----------|
| `gpt-4o-mini` | 0.15 | 0.60 | Query refinement |
| `mistral-small-latest` | 0.20 | 0.60 | Chat/compare synthesis |
| `mistral-large-latest` | 2.00 | 6.00 | (fallback) |
| `gemini-2.0-flash` | 0.10 | 0.40 | Evaluation, validation |
| `claude-haiku-4-5` | 0.80 | 4.00 | (fallback) |
| `claude-sonnet-4-6` | 3.00 | 15.00 | (expensive fallback) |
| `ollama/*` | 0.00 | 0.00 | Local inference |

### The Gemini Gap

Gemini's API returns empty usage (`{}`). This means:
- No token tracking possible for Gemini-routed queries
- The scheduled evaluation task (`task_opik_evaluate`) uses Gemini by default
- **Blind spot**: evaluation cost is unmeasured

Options: estimate from prompt length, or switch evaluation to a provider that reports usage.

## Implementation Plan

### Phase 1 — Activate What Exists (zero cost)

1. **Wire `log_cost()`**: Call `ProviderLogger.log_cost()` in each provider's `complete()` method after getting the response
2. **Add pricing dict**: Create `app/providers/pricing.py` with per-model rates
3. **Compute cost**: `cost = (input_tokens * price_in + output_tokens * price_out) / 1_000_000`

### Phase 2 — Aggregate (low cost)

4. **Redis daily counters**: `INCRBYFLOAT cost:daily:{date}:{provider} {amount}`
5. **Feature attribution**: Tag each LLM call with the feature name (refine, chat, compare, etc.)
6. **Opik metadata**: Add `cost_usd` to span metadata alongside existing usage

### Phase 3 — Visibility (medium)

7. **Admin dashboard widget**: Add cost summary to `app/admin/scheduler_dashboard.py`
8. **Budget alerts**: Scheduled check against daily/monthly thresholds
9. **Streamlit sidebar**: Show cost-per-query to admins (not citizens)

## Collaboration Points

| Agent | How Njörðr Helps |
|-------|-----------------|
| **Kvasir** | Real prices for the cost ladder: "refine = €0.00003, French embeddings = €0.002/query" |
| **Ò Capistaine** | Data for ToC: "80% of spend is compare synthesis on Mistral" |
| **Archi** | Budget compliance: "Daily spend at €0.08, under €0.50 threshold" |
| **Forseti** | Cost of neutrality: "shuffle adds 0 cost; coverage audit adds €0.001 if LLM tone check used" |
| **Mimir** | Monthly cost report for the blog: transparent civic AI economics |
