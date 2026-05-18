"""Streaming consumer: financial-features → LightGBM → anomaly-scores.

Reads 64-byte FeatureFrame messages off the `financial-features` Kafka
topic (produced by the C++ engine in Phase 2.3), runs them through a
LightGBM classifier loaded from disk, and republishes the resulting
anomaly score on `anomaly-scores` for downstream consumers (the Phase 4.2
LangGraph agent cluster). Optionally mirrors each row into PostgreSQL
`feature_log` + `anomaly_score_log` so the Airflow DAG can retrain on
real traffic.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from kafka import KafkaConsumer, KafkaProducer

from .feature_frame import FeatureFrame
from .model import AnomalyModel

log = logging.getLogger("classifier")


@dataclass(frozen=True, slots=True)
class Config:
    brokers: str
    in_topic: str
    out_topic: str
    group_id: str
    model_path: Path
    score_threshold: float
    write_to_postgres: bool
    poll_timeout_ms: int

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            brokers=os.getenv("KAFKA_BROKERS", "chain-kafka.default.svc.cluster.local:9092"),
            in_topic=os.getenv("INPUT_TOPIC", "financial-features"),
            out_topic=os.getenv("OUTPUT_TOPIC", "anomaly-scores"),
            group_id=os.getenv("CONSUMER_GROUP", "chainguard-classifier"),
            model_path=Path(os.getenv("MODEL_PATH", "/models/baseline.txt")),
            score_threshold=float(os.getenv("SCORE_THRESHOLD", "0.85")),
            write_to_postgres=os.getenv("WRITE_POSTGRES", "true").lower() == "true",
            poll_timeout_ms=int(os.getenv("POLL_TIMEOUT_MS", "1000")),
        )


def make_consumer(cfg: Config) -> KafkaConsumer:
    return KafkaConsumer(
        cfg.in_topic,
        bootstrap_servers=cfg.brokers,
        group_id=cfg.group_id,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda v: v,  # raw bytes — we struct.unpack ourselves
        client_id="chainguard-classifier",
    )


def make_producer(cfg: Config) -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=cfg.brokers,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if isinstance(k, str) else k,
        client_id="chainguard-classifier",
        linger_ms=5,
    )


def build_score_payload(frame: FeatureFrame, score: float, threshold: float) -> dict:
    return {
        "schema": "chainguard.anomaly_score.v1",
        "ts_ns": frame.ts_ns,
        "symbol": frame.symbol,
        "score": score,
        "high_risk": score >= threshold,
        "features": {
            "ofi": frame.ofi,
            "realized_vol": frame.realized_vol,
            "mid_price": frame.mid_price,
            "total_volume": frame.total_volume,
            "window_count": frame.window_count,
        },
    }


class ClassifierService:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.model = AnomalyModel.load(cfg.model_path)
        self.consumer = make_consumer(cfg)
        self.producer = make_producer(cfg)
        self._pg_conn = None
        self._stop = False
        if cfg.write_to_postgres:
            try:
                from . import db
                self._pg_conn = db.connect_from_env()
                log.info("connected to postgres for feature_log mirror")
            except Exception as exc:
                log.warning("postgres mirror disabled: %s", exc)

    def shutdown(self, *_: object) -> None:
        log.info("shutdown requested")
        self._stop = True

    def run(self) -> int:
        log.info(
            "classifier ready: in=%s out=%s model=%s threshold=%.2f",
            self.cfg.in_topic,
            self.cfg.out_topic,
            self.cfg.model_path,
            self.cfg.score_threshold,
        )
        n = 0
        n_high = 0
        last_report = time.monotonic()

        while not self._stop:
            batch = self.consumer.poll(timeout_ms=self.cfg.poll_timeout_ms, max_records=256)
            for _tp, records in batch.items():
                for record in records:
                    try:
                        frame = FeatureFrame.from_bytes(record.value)
                    except ValueError as exc:
                        log.warning("skipping malformed message: %s", exc)
                        continue
                    score = self.model.predict_one(frame.as_feature_vector())
                    payload = build_score_payload(frame, score, self.cfg.score_threshold)
                    self.producer.send(self.cfg.out_topic, key=frame.symbol, value=payload)
                    n += 1
                    if payload["high_risk"]:
                        n_high += 1
                    self._mirror_to_postgres(frame, score)

            now = time.monotonic()
            if now - last_report >= 5.0:
                log.info("processed=%d high_risk=%d", n, n_high)
                last_report = now

        log.info("shutting down: processed=%d high_risk=%d", n, n_high)
        self.producer.flush(timeout=5.0)
        self.consumer.close()
        if self._pg_conn:
            self._pg_conn.close()
        return 0

    def _mirror_to_postgres(self, frame: FeatureFrame, score: float) -> None:
        if not self._pg_conn:
            return
        try:
            from . import db
            db.insert_feature_log(self._pg_conn, frame, label=None)
            db.insert_anomaly_score(self._pg_conn, frame, score, model_id=None)
            self._pg_conn.commit()
        except Exception as exc:
            log.warning("postgres mirror failed; will rollback: %s", exc)
            try:
                self._pg_conn.rollback()
            except Exception:
                pass
