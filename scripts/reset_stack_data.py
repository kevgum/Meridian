"""Delete every Meridian index so the dashboard starts from zero.

Used before a deployment or a demo when the console should open empty and
build up from live traffic only, rather than showing accumulated history from
earlier runs.

This deletes data. It refuses to run without ``--yes`` so it cannot be
triggered by a stray shell-history recall.

Usage::

    # see what would go, delete nothing
    docker compose --profile dev run --rm -e ELASTIC_HOST=http://elasticsearch:9200 \
        dev python -m scripts.reset_stack_data

    # actually delete
    ... dev python -m scripts.reset_stack_data --yes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.generate_transaction_batch import _build_es  # noqa: E402

# Every index family this system writes. Kibana's own saved objects live in
# .kibana* and are deliberately NOT touched — wiping those would destroy the
# data views, and they would have to be recreated by hand before Discover
# worked again.
INDEX_PATTERNS: list[str] = [
    "meridian-transactions-*",
    "meridian-incidents-*",
    "meridian-notifications-*",
    "meridian-audit-*",
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Delete all Meridian indices so the dashboard starts empty."
    )
    parser.add_argument("--yes", action="store_true",
                        help="actually delete (without this, only reports)")
    args = parser.parse_args()

    es = _build_es()
    if not es.ping():
        print("[!] Elasticsearch not reachable.")
        return 1

    total_docs = 0
    found: list[tuple[str, int]] = []

    for pattern in INDEX_PATTERNS:
        try:
            stats = es.indices.stats(index=pattern)
        except Exception:
            continue  # pattern matches nothing
        for name, body in stats.get("indices", {}).items():
            docs = body["primaries"]["docs"]["count"]
            found.append((name, docs))
            total_docs += docs

    if not found:
        print("Nothing to delete — the cluster has no Meridian indices.")
        return 0

    print(f"\n{len(found)} index/indices, {total_docs:,} documents:\n")
    for name, docs in sorted(found):
        print(f"  {name:<40} {docs:>8,} docs")

    if not args.yes:
        print("\nDry run — nothing deleted. Re-run with --yes to delete.\n")
        return 0

    print()
    for pattern in INDEX_PATTERNS:
        try:
            es.indices.delete(index=pattern, ignore_unavailable=True)
            print(f"  deleted {pattern}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [!] {pattern}: {exc}")

    print(f"\nDone. {total_docs:,} documents removed; the dashboard will "
          "start from zero.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
