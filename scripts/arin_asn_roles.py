#!/usr/bin/env python3
"""Fetch ARIN role emails for a list of ASNs via RDAP."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Iterable

ARIN_RDAP = "https://rdap.arin.net/registry/autnum/{asn}"
ROLE_PRIORITY = ("abuse", "administrative", "technical", "routing", "noc", "registrant")


@dataclass
class RoleContact:
    asn: int
    org: str | None
    roles: list[str] = field(default_factory=list)
    name: str | None = None
    email: str | None = None
    handle: str | None = None
    rir: str | None = None
    error: str | None = None


def parse_asn(value: str) -> int | None:
    value = value.strip()
    if not value or value.startswith("#"):
        return None
    match = re.search(r"\d+", value)
    return int(match.group()) if match else None


def load_asns(path: str | None) -> list[int]:
    if path:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    else:
        lines = sys.stdin.readlines()

    seen: set[int] = set()
    asns: list[int] = []
    for line in lines:
        asn = parse_asn(line)
        if asn is not None and asn not in seen:
            seen.add(asn)
            asns.append(asn)
    return asns


def vcard_fields(vcard_array: list) -> dict[str, str]:
    fields: dict[str, str] = {}
    for row in vcard_array[1]:
        key = row[0]
        value = row[3]
        if isinstance(value, str) and value:
            fields[key] = value
    return fields


def walk_entities(entities: list, rows: list[RoleContact], asn: int, org: str | None) -> None:
    for entity in entities:
        roles = entity.get("roles") or []
        vcard = entity.get("vcardArray")
        email = name = None
        if vcard:
            fields = vcard_fields(vcard)
            email = fields.get("email")
            name = fields.get("fn") or fields.get("org")

        if roles and email:
            rows.append(
                RoleContact(
                    asn=asn,
                    org=org,
                    roles=roles,
                    name=name,
                    email=email.lower(),
                    handle=entity.get("handle"),
                )
            )

        nested = entity.get("entities")
        if nested:
            walk_entities(nested, rows, asn, org)


def fetch_asn(asn: int, timeout: float) -> dict:
    url = ARIN_RDAP.format(asn=asn)
    req = urllib.request.Request(url, headers={"Accept": "application/rdap+json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def lookup_asn(asn: int, timeout: float) -> list[RoleContact]:
    try:
        data = fetch_asn(asn, timeout)
    except urllib.error.HTTPError as exc:
        return [RoleContact(asn=asn, org=None, error=f"HTTP {exc.code}")]
    except urllib.error.URLError as exc:
        return [RoleContact(asn=asn, org=None, error=str(exc.reason))]

    port43 = data.get("port43")
    start = data.get("startAutnum")
    end = data.get("endAutnum")
    org = data.get("name")

    if port43 != "whois.arin.net":
        return [
            RoleContact(
                asn=asn,
                org=org,
                rir=port43,
                error=f"not ARIN-managed (port43={port43})",
            )
        ]

    if start != asn or end != asn:
        return [
            RoleContact(
                asn=asn,
                org=org,
                rir="whois.arin.net",
                error=f"returned block AS{start}-AS{end}, not AS{asn}",
            )
        ]

    rows: list[RoleContact] = []
    walk_entities(data.get("entities") or [], rows, asn, org)

    if not rows:
        return [RoleContact(asn=asn, org=org, rir="ARIN", error="no role emails found")]

    for row in rows:
        row.rir = "ARIN"
    return dedupe_rows(rows)


def dedupe_rows(rows: Iterable[RoleContact]) -> list[RoleContact]:
    seen: set[tuple[int, str, str]] = set()
    unique: list[RoleContact] = []
    for row in rows:
        role_key = ",".join(sorted(row.roles))
        key = (row.asn, role_key, row.email or "")
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)

    def sort_key(row: RoleContact) -> tuple[int, str]:
        primary = row.roles[0] if row.roles else ""
        try:
            priority = ROLE_PRIORITY.index(primary)
        except ValueError:
            priority = len(ROLE_PRIORITY)
        return (priority, row.email or "")

    return sorted(unique, key=sort_key)


def write_csv(path: str, rows: list[RoleContact]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["asn", "org", "roles", "name", "email", "handle", "rir", "error"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "asn": row.asn,
                    "org": row.org or "",
                    "roles": ",".join(row.roles),
                    "name": row.name or "",
                    "email": row.email or "",
                    "handle": row.handle or "",
                    "rir": row.rir or "",
                    "error": row.error or "",
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch ARIN role emails for ASN list")
    parser.add_argument("input", nargs="?", help="ASN list file (one ASN per line). Read stdin if omitted.")
    parser.add_argument("-o", "--output", default="arin_asn_roles.csv", help="Output CSV path")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests in seconds")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout in seconds")
    args = parser.parse_args()

    asns = load_asns(args.input)
    if not asns:
        print("No ASNs found.", file=sys.stderr)
        return 1

    all_rows: list[RoleContact] = []
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
