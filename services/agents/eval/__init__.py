"""ChainGuard-Core agent evaluation harness (Phase 6).

Ragas + binary-correctness scoring over a curated 200-case fixture,
replayed through the LangGraph agent cluster nightly via Airflow.
Designed to catch prompt regressions before they reach production.

See ``build-plan.md`` Phase 6 and the README's *LLM Evaluation &
Observability* section.
"""
