-- Volatix-AI — operational schema.
-- Apply once after `make infra-up`: `make init-postgres`.
--
-- Tables:
--   feature_log         feature rows mirrored from the C++ engine; the
--                       Airflow DAG retrains LightGBM on this nightly.
--   anomaly_score_log   classifier output (one row per scored frame).
--   model_registry      LightGBM artifacts produced by Airflow, plus the
--                       CV metrics they were promoted with.
--   agent_report        Phase 4.2 LangGraph audit output. Created here
--                       so the Forensic Investigator / Settlement &
--                       Enforcer have somewhere to land.
--
-- All tables are idempotent (IF NOT EXISTS); safe to rerun.

BEGIN;

CREATE TABLE IF NOT EXISTS feature_log (
    id            BIGSERIAL PRIMARY KEY,
    ts_ns         BIGINT      NOT NULL,
    symbol        VARCHAR(16) NOT NULL,
    ofi           DOUBLE PRECISION NOT NULL,
    realized_vol  DOUBLE PRECISION NOT NULL,
    mid_price     DOUBLE PRECISION NOT NULL,
    total_volume  DOUBLE PRECISION NOT NULL,
    window_count  INTEGER     NOT NULL,
    label         SMALLINT,            -- nullable; backfilled by Airflow
    inserted_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS feature_log_ts_idx ON feature_log (ts_ns);
CREATE INDEX IF NOT EXISTS feature_log_symbol_ts_idx ON feature_log (symbol, ts_ns);

CREATE TABLE IF NOT EXISTS anomaly_score_log (
    id            BIGSERIAL PRIMARY KEY,
    ts_ns         BIGINT      NOT NULL,
    symbol        VARCHAR(16) NOT NULL,
    score         DOUBLE PRECISION NOT NULL,
    model_id      BIGINT,
    inserted_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS anomaly_score_log_ts_idx ON anomaly_score_log (ts_ns);
CREATE INDEX IF NOT EXISTS anomaly_score_log_score_idx ON anomaly_score_log (score DESC);

CREATE TABLE IF NOT EXISTS model_registry (
    id            BIGSERIAL PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL,
    training_day  DATE        NOT NULL,
    n_train       INTEGER     NOT NULL,
    n_features    INTEGER     NOT NULL,
    cv_auc_mean   DOUBLE PRECISION NOT NULL,
    cv_auc_std    DOUBLE PRECISION NOT NULL,
    model_path    TEXT        NOT NULL,
    model_bytes   BYTEA       NOT NULL
);
CREATE INDEX IF NOT EXISTS model_registry_day_idx ON model_registry (training_day DESC);

CREATE TABLE IF NOT EXISTS agent_report (
    id            BIGSERIAL PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    case_id       UUID        NOT NULL UNIQUE,
    symbol        VARCHAR(16) NOT NULL,
    ts_ns         BIGINT      NOT NULL,
    anomaly_score DOUBLE PRECISION NOT NULL,
    confidence    DOUBLE PRECISION,         -- Agent 2 output, 0..1
    enforced      BOOLEAN     NOT NULL DEFAULT FALSE,  -- Agent 3 actioned?
    rationale_md  TEXT        NOT NULL,
    evidence      JSONB       NOT NULL DEFAULT '{}'::JSONB
);
CREATE INDEX IF NOT EXISTS agent_report_ts_idx ON agent_report (ts_ns DESC);
CREATE INDEX IF NOT EXISTS agent_report_symbol_idx ON agent_report (symbol);

-- ===========================================================================
-- Post-1.0 "Microsecond Receipt" additions.
-- Every stage now stamps the wall-clock time it observed the case so the
-- dashboard can render a complete T+0..T+enforced timeline. The case_id
-- column is the join key — it comes from the C++ engine inside the
-- FeatureFrame and flows through every Python service unchanged.
-- All ADDs are idempotent; safe to rerun.
-- ===========================================================================

ALTER TABLE feature_log
    ADD COLUMN IF NOT EXISTS case_id        BIGINT,
    ADD COLUMN IF NOT EXISTS wire_ts_ns     BIGINT,
    ADD COLUMN IF NOT EXISTS compute_ts_ns  BIGINT;

ALTER TABLE anomaly_score_log
    ADD COLUMN IF NOT EXISTS case_id        BIGINT,
    ADD COLUMN IF NOT EXISTS wire_ts_ns     BIGINT,
    ADD COLUMN IF NOT EXISTS compute_ts_ns  BIGINT,
    ADD COLUMN IF NOT EXISTS score_ts_ns    BIGINT;

ALTER TABLE agent_report
    ADD COLUMN IF NOT EXISTS pipeline_case_id BIGINT,
    ADD COLUMN IF NOT EXISTS wire_ts_ns       BIGINT,
    ADD COLUMN IF NOT EXISTS compute_ts_ns    BIGINT,
    ADD COLUMN IF NOT EXISTS score_ts_ns      BIGINT,
    ADD COLUMN IF NOT EXISTS verdict_ts_ns    BIGINT,
    ADD COLUMN IF NOT EXISTS enforced_ts_ns   BIGINT;

CREATE INDEX IF NOT EXISTS feature_log_case_idx        ON feature_log (case_id);
CREATE INDEX IF NOT EXISTS anomaly_score_log_case_idx  ON anomaly_score_log (case_id);
CREATE INDEX IF NOT EXISTS agent_report_pipeline_idx   ON agent_report (pipeline_case_id);

-- ===========================================================================
-- Phase 6 — LLM evaluation & observability.
-- prompt_version on agent_report: which prompt template / model / temp
-- produced this row. Backfills historical rows as 'v0' so per-version
-- regression queries don't need to special-case nulls. The nightly
-- eval DAG writes one eval_run per (prompt_version, fixture_revision)
-- with the rolled-up Ragas + freeze_correctness metrics; eval_case_result
-- holds the per-case scores so the dashboard can drill down.
-- ===========================================================================

ALTER TABLE agent_report
    ADD COLUMN IF NOT EXISTS prompt_version VARCHAR(32) NOT NULL DEFAULT 'v0';
CREATE INDEX IF NOT EXISTS agent_report_prompt_version_idx
    ON agent_report (prompt_version, created_at DESC);

CREATE TABLE IF NOT EXISTS eval_run (
    id                BIGSERIAL PRIMARY KEY,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    prompt_version    VARCHAR(32) NOT NULL,
    fixture_revision  VARCHAR(64) NOT NULL,  -- sha256 of cases.json
    llm_provider      VARCHAR(32) NOT NULL,
    llm_model         VARCHAR(64) NOT NULL,
    n_cases           INTEGER     NOT NULL,
    -- rolled-up metrics across all cases
    freeze_correctness DOUBLE PRECISION,     -- binary match vs. expected_action
    faithfulness       DOUBLE PRECISION,     -- Ragas, vs. RAG context
    answer_relevancy   DOUBLE PRECISION,     -- Ragas, vs. feature vector
    p50_latency_ms     DOUBLE PRECISION,
    p95_latency_ms     DOUBLE PRECISION,
    notes              TEXT
);
CREATE INDEX IF NOT EXISTS eval_run_version_idx
    ON eval_run (prompt_version, created_at DESC);

CREATE TABLE IF NOT EXISTS eval_case_result (
    id                BIGSERIAL PRIMARY KEY,
    eval_run_id       BIGINT NOT NULL REFERENCES eval_run (id) ON DELETE CASCADE,
    case_id           VARCHAR(64) NOT NULL,        -- fixture-local id
    expected_action   VARCHAR(16) NOT NULL,        -- FREEZE | MONITOR | NO_ACTION
    actual_action     VARCHAR(16),
    correct           BOOLEAN NOT NULL,
    faithfulness      DOUBLE PRECISION,
    answer_relevancy  DOUBLE PRECISION,
    latency_ms        DOUBLE PRECISION,
    agent_output      JSONB NOT NULL DEFAULT '{}'::JSONB
);
CREATE INDEX IF NOT EXISTS eval_case_result_run_idx
    ON eval_case_result (eval_run_id);

COMMIT;
