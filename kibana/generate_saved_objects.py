"""Generate a presentation-friendly Kibana dashboard as importable saved objects.

Produces ``meridian_overview.ndjson`` — a set of Kibana saved objects (two data
views, six visualisations, one saved search, and one dashboard) written in
plain, non-technical language so the dashboard can be shown to an audience with
no programming or security background.

Run once to regenerate the NDJSON after editing panel definitions::

    python kibana/generate_saved_objects.py

Import the result via Kibana → Stack Management → Saved Objects → Import.

Design notes
------------
* Uses the classic aggregation-based visualisation types (metric / pie /
  histogram / markdown) because their saved-object shape is compact and stable
  across Kibana 8.x. They import and render without a Lens migration step.
* The ``filters`` aggregation is used for the fraud pie so the slices read
  "Legitimate" and "Suspected Fraud" instead of the raw ``0`` / ``1`` values.
* Field names assume Elasticsearch dynamic mapping (text fields gain a
  ``.keyword`` sub-field). If a field name differs in your cluster, adjust the
  ``FIELD_*`` constants below and re-run.
"""

from __future__ import annotations

import json
from pathlib import Path

# Kibana version the saved objects target. Import is tolerant of minor drift.
KIBANA_VERSION = "8.11.0"

# --- Data view (index pattern) identifiers -----------------------------------
DV_TRANSACTIONS = "meridian-transactions-view"
DV_INCIDENTS = "meridian-incidents-view"

# --- Field names (adjust here if your mapping differs) -----------------------
FIELD_CHANNEL = "transaction.type.keyword"   # PAYMENT / TRANSFER / CASH_OUT ...
FIELD_IS_FRAUD = "labels.is_fraud"           # integer 0 (legit) / 1 (fraud)
FIELD_SEVERITY = "severity.keyword"          # CRITICAL / HIGH


def _search_source(index_ref: str, query: str = "") -> str:
    """Build the searchSourceJSON string that links a saved object to a data view."""
    return json.dumps(
        {
            "query": {"query": query, "language": "kuery"},
            "filter": [],
            "indexRefName": index_ref,
        }
    )


def _index_ref(dv_id: str) -> list[dict]:
    """The reference block linking a visualisation's search source to a data view."""
    return [
        {
            "name": "kibanaSavedObjectMeta.searchSourceJSON.index",
            "type": "index-pattern",
            "id": dv_id,
        }
    ]


def data_view(dv_id: str, title: str, time_field: str | None) -> dict:
    """A Kibana data view (index pattern) saved object."""
    attrs: dict = {"title": title}
    if time_field:
        attrs["timeFieldName"] = time_field
    return {
        "id": dv_id,
        "type": "index-pattern",
        "attributes": attrs,
        "references": [],
        "coreMigrationVersion": KIBANA_VERSION,
    }


def metric_viz(viz_id: str, title: str, subtitle: str, dv_id: str, query: str = "") -> dict:
    """A single big-number 'metric' visualisation."""
    vis_state = {
        "title": title,
        "type": "metric",
        "aggs": [
            {"id": "1", "enabled": True, "type": "count", "schema": "metric", "params": {}}
        ],
        "params": {
            "addTooltip": True,
            "addLegend": False,
            "type": "metric",
            "metric": {
                "percentageMode": False,
                "useRanges": False,
                "colorSchema": "Green to Red",
                "metricColorMode": "None",
                "colorsRange": [{"from": 0, "to": 100000000}],
                "labels": {"show": True},
                "invertColors": False,
                "style": {
                    "bgFill": "#000",
                    "bgColor": False,
                    "labelColor": False,
                    "subText": subtitle,
                    "fontSize": 48,
                },
            },
        },
    }
    return {
        "id": viz_id,
        "type": "visualization",
        "attributes": {
            "title": title,
            "visState": json.dumps(vis_state),
            "uiStateJSON": "{}",
            "description": subtitle,
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": _search_source(
                    "kibanaSavedObjectMeta.searchSourceJSON.index", query
                )
            },
        },
        "references": _index_ref(dv_id),
        "coreMigrationVersion": KIBANA_VERSION,
    }


def filters_pie(viz_id: str, title: str, dv_id: str, filters: list[tuple[str, str]]) -> dict:
    """A donut pie split by labelled filters (readable slice names)."""
    vis_state = {
        "title": title,
        "type": "pie",
        "aggs": [
            {"id": "1", "enabled": True, "type": "count", "schema": "metric", "params": {}},
            {
                "id": "2",
                "enabled": True,
                "type": "filters",
                "schema": "segment",
                "params": {
                    "filters": [
                        {"input": {"query": q, "language": "kuery"}, "label": label}
                        for label, q in filters
                    ]
                },
            },
        ],
        "params": {
            "type": "pie",
            "addTooltip": True,
            "addLegend": True,
            "legendPosition": "right",
            "isDonut": True,
            "labels": {"show": True, "values": True, "last_level": True, "truncate": 100},
        },
    }
    return _viz_object(viz_id, title, vis_state, dv_id)


def terms_pie(viz_id: str, title: str, dv_id: str, field: str, size: int = 5) -> dict:
    """A donut pie split by the top values of a field."""
    vis_state = {
        "title": title,
        "type": "pie",
        "aggs": [
            {"id": "1", "enabled": True, "type": "count", "schema": "metric", "params": {}},
            {
                "id": "2",
                "enabled": True,
                "type": "terms",
                "schema": "segment",
                "params": {
                    "field": field,
                    "orderBy": "1",
                    "order": "desc",
                    "size": size,
                    "otherBucket": False,
                    "missingBucket": False,
                },
            },
        ],
        "params": {
            "type": "pie",
            "addTooltip": True,
            "addLegend": True,
            "legendPosition": "right",
            "isDonut": True,
            "labels": {"show": True, "values": True, "last_level": True, "truncate": 100},
        },
    }
    return _viz_object(viz_id, title, vis_state, dv_id)


def terms_bar(viz_id: str, title: str, dv_id: str, field: str, size: int = 6) -> dict:
    """A vertical bar chart of the top values of a field."""
    vis_state = {
        "title": title,
        "type": "histogram",
        "aggs": [
            {"id": "1", "enabled": True, "type": "count", "schema": "metric", "params": {}},
            {
                "id": "2",
                "enabled": True,
                "type": "terms",
                "schema": "segment",
                "params": {
                    "field": field,
                    "orderBy": "1",
                    "order": "desc",
                    "size": size,
                    "otherBucket": False,
                    "missingBucket": False,
                },
            },
        ],
        "params": {
            "type": "histogram",
            "grid": {"categoryLines": False},
            "categoryAxes": [
                {
                    "id": "CategoryAxis-1",
                    "type": "category",
                    "position": "bottom",
                    "show": True,
                    "scale": {"type": "linear"},
                    "labels": {"show": True, "truncate": 100},
                    "title": {},
                }
            ],
            "valueAxes": [
                {
                    "id": "ValueAxis-1",
                    "name": "LeftAxis-1",
                    "type": "value",
                    "position": "left",
                    "show": True,
                    "scale": {"type": "linear", "mode": "normal"},
                    "labels": {"show": True, "rotate": 0, "filter": False, "truncate": 100},
                    "title": {"text": "Number of transactions"},
                }
            ],
            "seriesParams": [
                {
                    "show": True,
                    "type": "histogram",
                    "mode": "stacked",
                    "data": {"label": "Count", "id": "1"},
                    "valueAxis": "ValueAxis-1",
                    "drawLinesBetweenPoints": True,
                    "showCircles": True,
                }
            ],
            "addTooltip": True,
            "addLegend": False,
            "legendPosition": "right",
            "times": [],
            "addTimeMarker": False,
            "labels": {"show": True},
        },
    }
    return _viz_object(viz_id, title, vis_state, dv_id)


def markdown_viz(viz_id: str, title: str, markdown: str) -> dict:
    """A free-text markdown panel — used for the plain-language explainer."""
    vis_state = {
        "title": title,
        "type": "markdown",
        "aggs": [],
        "params": {"fontSize": 12, "openLinksInNewTab": True, "markdown": markdown},
    }
    return {
        "id": viz_id,
        "type": "visualization",
        "attributes": {
            "title": title,
            "visState": json.dumps(vis_state),
            "uiStateJSON": "{}",
            "description": "",
            "kibanaSavedObjectMeta": {"searchSourceJSON": json.dumps({"query": {"query": "", "language": "kuery"}, "filter": []})},
        },
        "references": [],
        "coreMigrationVersion": KIBANA_VERSION,
    }


def _viz_object(viz_id: str, title: str, vis_state: dict, dv_id: str) -> dict:
    return {
        "id": viz_id,
        "type": "visualization",
        "attributes": {
            "title": title,
            "visState": json.dumps(vis_state),
            "uiStateJSON": "{}",
            "description": "",
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": _search_source(
                    "kibanaSavedObjectMeta.searchSourceJSON.index"
                )
            },
        },
        "references": _index_ref(dv_id),
        "coreMigrationVersion": KIBANA_VERSION,
    }


def incidents_table(search_id: str, title: str, dv_id: str) -> dict:
    """A saved search (Discover table) listing recent incidents in plain columns."""
    return {
        "id": search_id,
        "type": "search",
        "attributes": {
            "title": title,
            "description": "",
            "columns": [
                "customer_id",
                "severity",
                "threat_score",
                "trigger_reason",
                "action",
                "status",
            ],
            "sort": [["timestamp", "desc"]],
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": _search_source(
                    "kibanaSavedObjectMeta.searchSourceJSON.index"
                )
            },
        },
        "references": _index_ref(dv_id),
        "coreMigrationVersion": KIBANA_VERSION,
    }


def dashboard(dash_id: str, title: str, description: str, panels: list[dict]) -> dict:
    """Assemble the dashboard saved object from a list of panel descriptors.

    Each descriptor is a dict: {ref_id, type, x, y, w, h, title}.
    """
    panels_json = []
    references = []
    for i, p in enumerate(panels, start=1):
        panel_ref = f"panel_{i}"
        panels_json.append(
            {
                "version": KIBANA_VERSION,
                "type": p["type"],
                "gridData": {"x": p["x"], "y": p["y"], "w": p["w"], "h": p["h"], "i": str(i)},
                "panelIndex": str(i),
                "embeddableConfig": {"enhancements": {}},
                "panelRefName": panel_ref,
                **({"title": p["title"]} if p.get("title") else {}),
            }
        )
        references.append({"name": panel_ref, "type": p["type"], "id": p["ref_id"]})

    return {
        "id": dash_id,
        "type": "dashboard",
        "attributes": {
            "title": title,
            "description": description,
            "hits": 0,
            "panelsJSON": json.dumps(panels_json),
            "optionsJSON": json.dumps({"useMargins": True, "syncColors": False, "hidePanelTitles": False}),
            "version": 1,
            "timeRestore": True,
            "timeTo": "now",
            "timeFrom": "now-30d",
            "refreshInterval": {"pause": True, "value": 0},
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": json.dumps({"query": {"query": "", "language": "kuery"}, "filter": []})
            },
        },
        "references": references,
        "coreMigrationVersion": KIBANA_VERSION,
    }


INTRO_MARKDOWN = (
    "## Meridian Sentinel — Fraud Detection Overview\n\n"
    "This board shows, in plain language, how the system is protecting customer "
    "accounts right now.\n\n"
    "- **Total Transactions Processed** — every payment the system checked.\n"
    "- **Suspected Fraud Detected** — payments the system flagged as unusual.\n"
    "- **Security Incidents Raised** — flagged cases sent to a human analyst to review.\n\n"
    "In the charts below, **green means safe** and **red means flagged for review**. "
    "Use the date picker at the top right to change the time period."
)


def build() -> list[dict]:
    objects: list[dict] = []

    # Data views
    objects.append(data_view(DV_TRANSACTIONS, "meridian-transactions-*", "@timestamp"))
    objects.append(data_view(DV_INCIDENTS, "meridian-incidents-*", "timestamp"))

    # Explainer
    objects.append(markdown_viz("viz-intro", "About this dashboard", INTRO_MARKDOWN))

    # Big-number metrics
    objects.append(
        metric_viz("viz-total-transactions", "Total Transactions Processed",
                   "payments checked", DV_TRANSACTIONS)
    )
    objects.append(
        metric_viz("viz-fraud-detected", "Suspected Fraud Detected",
                   "flagged as unusual", DV_TRANSACTIONS, query=f"{FIELD_IS_FRAUD}:1")
    )
    objects.append(
        metric_viz("viz-incidents-open", "Security Incidents Raised",
                   "sent to an analyst", DV_INCIDENTS)
    )

    # Charts
    objects.append(
        filters_pie(
            "viz-fraud-pie", "Legitimate vs Suspected Fraud", DV_TRANSACTIONS,
            filters=[("Legitimate", f"{FIELD_IS_FRAUD}:0"),
                     ("Suspected Fraud", f"{FIELD_IS_FRAUD}:1")],
        )
    )
    objects.append(
        terms_bar("viz-channel-bar", "Transactions by Payment Channel",
                  DV_TRANSACTIONS, FIELD_CHANNEL)
    )
    objects.append(
        terms_pie("viz-severity-pie", "Incidents by Urgency Level",
                  DV_INCIDENTS, FIELD_SEVERITY)
    )

    # Incident table
    objects.append(
        incidents_table("search-recent-incidents", "Latest Security Incidents", DV_INCIDENTS)
    )

    # Dashboard layout (48-column grid)
    panels = [
        {"ref_id": "viz-intro", "type": "visualization", "x": 0, "y": 0, "w": 48, "h": 7, "title": ""},
        {"ref_id": "viz-total-transactions", "type": "visualization", "x": 0, "y": 7, "w": 16, "h": 8, "title": "Total Transactions Processed"},
        {"ref_id": "viz-fraud-detected", "type": "visualization", "x": 16, "y": 7, "w": 16, "h": 8, "title": "Suspected Fraud Detected"},
        {"ref_id": "viz-incidents-open", "type": "visualization", "x": 32, "y": 7, "w": 16, "h": 8, "title": "Security Incidents Raised"},
        {"ref_id": "viz-fraud-pie", "type": "visualization", "x": 0, "y": 15, "w": 24, "h": 15, "title": "Legitimate vs Suspected Fraud"},
        {"ref_id": "viz-channel-bar", "type": "visualization", "x": 24, "y": 15, "w": 24, "h": 15, "title": "Transactions by Payment Channel"},
        {"ref_id": "viz-severity-pie", "type": "visualization", "x": 0, "y": 30, "w": 24, "h": 15, "title": "Incidents by Urgency Level"},
        {"ref_id": "search-recent-incidents", "type": "search", "x": 24, "y": 30, "w": 24, "h": 15, "title": "Latest Security Incidents"},
    ]
    objects.append(
        dashboard(
            "meridian-overview-dashboard",
            "Meridian Sentinel — Fraud Detection Overview",
            "Plain-language overview of transaction monitoring and fraud detection "
            "for non-technical viewers.",
            panels,
        )
    )
    return objects


def main() -> None:
    objects = build()
    out_path = Path(__file__).parent / "meridian_overview.ndjson"
    with out_path.open("w", encoding="utf-8", newline="\n") as fh:
        for obj in objects:
            fh.write(json.dumps(obj))
            fh.write("\n")
        # Kibana's export appends a summary line; import ignores objects without a type.
        fh.write(json.dumps({"exportedCount": len(objects), "missingRefCount": 0, "missingReferences": []}))
        fh.write("\n")
    print(f"Wrote {len(objects)} saved objects to {out_path}")


if __name__ == "__main__":
    main()
