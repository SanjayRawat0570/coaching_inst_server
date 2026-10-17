"""Import NTA cutoff data (marks / percentile -> rank) from a CSV into nta_cutoffs.

The rank predictor reads this table; it is reference data, not RAG content.

CSV columns (header row required; see scripts/nta_cutoffs_template.csv):
    exam        required  e.g. "JEE Main", "JEE Advanced", "NEET"
    year        required  e.g. 2025
    rank        required  AIR at that score
    marks       marks scored            (marks and/or percentile required)
    percentile  NTA percentile
    max_marks   paper total, e.g. 300   (lets the predictor scale a test %)
    category    default "GEN"
    source      where the numbers come from (URL / document)

Re-importing is safe: by default every (exam, year, category) group in the file
replaces the rows already stored for that group.

Usage (from backend/):
    python -m scripts.import_nta_cutoffs data/nta_cutoffs/jee_main_2025.csv --dry-run
    python -m scripts.import_nta_cutoffs data/nta_cutoffs/jee_main_2025.csv
"""

import argparse
import csv
import sys
from collections import defaultdict

BATCH = 500


def _num(value, kind, line, field):
    value = (value or "").strip().replace(",", "")
    if not value:
        return None
    try:
        return kind(float(value)) if kind is int else float(value)
    except ValueError:
        raise ValueError(f"line {line}: {field} must be a number, got {value!r}")


def parse(path: str) -> list[dict]:
    """Read + validate the CSV. Raises ValueError listing every bad line."""
    rows, errors = [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = {h.strip().lower() for h in reader.fieldnames or []}
        missing = {"exam", "year", "rank"} - header
        if missing:
            raise ValueError(f"missing column(s): {', '.join(sorted(missing))}")
        for line, raw in enumerate(reader, start=2):
            r = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
            if not any(r.values()):
                continue
            try:
                row = {
                    "exam": r.get("exam") or None,
                    "year": _num(r.get("year"), int, line, "year"),
                    "category": r.get("category") or "GEN",
                    "marks": _num(r.get("marks"), float, line, "marks"),
                    "max_marks": _num(r.get("max_marks"), float, line, "max_marks"),
                    "percentile": _num(r.get("percentile"), float, line, "percentile"),
                    "rank": _num(r.get("rank"), int, line, "rank"),
                    "source": r.get("source") or None,
                }
                if not row["exam"] or row["year"] is None or row["rank"] is None:
                    raise ValueError(f"line {line}: exam, year and rank are required")
                if row["marks"] is None and row["percentile"] is None:
                    raise ValueError(f"line {line}: give marks and/or percentile")
                if row["percentile"] is not None and not 0 <= row["percentile"] <= 100:
                    raise ValueError(f"line {line}: percentile must be 0-100")
                rows.append(row)
            except ValueError as e:
                errors.append(str(e))
    if errors:
        raise ValueError("\n".join(errors))
    return rows


def groups(rows: list[dict]) -> dict[tuple, list[dict]]:
    out = defaultdict(list)
    for r in rows:
        out[(r["exam"], r["year"], r["category"])].append(r)
    return dict(out)


def import_rows(sb, rows: list[dict], replace: bool = True) -> int:
    for (exam, year, category), group in groups(rows).items():
        if replace:
            (sb.table("nta_cutoffs").delete().eq("exam", exam).eq("year", year)
             .eq("category", category).execute())
        for i in range(0, len(group), BATCH):
            sb.table("nta_cutoffs").insert(group[i:i + BATCH]).execute()
    return len(rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Import NTA cutoffs from CSV")
    parser.add_argument("csv")
    parser.add_argument("--dry-run", action="store_true", help="validate and show the plan only")
    parser.add_argument("--append", action="store_true",
                        help="add rows instead of replacing each (exam, year, category) group")
    args = parser.parse_args(argv)

    try:
        rows = parse(args.csv)
    except (OSError, ValueError) as e:
        print(f"[nta_cutoffs] {args.csv}: {e}", file=sys.stderr)
        return 1

    plan = groups(rows)
    mode = "append to" if args.append else "replace"
    for (exam, year, category), group in sorted(plan.items()):
        print(f"  {mode} {exam} {year} {category}: {len(group)} rows")
    if args.dry_run:
        print(f"[nta_cutoffs] dry run: {len(rows)} valid rows, nothing written")
        return 0

    from dotenv import load_dotenv
    load_dotenv()
    from auth.supabase_auth import get_supabase
    count = import_rows(get_supabase(), rows, replace=not args.append)
    print(f"[nta_cutoffs] imported {count} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
