#!/usr/bin/env python3
"""CLI for fetching ARIN role emails for a list of ASNs."""

from __future__ import annotations

import argparse
import sys
import time

from arin_lookup import load_asns, lookup_asn, write_csv


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch ARIN role emails for ASN list")
    parser.add_argument(
        "input", nargs="?", help="ASN list file (one ASN per line). Read stdin if omitted."
    )
    parser.add_argument("-o", "--output", default="arin_asn_roles.csv", help="Output CSV path")
    parser.add_argument(
        "--delay", type=float, default=1.0, help="Delay between requests in seconds"
    )
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout in seconds")
    args = parser.parse_args()

    asns = load_asns(args.input)
    if not asns:
        print("No ASNs found.", file=sys.stderr)
        return 1

    all_rows = []
    for index, asn in enumerate(asns):
        rows = lookup_asn(asn, args.timeout)
        all_rows.extend(rows)
        status = rows[0].error or f"{sum(1 for r in rows if r.email)} email(s)"
        print(f"AS{asn}: {status}", file=sys.stderr)
        if index + 1 < len(asns):
            time.sleep(args.delay)

    write_csv(args.output, all_rows)
    print(f"Wrote {len(all_rows)} row(s) to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
