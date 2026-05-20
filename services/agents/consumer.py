"""Kafka consumer that drives the 3-tier agent cluster (Phase 4.2).

  anomaly-scores topic
      │
      ▼  filter high_risk == True
  build CaseState
      │
      ▼
  LangGraph.invoke → forensic → auditor → (enforcer | finalize) → END
      │
      ▼
  agent_report row written by the enforcer / finalizer
"""

from __future__ import annotations

import json
import logging
import os
import signal
import time
import uuid
from dataclasses import dataclass
from typing import Any

from kafka import KafkaConsumer

from .graph import build_graph
from .llm import make_chat_llm
from .state import CaseState
from .tools import db as db_tool
from .tools.rag import QdrantRag


log = logging.getLogger("agents")


@dataclass(frozen=True, slots=True)
class Config:
    brokers: str
    in_topic: str
    group_id: str
    write_to_postgres: bool
    poll_timeout_ms: int
    high_risk_only: bool

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            brokers=os.getenv("KAFKA_BROKERS", "chain-kafka.default.svc.cluster.local:9092"),
            in_topic=os.getenv("INPUT_TOPIC", "anomaly-scores"),
            group_id=os.getenv("CONSUMER_GROUP", "chainguard-agents"),
            write_to_postgres=os.getenv("WRITE_POSTGRES", "true").lower() == "true",
            poll_timeout_ms=int(os.getenv("POLL_TIMEOUT_MS", "1000")),
            high_risk_only=os.getenv("HIGH_RISK_ONLY", "true").lower() == "true",
        )


def _make_consumer(cfg: Config) -> KafkaConsumer:
    return KafkaConsumer(
        cfg.in_topic,
        bootstrap_servers=cfg.brokers,
        group_id=cfg.group_id,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        client_id="chainguard-agents",
    )


def _opt_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _payload_to_state(payload: dict[str, Any]) -> CaseState:
    return CaseState(
        case_id=uuid.uuid4(),
        symbol=str(payload.get("symbol", "?")),
        ts_ns=int(payload.get("ts_ns", 0)),
        anomaly_score=float(payload.get("score", 0.0)),
        features={k: float(v) for k, v in (payload.get("features") or {}).items()},
        pipeline_case_id=_opt_int(payload.get("case_id")),
        wire_ts_ns=_opt_int(payload.get("wire_ts_ns")),
        compute_ts_ns=_opt_int(payload.get("compute_ts_ns")),
        score_ts_ns=_opt_int(payload.get("score_ts_ns")),
    )


class AgentService:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.llm = make_chat_llm()
        self.rag = QdrantRag()
        self.graph = build_graph(self.llm, self.rag)
        self.consumer = _make_consumer(cfg)
        self._pg_conn = None
        self._stop = False
        if cfg.write_to_postgres:
            try:
                self._pg_conn = db_tool.connect_from_env()
                log.info("connected to postgres for agent_report mirror")
            except Exception as exc:
                log.warning("agent_report persistence disabled: %s", exc)

    def shutdown(self, *_: object) -> None:
        log.info("shutdown requested")
        self._stop = True

    def run(self) -> int:
        log.info(
            "agent service ready: in=%s group=%s high_risk_only=%s",
            self.cfg.in_topic,
            self.cfg.group_id,
            self.cfg.high_risk_only,
        )
        n_seen = 0
        n_processed = 0
        n_enforced = 0
        last_report = time.monotonic()

        while not self._stop:
            batch = self.consumer.poll(timeout_ms=self.cfg.poll_timeout_ms, max_records=64)
            for _tp, records in batch.items():
                for record in records:
                    n_seen += 1
                    payload = record.value
                    if self.cfg.high_risk_only and not payload.get("high_risk"):
                        continue
                    try:
                        state = _payload_to_state(payload)
                        final_dict = self.graph.invoke(state)
                        # Stamp the verdict timestamp BEFORE constructing the
                        # final CaseState so it lives alongside enforced_ts_ns
                        # in the same row.
                        final_dict["verdict_ts_ns"] = time.time_ns()
                        final = CaseState.model_validate(final_dict)
                        n_processed += 1
                        if final.enforcement_action is not None:
                            n_enforced += 1
                        self._persist(final)
                    except Exception as exc:
                        log.exception("graph invocation failed: %s", exc)

            now = time.monotonic()
            if now - last_report >= 5.0:
                log.info(
                    "seen=%d processed=%d enforced=%d",
                    n_seen,
                    n_processed,
                    n_enforced,
                )
                last_report = now

        log.info("shutting down: seen=%d processed=%d enforced=%d",
                 n_seen, n_processed, n_enforced)
        self.consumer.close()
        self.rag.close()
        if self._pg_conn:
            self._pg_conn.close()
        return 0

    def _persist(self, state: CaseState) -> None:
        if not self._pg_conn:
            return
        try:
            # Evidence carries the replay payload: per-stage prompts +
            # rationales so the dashboard's Replay UI can animate the
            # decision without re-running anything. Shape is documented
            # in web/lib/types.ts as AgentReportEvidence.
            evidence = {
                "schema": "chainguard.agent_evidence.v1",
                "features": state.features,
                "rag_matches": [m.model_dump() for m in state.rag_matches],
                "stages": {
                    "forensic": {
                        "prompt": state.forensic_prompt,
                        "rationale": state.forensic_rationale,
                    },
                    "auditor": {
                        "prompt": state.audit_prompt,
                        "rationale": state.audit_rationale,
                        "confidence": state.confidence,
                    },
                    "enforcer": {
                        "prompt": state.enforcement_prompt,
                        "rationale": state.enforcement_rationale,
                        "action": (
                            state.enforcement_action.model_dump()
                            if state.enforcement_action is not None
                            else None
                        ),
                    },
                },
                # Kept at the top level for backwards compatibility with
                # any consumer that read the v0 layout.
                "enforcement_action": (
                    state.enforcement_action.model_dump()
                    if state.enforcement_action is not None
                    else None
                ),
            }
            db_tool.insert_agent_report(
                self._pg_conn,
                case_id=state.case_id,
                symbol=state.symbol,
                ts_ns=state.ts_ns,
                anomaly_score=state.anomaly_score,
                confidence=state.confidence,
                enforced=state.enforcement_action is not None,
                rationale_md=state.rationale_md,
                evidence=evidence,
                pipeline_case_id=state.pipeline_case_id,
                wire_ts_ns=state.wire_ts_ns,
                compute_ts_ns=state.compute_ts_ns,
                score_ts_ns=state.score_ts_ns,
                verdict_ts_ns=state.verdict_ts_ns,
                enforced_ts_ns=state.enforced_ts_ns,
            )
        except Exception as exc:
            log.warning("agent_report insert failed: %s", exc)
            try:
                self._pg_conn.rollback()
            except Exception:
                pass


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    cfg = Config.from_env()
    service = AgentService(cfg)
    signal.signal(signal.SIGINT, service.shutdown)
    signal.signal(signal.SIGTERM, service.shutdown)
    return service.run()


if __name__ == "__main__":
    raise SystemExit(main())
