"""End-to-end orchestration for a single transaction, with a full audit trail.

The engines in this project each did their own job correctly but nothing joined
them up: ``ElasticSIEMCorrelator`` evaluated rules, ``LSTMInferenceClient``
returned a probability, ``HybridThreatScorer`` blended them, ``PlaybookEngine``
wrote incidents, and the walkthrough scripts stitched those calls together by
hand, differently each time. Nothing recorded that a given transaction had
passed through all of them, and the inference call left no trace at all.

``TransactionPipeline`` is that missing seam. It runs the stages in order,
emits an ``AuditTrail`` record at each one, and carries a single correlation id
from the first stage into the Elasticsearch document and the incident, so the
whole decision is reconstructable afterwards from one id.

Stage order (see ``src.observability.audit.STAGES``)::

    TRANSACTION_RECEIVED
        -> RULES_EVALUATED         ElasticSIEMCorrelator, 5 rules
        -> INFERENCE_REQUESTED     tensor [1, 5, 13] built and sent
        -> INFERENCE_RECEIVED      probability + request id, latency, version
        -> DECISION_GENERATED      HybridThreatScorer blend + verdict
        -> PLAYBOOK_FIRED          only when FLAGGED
        -> ELASTICSEARCH_INDEXED   transaction document written
        -> DASHBOARD_UPDATED       dashboard's own query replayed to confirm

Inference is issued one transaction at a time rather than as a batch. A batch
call is faster and is what ``generate_transaction_batch.score_with_model`` uses
for volume, but it produces a single request id and one latency figure covering
fifty transactions, which cannot be attributed to any individual one. Per
transaction, every score gets its own traceable call.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np

from src.inference_client import InferenceResult, LSTMInferenceClient
from src.observability.audit import AuditTrail

logger = logging.getLogger(__name__)


@dataclass
class PipelineOutcome:
    """Everything the pipeline decided about one transaction."""

    correlation_id: str
    siem: dict[str, Any]
    inference: InferenceResult
    result: dict[str, Any]
    trail: AuditTrail
    document: dict[str, Any] = field(default_factory=dict)
    indexed_id: str | None = None

    @property
    def verdict(self) -> str:
        return str(self.result.get("verdict", "MONITOR"))

    @property
    def flagged(self) -> bool:
        return self.verdict == "FLAGGED"

    @property
    def triggered_rules(self) -> list[str]:
        return [r["rule_id"] for r in self.siem.get("rules", []) if r["triggered"]]


def build_windows(txns: list[Any]) -> np.ndarray:
    """Build one MinMax-scaled ``[5, 13]`` window per transaction, in input order.

    Lifted from ``generate_transaction_batch.score_with_model`` so the tensor
    the pipeline sends is byte-for-byte what the batch path sends — the feature
    order and scaling are part of the model, and two code paths computing them
    separately is how they drift.

    Windows at the start of a customer's history are zero-padded at the front,
    matching the convention ``engineer_features`` uses in training.

    Args:
        txns: Transactions exposing ``paysim_row()`` (``scripts.generate_transaction_batch.Txn``).

    Returns:
        Array of shape ``[len(txns), 5, 13]``, row *i* aligned to ``txns[i]``.

    Raises:
        FileNotFoundError: if the training scaler is absent. Refitting on a
            handful of rows sets the range from that batch's own extremes and
            the model returns confidently wrong answers rather than obviously
            broken ones — see MODEL_CARD Known Limitations item 2.
    """
    import pandas as pd

    from src.pipeline.feature_engineering import (
        DEFAULT_SCALER_PATH,
        SEQ_LEN,
        compute_feature_matrix,
    )
    from pathlib import Path

    if not Path(DEFAULT_SCALER_PATH).exists():
        raise FileNotFoundError(
            f"no fitted feature scaler at {DEFAULT_SCALER_PATH} — inference needs "
            "the training range, not a range refitted on this batch."
        )

    frame = pd.DataFrame([t.paysim_row() for t in txns])
    # compute_feature_matrix sorts by (nameOrig, step) and reindexes, so carry a
    # key through to map scored rows back to their original position.
    frame["_batch_idx"] = range(len(txns))
    features, ordered = compute_feature_matrix(frame, fit=False)

    windows = np.zeros((len(ordered), SEQ_LEN, features.shape[1]), dtype=np.float32)
    for _, group in ordered.groupby("nameOrig"):
        positions = group.index.to_numpy()
        for k, pos in enumerate(positions):
            start = max(0, k - SEQ_LEN + 1)
            seq = features[positions[start : k + 1]]
            windows[pos, SEQ_LEN - len(seq):] = seq

    aligned = np.zeros_like(windows)
    for pos in range(len(ordered)):
        aligned[int(ordered.at[pos, "_batch_idx"])] = windows[pos]
    return aligned


class TransactionPipeline:
    """Runs one transaction through every stage, auditing each.

    Usage::

        pipeline = TransactionPipeline(client, correlator, scorer, es_client=es)
        windows = build_windows(txns)
        for txn, window in zip(txns, windows):
            outcome = pipeline.process(txn, window)
    """

    def __init__(
        self,
        client: LSTMInferenceClient,
        correlator: Any,
        scorer: Any,
        es_client: Any | None = None,
        index: str | None = None,
        doc_builder: Any = None,
    ) -> None:
        """Wire the pipeline to its engines.

        Args:
            client: Inference client for the served LSTM.
            correlator: ElasticSIEMCorrelator instance.
            scorer: HybridThreatScorer instance (already holding a playbook).
            es_client: Elasticsearch client. None runs the pipeline in dry-run
                       mode — every stage up to DECISION_GENERATED still runs
                       and is audited; nothing is written.
            index: Target transaction index. Defaults to today's daily index.
            doc_builder: Callable building the ES document from a transaction.
                         Defaults to ``generate_transaction_batch.transaction_doc``.
        """
        self._client = client
        self._correlator = correlator
        self._scorer = scorer
        self._es = es_client
        self._index = index or (
            f"meridian-transactions-{datetime.now(tz=timezone.utc):%Y.%m.%d}"
        )
        if doc_builder is None:
            from scripts.generate_transaction_batch import transaction_doc
            doc_builder = transaction_doc
        self._doc_builder = doc_builder

    def index_context_only(self, txn: Any) -> str | None:
        """Index a transaction as plain history, without rules or inference.

        For context rows that exist only to populate a headline transaction's
        window — the same treatment ``fifty_dollar_pass_check.py`` and
        ``fraud_transaction_fail_check.py`` give their own prior transactions
        (``for t in txns[:-1]: es.index(...)``, never individually scored).
        ``txn.siem``/``txn.result`` are left at their dataclass defaults, so
        the written document carries an honest empty rule list and a MONITOR
        placeholder verdict rather than a fabricated one.

        Returns:
            The indexed document id, or None in dry-run mode (no ES client).
        """
        document = self._doc_builder(txn)
        if self._es is None:
            return None
        response = self._es.index(index=self._index, document=document, refresh=False)
        return response.get("_id")

    def process(self, txn: Any, window: np.ndarray, refresh: bool = True) -> PipelineOutcome:
        """Run every stage for one transaction and return the outcome.

        Args:
            txn: A ``Txn``. Mutated in place — ``siem``, ``result``,
                 ``lstm_score`` and ``lstm_source`` are set, matching what the
                 existing walkthrough scripts already expect to read back.
            window: This transaction's ``[5, 13]`` window from ``build_windows``.
            refresh: Force an index refresh so the document is immediately
                     queryable. Needed for the DASHBOARD_UPDATED check to mean
                     anything on the transaction that just landed.

        Returns:
            PipelineOutcome carrying the audit trail and every stage's result.
        """
        trail = AuditTrail(customer_id=txn.customer_id, es_client=self._es)
        event = txn.event()

        # -- 1. received ----------------------------------------------------
        trail.record("TRANSACTION_RECEIVED", detail={
            "amount": txn.amount,
            "merchant_id": txn.merchant[0],
            "merchant_name": txn.merchant[1],
            "location": txn.location,
            "channel": txn.channel,
            "txn_type": txn.txn_type,
            "timestamp": txn.when.isoformat(),
            "prior_transactions_known": len(txn.recent),
        })

        # -- 2. rules -------------------------------------------------------
        siem = self._correlator.evaluate(event)
        txn.siem = siem
        triggered = [r["rule_id"] for r in siem["rules"] if r["triggered"]]
        trail.record("RULES_EVALUATED", detail={
            "rules_evaluated": len(siem["rules"]),
            "triggered": triggered or ["none"],
            "triggered_count": len(triggered),
            "siem_score": siem["siem_score"],
            "rule_engine_decision": "FLAG" if triggered else "ALLOW",
        })

        # -- 3/4. inference -------------------------------------------------
        tensor = window[np.newaxis, ...] if window.ndim == 2 else window
        trail.record("INFERENCE_REQUESTED", detail={
            "endpoint": self._client.predict_url,
            "input_shape": list(tensor.shape),
            "input_elements": int(tensor.size),
            "input_dtype": str(tensor.dtype),
            "padded_timesteps": int((tensor[0].sum(axis=1) == 0).sum()),
        })
        try:
            inference = self._client.predict_batch_with_metadata(tensor)
            txn.lstm_score = round(float(inference.scores[0]), 4)
            txn.lstm_source = "model"
            trail.record("INFERENCE_RECEIVED", detail={
                "request_id": inference.request_id,
                "model": f"{inference.metadata.get('model_name', '?')}"
                         f":{inference.model_version}",
                "anomaly_probability": txn.lstm_score,
                "output_elements": inference.output_elements,
                "server_latency_ms": inference.metadata.get("latency_ms"),
                "round_trip_ms": inference.round_trip_ms,
                "decision_threshold": inference.metadata.get("decision_threshold"),
                "model_verdict": (
                    "ANOMALY"
                    if txn.lstm_score >= float(
                        inference.metadata.get("decision_threshold", 0.90))
                    else "NORMAL"
                ),
            })
        except Exception as exc:  # noqa: BLE001
            trail.record("INFERENCE_RECEIVED", status="ERROR", detail={
                "error": f"{type(exc).__name__}: {exc}",
            })
            raise

        # -- 5. decision ----------------------------------------------------
        result = self._scorer.score(txn.lstm_score, siem, event)
        txn.result = result
        trail.record("DECISION_GENERATED", detail={
            "lstm_score": result["lstm_score"],
            "siem_score": result["siem_score"],
            "formula": f"{result['lstm_score']} x 0.60 + {result['siem_score']} x 0.40",
            "threat_score": result["threat_score"],
            "verdict": result["verdict"],
            "trigger_reason": result["trigger_reason"],
        })

        # -- 6. playbook ----------------------------------------------------
        if result.get("playbook_fired"):
            incident = result.get("incident") or {}
            trail.record("PLAYBOOK_FIRED", detail={
                "incident_id": incident.get("incident_id"),
                "severity": incident.get("severity"),
                "action": incident.get("action"),
                "status": incident.get("status"),
            })

        # -- 7. elasticsearch -----------------------------------------------
        document = self._doc_builder(txn)
        # Stamp the trail's id and the inference provenance onto the stored
        # document. This is what makes a score in Elasticsearch traceable back
        # to the call that produced it.
        document["correlation_id"] = trail.correlation_id
        document["inference"] = {
            "request_id": inference.request_id,
            "model_name": inference.metadata.get("model_name"),
            "model_version": inference.model_version,
            "inference_timestamp": inference.metadata.get("inference_timestamp"),
            "server_latency_ms": inference.metadata.get("latency_ms"),
            "round_trip_ms": inference.round_trip_ms,
            "input_shape": inference.metadata.get("input_shape"),
            "input_elements": inference.input_elements,
            "output_elements": inference.output_elements,
            "decision_threshold": inference.metadata.get("decision_threshold"),
        }

        outcome = PipelineOutcome(
            correlation_id=trail.correlation_id,
            siem=siem,
            inference=inference,
            result=result,
            trail=trail,
            document=document,
        )

        if self._es is None:
            trail.record("ELASTICSEARCH_INDEXED", status="SKIPPED",
                         detail={"reason": "dry run - no Elasticsearch client"})
            trail.record("DASHBOARD_UPDATED", status="SKIPPED",
                         detail={"reason": "dry run - nothing was indexed"})
            return outcome

        try:
            response = self._es.index(
                index=self._index, document=document, refresh=refresh
            )
            outcome.indexed_id = response.get("_id")
            trail.record("ELASTICSEARCH_INDEXED", detail={
                "index": self._index,
                "document_id": outcome.indexed_id,
                "result": response.get("result"),
                "correlation_id": trail.correlation_id,
            })
        except Exception as exc:  # noqa: BLE001
            trail.record("ELASTICSEARCH_INDEXED", status="ERROR",
                         detail={"error": f"{type(exc).__name__}: {exc}"})
            trail.flush()
            return outcome

        # -- 8. dashboard visibility ----------------------------------------
        self._verify_dashboard_visibility(trail)
        trail.flush()
        return outcome

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _verify_dashboard_visibility(self, trail: AuditTrail) -> None:
        """Replay the dashboard's own query and confirm the row is available.

        This process cannot observe a browser painting a row, and recording
        that it did would be a claim it is not in a position to make. What it
        can do is run the exact query ``useElasticPolling`` runs — recent 16 by
        ``@timestamp`` descending — and report whether this correlation id is
        in the result set the next poll will receive.
        """
        try:
            # ``correlation_id`` gets Elasticsearch's default dynamic mapping
            # for a new string field: ``text`` (analysed, tokenised on
            # hyphens) plus a ``.keyword`` sub-field (exact match). A ``term``
            # query against the bare field name matches against the analysed
            # tokens ("txn", "f8b7b739...") and silently never matches the
            # literal id — found the hard way, matching by hand against the
            # feed below while this query reported not-found for the same id.
            found = self._es.search(
                index="meridian-transactions-*",
                query={"term": {"correlation_id.keyword": trail.correlation_id}},
                size=1,
            )
            queryable = found["hits"]["total"]["value"] > 0

            feed = self._es.search(
                index="meridian-transactions-*",
                sort="@timestamp:desc",
                size=16,
            )
            feed_ids = [
                h["_source"].get("correlation_id") for h in feed["hits"]["hits"]
            ]
            position = (
                feed_ids.index(trail.correlation_id) + 1
                if trail.correlation_id in feed_ids
                else None
            )

            trail.record(
                "DASHBOARD_UPDATED",
                status="OK" if queryable else "ERROR",
                detail={
                    "dashboard_query": "meridian-transactions-*/_search"
                                       "?sort=@timestamp:desc&size=16",
                    "queryable": queryable,
                    "in_recent_feed": position is not None,
                    "feed_position": position,
                    "note": "confirmed available to the dashboard's next poll; "
                            "browser render is not observable from here",
                },
            )
        except Exception as exc:  # noqa: BLE001
            trail.record("DASHBOARD_UPDATED", status="ERROR",
                         detail={"error": f"{type(exc).__name__}: {exc}"})
