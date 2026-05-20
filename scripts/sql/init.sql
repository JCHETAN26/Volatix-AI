-- ChainGuard-Core — operational schema.
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

COMMIT;
