"""Audit trail for the detection pipeline.

Every transaction that enters the system gets one ``AuditTrail``, keyed by a
correlation id that is carried through every downstream record — the
Elasticsearch transaction document, the incident the playbook writes, and the
inference call itself. Given a correlation id, an analyst can reconstruct the
whole decision without guessing which log line belongs to which payment.

Why this exists
---------------
The engines were already doing the work — rules evaluated, model called,
verdict blended, incident written — but each stage only left an unstructured
``logger.info`` behind, keyed to nothing. Two transactions a second apart
produced interleaved lines with no way to separate them, and the inference call
left no trace at all (``LSTMInferenceClient.predict`` returned a bare float and
discarded the response's latency, request id and model version).

APRA CPS 234 requires an audit trail sufficient to reconstruct an incident
response; PCI DSS v4.0 Requirement 10 requires the same for cardholder-data
systems. A per-stage record with a shared correlation id is the minimum shape
that satisfies either.

Stages
------
The pipeline is linear, and the stage list is ordered. Not every transaction
visits every stage — ``PLAYBOOK_FIRED`` only appears on a FLAGGED verdict — but
a transaction never visits them out of order, so a trail that skips a stage it
should have reached is itself the finding.

``DASHBOARD_UPDATED`` deserves a note. The backend cannot observe a browser
rendering a row, and recording that it did would be a claim this process is not
in a position to make. What it records instead is verifiable: the dashboard's
*own* Elasticsearch query was replayed and the correlation id was found in the
result set, so the row is available to the next poll. The detail carries the
query that was run.

Sinks
-----
Records go to two places, independently:

* a JSONL file under ``logs/audit/`` — always written, needs no cluster, and is
  what the walkthrough scripts print from;
* ``meridian-audit-YYYY.MM.dd`` in Elasticsearch — only when a client is
  supplied, so unit tests and dry runs never need a live stack.

A failure in either sink is logged and swallowed. An audit trail that raises
and takes down the transaction it was auditing would be worse than one that
loses a record.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_AUDIT_INDEX_PREFIX = "meridian-audit"

# Default JSONL sink. Relative to the repo root so a script run from anywhere
# writes to the same place.
_DEFAULT_SINK_DIR = Path(__file__).resolve().parent.parent.parent / "logs" / "audit"

#: The ordered stages a transaction passes through. Order is meaningful —
#: ``AuditTrail.gaps()`` reports stages that were expected but never reached.
STAGES: tuple[str, ...] = (
    "TRANSACTION_RECEIVED",
    "RULES_EVALUATED",
    "INFERENCE_REQUESTED",
    "INFERENCE_RECEIVED",
    "DECISION_GENERATED",
    "PLAYBOOK_FIRED",
    "ELASTICSEARCH_INDEXED",
    "DASHBOARD_UPDATED",
)

#: Stages every transaction must reach regardless of verdict. ``PLAYBOOK_FIRED``
#: is excluded — a MONITOR verdict correctly never fires one.
_ALWAYS_EXPECTED: frozenset[str] = frozenset(STAGES) - {"PLAYBOOK_FIRED"}


@dataclass
class AuditRecord:
    """One stage transition in a transaction's journey through the pipeline."""

    correlation_id: str
    customer_id: str
    stage: str
    status: str
    sequence: int
    timestamp: str
    elapsed_ms: float
    detail: dict[str, Any] = field(default_factory=dict)

    def to_document(self) -> dict[str, Any]:
        """The Elasticsearch document shape.

        Carries both ``@timestamp`` (what Kibana data views and ECS tooling
        expect) and ``timestamp``, matching the convention already used by
        ``PlaybookEngine._build_incident`` so both consumers work without a
        migration.
        """
        return {
            "@timestamp": self.timestamp,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
            "customer_id": self.customer_id,
            "stage": self.stage,
            "status": self.status,
            "sequence": self.sequence,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "detail": self.detail,
            "event": {"category": "process", "type": "info", "kind": "event"},
        }


class AuditTrail:
    """Collects the ordered audit record for a single transaction.

    Usage::

        trail = AuditTrail(customer_id="CUST-52210", es_client=es)
        trail.record("TRANSACTION_RECEIVED", detail={"amount": 50.0})
        ...
        trail.flush()          # writes every record to Elasticsearch
        print(trail.render())  # human-readable trace

    The correlation id is generated at construction unless one is supplied, so
    a caller that already has an id (a request header, an upstream trace) can
    keep the same value rather than minting a second one.
    """

    def __init__(
        self,
        customer_id: str,
        correlation_id: str | None = None,
        es_client: Any | None = None,
        sink_dir: Path | None = None,
        write_jsonl: bool = True,
    ) -> None:
        """Open a trail.

        Args:
            customer_id: The customer the transaction belongs to.
            correlation_id: Reuse an existing id, or None to mint one.
            es_client: Elasticsearch client for the ``meridian-audit-*`` sink.
                       None keeps the trail file-only — the mode unit tests and
                       dry runs use.
            sink_dir: Override the JSONL directory. Defaults to ``logs/audit/``.
            write_jsonl: Set False to suppress the file sink entirely.
        """
        self.correlation_id = correlation_id or f"TXN-{uuid.uuid4().hex[:16].upper()}"
        self.customer_id = customer_id
        self.records: list[AuditRecord] = []
        self._es = es_client
        self._sink_dir = sink_dir or _DEFAULT_SINK_DIR
        self._write_jsonl = write_jsonl
        # Monotonic, so elapsed_ms is unaffected by a wall-clock adjustment
        # mid-transaction.
        self._started = time.perf_counter()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(
        self,
        stage: str,
        status: str = "OK",
        detail: dict[str, Any] | None = None,
    ) -> AuditRecord:
        """Append one stage transition and write it to the JSONL sink.

        Args:
            stage: One of ``STAGES``. An unknown stage is accepted and logged
                   as a warning rather than rejected — losing an audit record
                   because a caller invented a stage name is the worse failure.
            status: ``OK``, ``ERROR``, or a caller-defined state such as
                    ``SKIPPED``.
            detail: Stage-specific evidence. Must be JSON-serialisable.

        Returns:
            The record that was appended.
        """
        if stage not in STAGES:
            logger.warning("Unknown audit stage %r recorded for %s", stage, self.correlation_id)

        rec = AuditRecord(
            correlation_id=self.correlation_id,
            customer_id=self.customer_id,
            stage=stage,
            status=status,
            sequence=len(self.records) + 1,
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            elapsed_ms=(time.perf_counter() - self._started) * 1000.0,
            detail=detail or {},
        )
        self.records.append(rec)
        self._append_jsonl(rec)
        return rec

    def flush(self) -> int:
        """Write every collected record to Elasticsearch.

        Returns:
            The number of records successfully indexed. Zero when no client was
            supplied, which is not an error — it is the file-only mode.
        """
        if self._es is None:
            return 0

        today = datetime.now(tz=timezone.utc).strftime("%Y.%m.%d")
        index_name = f"{_AUDIT_INDEX_PREFIX}-{today}"
        written = 0
        for rec in self.records:
            try:
                self._es.index(index=index_name, document=rec.to_document())
                written += 1
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Failed to index audit record %s/%s: %s",
                    self.correlation_id,
                    rec.stage,
                    exc,
                )
        if written:
            try:
                self._es.indices.refresh(index=index_name)
            except Exception as exc:  # noqa: BLE001
                logger.error("Audit index refresh failed: %s", exc)
        return written

    def gaps(self) -> list[str]:
        """Stages that every transaction should have reached but this one did not.

        A non-empty result means the pipeline broke somewhere, and which stage
        is missing localises it. ``PLAYBOOK_FIRED`` is never reported — a
        MONITOR verdict is supposed to skip it.
        """
        reached = {r.stage for r in self.records}
        return [s for s in STAGES if s in _ALWAYS_EXPECTED and s not in reached]

    def render(self, indent: str = "  ") -> str:
        """A human-readable trace of the whole trail.

        Deliberately ASCII-only: a Windows console defaults to cp1252 and turns
        box-drawing characters into replacement glyphs mid-demo.
        """
        lines = [
            f"{indent}correlation_id : {self.correlation_id}",
            f"{indent}customer       : {self.customer_id}",
            f"{indent}stages         : {len(self.records)}",
            "",
            f"{indent}{'#':>2}  {'+ms':>9}  {'stage':<22} {'status':<8} detail",
            f"{indent}{'-' * 86}",
        ]
        for rec in self.records:
            detail = ", ".join(f"{k}={v}" for k, v in rec.detail.items())
            if len(detail) > 120:
                detail = detail[:117] + "..."
            lines.append(
                f"{indent}{rec.sequence:>2}  {rec.elapsed_ms:>9.2f}  "
                f"{rec.stage:<22} {rec.status:<8} {detail}"
            )
        missing = self.gaps()
        if missing:
            lines.append("")
            lines.append(f"{indent}[!] never reached: {', '.join(missing)}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _append_jsonl(self, rec: AuditRecord) -> None:
        """Append one record to the daily JSONL file.

        Failures are logged and swallowed — the audit sink must never be able
        to abort the transaction it is auditing.
        """
        if not self._write_jsonl:
            return
        try:
            self._sink_dir.mkdir(parents=True, exist_ok=True)
            day = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
            path = self._sink_dir / f"meridian-audit-{day}.jsonl"
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec.to_document(), default=str) + "\n")
        except OSError as exc:
            logger.error("Audit JSONL write failed: %s", exc)
