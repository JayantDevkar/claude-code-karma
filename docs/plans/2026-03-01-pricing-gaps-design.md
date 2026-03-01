# Fix Pricing Gaps in Token Economics

**Date**: 2026-03-01
**Status**: Approved
**Scope**: Single file change — `api/models/usage.py`

## Problem

Our cost analysis logic in `api/models/usage.py` is accurate for existing models but has gaps compared to Anthropic's official pricing (March 2026):

1. **Missing Sonnet 4.6** — new model not in `MODEL_PRICING`
2. **Missing Opus 4.6 long context** — $10/$37.50 when >200K input tokens
3. **Missing Sonnet 4 long context** — same $6/$22.50 threshold as Sonnet 4.5
4. **Missing Sonnet 3.7** — deprecated but still appears in session data
5. **Default fallback is Opus** — should be Sonnet since Claude Code defaults to Sonnet

## Research

Compared our implementation against two open-source tools:

| Repo | Accuracy | Key Issues |
|------|----------|------------|
| **Claud-ometer** | Broken | Opus 4.5/4.6 priced at $15/$75 (should be $5/$25) — 3x overcharge |
| **claude-spend** | Correct | Missing models, no long context, but rates are accurate |
| **Claude Karma (ours)** | Best | Just needs additive fixes below |

Official source: https://platform.claude.com/docs/en/about-claude/pricing

## Changes

### 1. Add missing models to `MODEL_PRICING`

```python
"claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "input_long": 6.0, "output_long": 22.5, "long_context_threshold": 200_000},
"claude-sonnet-3-7-20250219": {"input": 3.0, "output": 15.0},
```

### 2. Add long context to existing models

```python
"claude-opus-4-6": {"input": 5.0, "output": 25.0, "input_long": 10.0, "output_long": 37.5, "long_context_threshold": 200_000},
"claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0, "input_long": 6.0, "output_long": 22.5, "long_context_threshold": 200_000},
```

### 3. Add fuzzy patterns

```python
("sonnet-4-6", "claude-sonnet-4-6"),
("sonnet-3-7", "claude-sonnet-3-7-20250219"),
```

### 4. Change default fallback

```python
DEFAULT_PRICING_MODEL = "claude-sonnet-4-6"  # was "claude-opus-4-6"
```

## What stays unchanged

- Cost formula (`calculate_cost`) — no changes needed
- Cache multipliers (1.25x write / 0.1x read) — correct per official docs
- All existing model entries — only expanding some with long context fields
- API endpoints, DB schema, frontend — all untouched
- SQLite pre-computed costs only update on re-index
