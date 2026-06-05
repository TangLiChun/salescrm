"""Multi-RIR ASN role email lookup via RDAP (ARIN, RIPE, APNIC, LACNIC, AFRINIC)."""

from __future__ import annotations

import csv
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from io import StringIO
from typing import Iterable

ARIN_BOOTSTRAP = "https://rdap.arin.net/registry/autnum/{asn}"
RIR_RDAP = {
    "whois.arin.net": "https://rdap.arin.net/registry/autnum/{asn}",
    "whois.ripe.net": "https://rdap.db.ripe.net/autnum/{asn}",
    "whois.apnic.net": "https://rdap.apnic.net/autnum/{asn}",
    "whois.lacnic.net": "https://rdap.lacnic.net/rdap/autnum/{asn}",
    "whois.afrinic.net": "https://rdap.afrinic.net/rdap/autnum/{asn}",
}
RIR_LABEL = {
    "whois.arin.net": "ARIN",
    "whois.ripe.net": "RIPE",
    "whois.apnic.net": "APNIC",
    "whois.lacnic.net": "LACNIC",
    "whois.afrinic.net": "AFRINIC",
}
ROLE_PRIORITY = ("abuse", "administrative", "technical", "routing", "noc", "registrant")
MAX_ASN = 4294967295
ASN_PREFIX_RE = re.compile(r"\bAS[N]?\s*[-#]?\s*(\d{1,10})\b", re.IGNORECASE)


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

    def to_dict(self) -> dict:
        return {
            "asn": self.asn,
            "org": self.org or "",
            "roles": self.roles,
            "name": self.name or "",
            "email": self.email or "",
            "handle": self.handle or "",
            "rir": self.rir or "",
            "error": self.error or "",
        }


def parse_asn(value: str) -> int | None:
    value = value.strip()
    if not value or value.startswith("#"):
        return None
    match = re.search(r"\d+", value)
    if not match:
        return None
    asn = int(match.group())
    return asn if 1 <= asn <= MAX_ASN else None


def _add_asn(asn: int, seen: set[int], ordered: list[int]) -> None:
    if 1 <= asn <= MAX_ASN and asn not in seen:
        seen.add(asn)
        ordered.append(asn)


def parse_asns_from_text(text: str) -> list[int]:
    """Extract unique ASNs from free-form text (order preserved).

    Supports AS/ASN prefixes, one-per-line numbers, and delimited lists
    such as ``15169, 7922`` or ``AS15169 7922`` on a single line.
    """
    if not text or not text.strip():
        return []

    seen: set[int] = set()
    ordered: list[int] = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "#" in stripped:
            stripped = stripped.split("#", 1)[0].strip()
        if not stripped:
            continue

        for match in ASN_PREFIX_RE.finditer(stripped):
            _add_asn(int(match.group(1)), seen, ordered)

        parts = [part.strip().strip("'\"") for part in re.split(r"[\s,;|]+", stripped) if part.strip()]
        for part in parts:
            if re.fullmatch(r"\d{1,10}", part):
                _add_asn(int(part), seen, ordered)
                continue
            if len(parts) == 1:
                asn = parse_asn(part)
                if asn is not None:
                    _add_asn(asn, seen, ordered)

    return ordered


def load_asns(path: str | None) -> list[int]:
    if path:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = sys.stdin.read()
    return parse_asns_from_text(text)


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


def fetch_rdap(url: str, timeout: float) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/rdap+json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def rir_label(port43: str | None) -> str:
    if not port43:
        return "RDAP"
    return RIR_LABEL.get(port43, port43)


def asn_in_range(asn: int, data: dict) -> bool:
    start = data.get("startAutnum")
    end = data.get("endAutnum")
    if start is None or end is None:
        return True
    return start <= asn <= end


def parse_rdap_response(data: dict, asn: int, *, port43: str | None = None) -> list[RoleContact]:
    port43 = port43 or data.get("port43")
    rir = rir_label(port43)
    org = data.get("name")

    if not asn_in_range(asn, data):
        start = data.get("startAutnum")
        end = data.get("endAutnum")
        return [
            RoleContact(
                asn=asn,
                org=org,
                rir=rir,
                error=f"returned block AS{start}-AS{end}, AS{asn} not in range",
            )
        ]

    rows: list[RoleContact] = []
    walk_entities(data.get("entities") or [], rows, asn, org)

    if not rows:
        return [RoleContact(asn=asn, org=org, rir=rir, error="no role emails found")]

    for row in rows:
        row.rir = rir
    return dedupe_rows(rows)


def _lookup_asn_try_all_rirs(asn: int, timeout: float) -> list[RoleContact]:
    errors: list[str] = []
    for port43, url in RIR_RDAP.items():
        label = rir_label(port43)
        try:
            data = fetch_rdap(url.format(asn=asn), timeout)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                errors.append(f"{label}: HTTP {exc.code}")
            continue
        except urllib.error.URLError as exc:
            errors.append(f"{label}: {exc.reason}")
            continue

        if not asn_in_range(asn, data):
            continue

        rows = parse_rdap_response(data, asn, port43=port43)
        if any(row.email and not row.error for row in rows):
            return rows
        if rows and rows[0].error:
            errors.append(f"{label}: {rows[0].error}")

    if errors:
        return [RoleContact(asn=asn, org=None, error="; ".join(errors[:3]))]
    return [RoleContact(asn=asn, org=None, error="所有 RIR 均未找到该 ASN")]


def lookup_asn(asn: int, timeout: float = 20.0) -> list[RoleContact]:
    try:
        bootstrap = fetch_rdap(ARIN_BOOTSTRAP.format(asn=asn), timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return _lookup_asn_try_all_rirs(asn, timeout)
        return [RoleContact(asn=asn, org=None, error=f"HTTP {exc.code}")]
    except urllib.error.URLError as exc:
        return [RoleContact(asn=asn, org=None, error=str(exc.reason))]

    port43 = bootstrap.get("port43")
    if not port43:
        return [RoleContact(asn=asn, org=bootstrap.get("name"), error="unknown RIR (missing port43)")]

    rir_url = RIR_RDAP.get(port43)
    if not rir_url:
        return [
            RoleContact(
                asn=asn,
                org=bootstrap.get("name"),
                rir=port43,
                error=f"unsupported RIR (port43={port43})",
            )
        ]

    label = rir_label(port43)

    if port43 == "whois.arin.net" and asn_in_range(asn, bootstrap):
        return parse_rdap_response(bootstrap, asn, port43=port43)

    try:
        data = fetch_rdap(rir_url.format(asn=asn), timeout)
    except urllib.error.HTTPError as exc:
        return [RoleContact(asn=asn, org=bootstrap.get("name"), rir=label, error=f"HTTP {exc.code} from {label}")]
    except urllib.error.URLError as exc:
        return [RoleContact(asn=asn, org=bootstrap.get("name"), rir=label, error=str(exc.reason))]

    return parse_rdap_response(data, asn, port43=port43)


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


def rows_to_csv(rows: list[RoleContact]) -> str:
    buffer = StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=["asn", "org", "roles", "name", "email", "handle", "rir", "error"],
    )
    writer.writeheader()
    for row in rows:
        payload = row.to_dict()
        payload["roles"] = ",".join(row.roles)
        writer.writerow(payload)
    return buffer.getvalue()


def write_csv(path: str, rows: list[RoleContact]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(rows_to_csv(rows))
