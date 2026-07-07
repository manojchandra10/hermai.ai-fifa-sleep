#!/usr/bin/env python3
"""
Refresh fifa_index.html from Hermai at build time.

Usage:
    python build_data.py fifa_index.html
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


API_URL = "https://api.hermai.ai/v1/fetch"
REQUEST_BODY = {
    "site": "thestatsapi.com",
    "endpoint": "world_cup_fixtures",
}

SLEEP_START_MINUTE = 23 * 60
SLEEP_END_MINUTE = 7 * 60
MATCH_MINUTES = 120
HOURS_PER_YEAR = 8760

TEAM_META = {
    "Algeria": ("Africa/Algiers", "Algiers"),
    "Argentina": ("America/Argentina/Buenos_Aires", "Buenos Aires"),
    "Australia": ("Australia/Sydney", "Sydney"),
    "Austria": ("Europe/Vienna", "Vienna"),
    "Belgium": ("Europe/Brussels", "Brussels"),
    "Bosnia & Herzegovina": ("Europe/Sarajevo", "Sarajevo"),
    "Brazil": ("America/Sao_Paulo", "São Paulo"),
    "Canada": ("America/Toronto", "Toronto"),
    "Cape Verde": ("Atlantic/Cape_Verde", "Praia"),
    "Colombia": ("America/Bogota", "Bogotá"),
    "Croatia": ("Europe/Zagreb", "Zagreb"),
    "Curaçao": ("America/Curacao", "Willemstad"),
    "Czechia": ("Europe/Prague", "Prague"),
    "DR Congo": ("Africa/Kinshasa", "Kinshasa"),
    "Ecuador": ("America/Guayaquil", "Guayaquil"),
    "Egypt": ("Africa/Cairo", "Cairo"),
    "England": ("Europe/London", "London"),
    "France": ("Europe/Paris", "Paris"),
    "Germany": ("Europe/Berlin", "Berlin"),
    "Ghana": ("Africa/Accra", "Accra"),
    "Haiti": ("America/Port-au-Prince", "Port-au-Prince"),
    "Iran": ("Asia/Tehran", "Tehran"),
    "Iraq": ("Asia/Baghdad", "Baghdad"),
    "Ivory Coast": ("Africa/Abidjan", "Abidjan"),
    "Japan": ("Asia/Tokyo", "Tokyo"),
    "Jordan": ("Asia/Amman", "Amman"),
    "Mexico": ("America/Mexico_City", "Mexico City"),
    "Morocco": ("Africa/Casablanca", "Casablanca"),
    "Netherlands": ("Europe/Amsterdam", "Amsterdam"),
    "New Zealand": ("Pacific/Auckland", "Auckland"),
    "Norway": ("Europe/Oslo", "Oslo"),
    "Panama": ("America/Panama", "Panama City"),
    "Paraguay": ("America/Asuncion", "Asunción"),
    "Portugal": ("Europe/Lisbon", "Lisbon"),
    "Qatar": ("Asia/Qatar", "Doha"),
    "Saudi Arabia": ("Asia/Riyadh", "Riyadh"),
    "Scotland": ("Europe/London", "Edinburgh"),
    "Senegal": ("Africa/Dakar", "Dakar"),
    "South Africa": ("Africa/Johannesburg", "Johannesburg"),
    "South Korea": ("Asia/Seoul", "Seoul"),
    "Spain": ("Europe/Madrid", "Madrid"),
    "Sweden": ("Europe/Stockholm", "Stockholm"),
    "Switzerland": ("Europe/Zurich", "Zurich"),
    "Tunisia": ("Africa/Tunis", "Tunis"),
    "Türkiye": ("Europe/Istanbul", "Istanbul"),
    "United States": ("America/New_York", "New York / Eastern Time"),
    "Uruguay": ("America/Montevideo", "Montevideo"),
    "Uzbekistan": ("Asia/Tashkent", "Tashkent"),
}

ALIASES = {
    "USA": "United States",
    "United States of America": "United States",
    "Korea Republic": "South Korea",
    "Korea, South": "South Korea",
    "Cabo Verde": "Cape Verde",
    "Bosnia and Herzegovina": "Bosnia & Herzegovina",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Turkey": "Türkiye",
    "Turkiye": "Türkiye",
    "IR Iran": "Iran",
    "Congo DR": "DR Congo",
}

STAGE_LABELS = {
    "group-stage": "Group stage",
    "round-of-32": "Round of 32",
    "round-of-16": "Round of 16",
    "quarter-final": "Quarter-final",
    "quarter-finals": "Quarter-final",
    "semi-final": "Semi-final",
    "semi-finals": "Semi-final",
    "third-place": "Third place",
    "final": "Final",
}

DATA_PATTERN = re.compile(
    r"/\* HERMAI_DATA_START[\s\S]*?/\* HERMAI_DATA_END \*/"
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def error_report(message: str) -> None:
    print(
        json.dumps(
            {
                "timestamp_utc": utc_now().isoformat(),
                "request_body": REQUEST_BODY,
                "error": message,
            },
            indent=2,
        ),
        file=sys.stderr,
    )


def get_key() -> str:
    key = os.environ.get("HERMAI_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "HERMAI_KEY is not set in this build environment."
        )
    return key


def fetch_fixtures(key: str) -> list[dict[str, Any]]:
    payload = json.dumps(REQUEST_BODY).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body_text = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        message = (
            f"Hermai returned HTTP {exc.code}. "
            f"Response starts: {body_text[:200]}"
        )
        error_report(message)
        raise RuntimeError(message) from exc
    except Exception as exc:
        error_report(str(exc))
        raise

    try:
        result = json.loads(body_text)
    except json.JSONDecodeError as exc:
        message = f"Hermai returned invalid JSON: {body_text[:200]}"
        error_report(message)
        raise RuntimeError(message) from exc

    fixtures = result.get("data", {}).get("fixtures")
    if result.get("success") is not True or not isinstance(fixtures, list):
        message = (
            "Unexpected Hermai response. Expected "
            "{success: true, data: {fixtures: [...]}}."
        )
        error_report(message)
        raise RuntimeError(message)

    if len(fixtures) != 104:
        message = f"Expected 104 fixtures; received {len(fixtures)}."
        error_report(message)
        raise RuntimeError(message)

    match_numbers = []
    for fixture in fixtures:
        try:
            match_numbers.append(int(fixture["matchNumber"]))
        except (KeyError, TypeError, ValueError) as exc:
            message = f"Invalid matchNumber in fixture: {fixture!r}"
            error_report(message)
            raise RuntimeError(message) from exc

    if sorted(match_numbers) != list(range(1, 105)):
        message = "Fixture match numbers are not exactly 1 through 104."
        error_report(message)
        raise RuntimeError(message)

    return fixtures


def canonical_team(value: Any) -> str | None:
    if value is None:
        return None

    name = str(value).strip()
    if name in TEAM_META:
        return name
    return ALIASES.get(name)


def stage_label(value: Any) -> str:
    raw = str(value or "Match").strip()
    key = raw.lower()
    if key in STAGE_LABELS:
        return STAGE_LABELS[key]
    return raw.replace("-", " ").capitalize()


def parse_utc(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("kickoffUtc is missing.")

    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"kickoffUtc has no UTC offset: {text!r}")
    return parsed.astimezone(timezone.utc)


def local_display(value: datetime) -> str:
    text = value.strftime("%Y-%m-%d %H:%M:%S%z")
    return f"{text[:-2]}:{text[-2:]}"


def overlap_hours(start_minute: int) -> float:
    overlap_minutes = 0

    for offset in range(MATCH_MINUTES):
        minute = (start_minute + offset) % 1440
        if (
            minute >= SLEEP_START_MINUTE
            or minute < SLEEP_END_MINUTE
        ):
            overlap_minutes += 1

    return overlap_minutes / 60


def compute_rankings(
    fixtures: list[dict[str, Any]],
    now_utc: datetime,
) -> tuple[list[dict[str, Any]], int, int]:
    per_team: dict[str, list[dict[str, Any]]] = {
        team: [] for team in TEAM_META
    }

    counted_matches = 0
    skipped_unknown_sides = 0

    for fixture in fixtures:
        kickoff = parse_utc(fixture.get("kickoffUtc"))

        # The API schema supplied by the client has no match-status field.
        # To avoid counting a live match, wait until the same 120-minute
        # viewing period used by the model has ended.
        if kickoff + timedelta(minutes=MATCH_MINUTES) > now_utc:
            continue

        counted_matches += 1

        home = canonical_team(fixture.get("homeTeam"))
        away = canonical_team(fixture.get("awayTeam"))

        for team, opponent_raw in (
            (home, fixture.get("awayTeam")),
            (away, fixture.get("homeTeam")),
        ):
            if team is None:
                skipped_unknown_sides += 1
                continue

            zone_name, _ = TEAM_META[team]
            local_kickoff = kickoff.astimezone(ZoneInfo(zone_name))
            start_minute = (
                local_kickoff.hour * 60 + local_kickoff.minute
            )

            per_team[team].append(
                {
                    "opponent": (
                        canonical_team(opponent_raw)
                        or str(opponent_raw or "TBC")
                    ),
                    "stage": stage_label(fixture.get("stage")),
                    "localKickoff": local_display(local_kickoff),
                    "sleepHours": overlap_hours(start_minute),
                    "venue": str(fixture.get("stadium") or ""),
                    "hostCity": str(
                        fixture.get("hostCity") or ""
                    ).replace("-", " ").title(),
                    "_kickoff": kickoff.timestamp(),
                }
            )

    rows: list[dict[str, Any]] = []

    for team, matches in per_team.items():
        matches.sort(key=lambda row: row["_kickoff"])

        total = sum(row["sleepHours"] for row in matches)
        affected = sum(row["sleepHours"] > 0 for row in matches)
        count = len(matches)
        mean = total / count if count else 0
        maximum = max(
            (row["sleepHours"] for row in matches),
            default=0,
        )

        clean_details = [
            {
                key: value
                for key, value in row.items()
                if key != "_kickoff"
            }
            for row in matches
        ]

        _, city = TEAM_META[team]
        rows.append(
            {
                "team": team,
                "city": city,
                "timezone": TEAM_META[team][0],
                "matches": count,
                "affectedMatches": affected,
                "sleepHours": round(total, 2),
                "meanHours": round(mean, 4),
                "maxHours": round(maximum, 2),
                "affectedShare": (
                    round(affected / count, 4) if count else 0
                ),
                "yearsPerMillion": round(
                    total * 1_000_000 / HOURS_PER_YEAR,
                    4,
                ),
                # Preserves the current UI's Pattern column.
                # This is a simple display band, not a K-means result.
                "cluster": (
                    "moderate impact"
                    if total >= 2
                    else "low impact"
                ),
                "details": clean_details,
            }
        )

    rows.sort(
        key=lambda row: (
            -row["sleepHours"],
            -row["affectedShare"],
            -row["meanHours"],
            row["team"],
        )
    )

    for index, row in enumerate(rows, start=1):
        row["rank"] = index

    return rows, counted_matches, skipped_unknown_sides


def inject_data(
    html: str,
    rankings: list[dict[str, Any]],
    snapshot_iso: str,
) -> str:
    block = (
        "/* HERMAI_DATA_START — regenerated by build_data.py; "
        "oops nope dont you dare*/\n"
        f"    const snapshotUtc = {json.dumps(snapshot_iso)};\n"
        "    const rankings = "
        + json.dumps(
            rankings,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + ";\n"
        "    /* HERMAI_DATA_END */"
    )

    if not DATA_PATTERN.search(html):
        raise RuntimeError(
            "The HTML does not contain HERMAI_DATA_START and "
            "HERMAI_DATA_END markers."
        )

    return DATA_PATTERN.sub(block, html, count=1)


def read_populations(html: str) -> dict[str, float]:
    match = re.search(
        r"const POPULATIONS = \{([\s\S]*?)\};",
        html,
    )
    if not match:
        return {}

    return {
        team: float(value)
        for team, value in re.findall(
            r'"([^"]+)":\s*([\d.]+)',
            match.group(1),
        )
    }


def print_summary(
    rankings: list[dict[str, Any]],
    populations: dict[str, float],
    counted_matches: int,
    skipped_unknown_sides: int,
) -> None:
    top_per_fan = rankings[0]

    print(f"Fixtures returned: 104")
    print(f"Matches counted: {counted_matches}")
    print(f"Fanbases written: {len(rankings)}")
    print(
        f"Top per fan: {top_per_fan['team']} "
        f"at {top_per_fan['sleepHours']}h."
    )

    collective = [
        {
            "team": row["team"],
            "hours": (
                row["sleepHours"]
                * populations.get(row["team"], 0)
                * 1_000_000
            ),
        }
        for row in rankings
    ]
    collective.sort(
        key=lambda row: row["hours"],
        reverse=True,
    )

    if collective and collective[0]["hours"] > 0:
        top = collective[0]
        years = round(top["hours"] / HOURS_PER_YEAR)
        print(
            f"Top collective: {top['team']} at "
            f"{top['hours'] / 1_000_000:.1f} million hours "
            f"(about {years:,} years)."
        )

    if skipped_unknown_sides:
        print(
            "Skipped placeholder or unrecognised fixture sides: "
            f"{skipped_unknown_sides}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "page",
        nargs="?",
        default="fifa_index.html",
        type=Path,
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write to a different file instead of updating page in place.",
    )
    parser.add_argument(
        "--fixtures-file",
        type=Path,
        help=(
            "Use a local JSON fixture response for testing instead "
            "of calling Hermai."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    page_path: Path = args.page
    output_path: Path = args.output or page_path

    html = page_path.read_text(encoding="utf-8")

    if args.fixtures_file:
        fixture_payload = json.loads(
            args.fixtures_file.read_text(encoding="utf-8")
        )
        fixtures = (
            fixture_payload.get("data", {}).get("fixtures")
            if isinstance(fixture_payload, dict)
            else fixture_payload
        )
        if not isinstance(fixtures, list):
            raise RuntimeError(
                "The local fixture file does not contain a fixture array."
            )
    else:
        fixtures = fetch_fixtures(get_key())

    now = utc_now()
    rankings, counted, skipped = compute_rankings(fixtures, now)

    updated_html = inject_data(
        html,
        rankings,
        now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )

    # Final security checks on the file that will be published.
    if os.environ.get("HERMAI_KEY", "") in updated_html:
        raise RuntimeError("The API key appeared in the output HTML.")
    if API_URL in updated_html:
        raise RuntimeError(
            "The Hermai API endpoint appeared in the browser HTML."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(updated_html, encoding="utf-8")

    print_summary(
        rankings,
        read_populations(html),
        counted,
        skipped,
    )
    print(f"Updated page: {output_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        if not isinstance(exc, RuntimeError):
            error_report(str(exc))
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
