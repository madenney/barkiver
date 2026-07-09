#!/usr/bin/env python3
"""poolmine CLI — database, download, shots, search and slice phases.

  python3 index.py index init
  python3 index.py source register --type export --ref export/export
  python3 index.py source reconcile            # adopt already-downloaded videos
  python3 index.py source acquire --video      # download the rest
  python3 index.py process --pr shots          # ingest shot annotations
  python3 index.py status
  python3 index.py search --player "Gorst" --type attack --made
  python3 index.py slice  --break-and-run --pad 2 --break-end-seconds 4

(The legacy Node pipeline still lives in index.js — this is the new Python one.)
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from poolmine import workspace
from poolmine.index import DEFAULT_INDEX_PATH, ensure_index, load_index
from poolmine.process import list_processors, run_processor
from poolmine.search import asset_shots, format_hms, frames_to_seconds, search_shots
from poolmine.slice import slice_shots
from poolmine.source import acquire, list_sources, reconcile_library, register_source
from poolmine.status import summarize

INDEX_TOKEN_RE = re.compile(r"^\d+(?:-\d+)?$")


def parse_index_selection(selection: str) -> list:
    cleaned = selection.replace(" ", "")
    if not cleaned:
        return []
    indices: list = []
    for token in cleaned.split(","):
        if not token:
            continue
        if not INDEX_TOKEN_RE.match(token):
            raise ValueError(f"Invalid index token: {token}")
        if "-" in token:
            a, b = token.split("-", 1)
            start, end = int(a), int(b)
            if start <= 0 or end <= 0 or start > end:
                raise ValueError(f"Invalid range: {token}")
            indices.extend(range(start, end + 1))
        else:
            idx = int(token)
            if idx <= 0:
                raise ValueError("Indices must be positive.")
            indices.append(idx)
    seen, unique = set(), []
    for idx in indices:
        if idx not in seen:
            seen.add(idx)
            unique.append(idx)
    return unique


# ---- shared shot-filter args (used by search + slice) ----------------------

def add_filter_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--player", help="Substring match on player name.")
    p.add_argument("--type", dest="types", action="append",
                   help="Shot type (repeatable): break, attack, safe, bank, kick, …")
    made = p.add_mutually_exclusive_group()
    made.add_argument("--made", action="store_true", help="Only shots where a ball was made.")
    made.add_argument("--missed", action="store_true", help="Only shots where nothing was made.")
    p.add_argument("--break-and-run", dest="break_and_run", action="store_true",
                   help="Match whole break-and-run sequences (spans the run).")
    p.add_argument("--long", action="store_true", help="Only shots flagged long.")
    p.add_argument("--complex", action="store_true", help="Only shots flagged complex.")
    p.add_argument("--strong", action="store_true", help="Only shots flagged strong.")
    p.add_argument("--min-pocket-complexity", dest="min_pocket_complexity", type=float,
                   help="Only shots with pocketComplexity >= this.")
    p.add_argument("--limit", type=int, help="Cap the number of matches.")


def filters_from_args(args: argparse.Namespace) -> dict:
    made = True if args.made else (False if args.missed else None)
    return {
        "player": args.player,
        "types": args.types,
        "made": made,
        "break_and_run": args.break_and_run,
        "long": args.long,
        "complex": args.complex,
        "strong": args.strong,
        "min_pocket_complexity": args.min_pocket_complexity,
    }


# ---- handlers --------------------------------------------------------------

def handle_index_init(_: argparse.Namespace, index_path: Path) -> None:
    ensure_index(index_path)
    print(f"Initialized index at {index_path}")


def handle_index_list(_: argparse.Namespace, index_path: Path) -> None:
    index = load_index(index_path)
    assets = index.get("assets", [])
    if not assets:
        print("No assets registered.")
        return
    for i, asset in enumerate(assets, start=1):
        db = asset.get("database", {})
        meta = db.get("metadata", {})
        shots = len(asset_shots(asset))
        print(f"{i:>4} | {meta.get('video_id','?'):<12} | {db.get('media','none'):<5} | "
              f"shots:{shots:<4} | {(meta.get('title') or '')[:60]}")


def handle_source_register(args: argparse.Namespace, index_path: Path) -> None:
    try:
        assets = register_source(args.type, args.ref, index_path, limit=args.limit)
    except (RuntimeError, KeyError) as exc:
        raise SystemExit(str(exc)) from exc
    if not assets:
        print("No new items registered (already known or none found).")
        return
    print(f"Registered {len(assets)} item(s) from {args.type}. "
          f"Next: `process --pr shots`, then `source acquire --video`.")


def handle_source_reconcile(_: argparse.Namespace, index_path: Path) -> None:
    n = reconcile_library(index_path)
    print(f"Adopted {n} already-downloaded video(s) into the index.")


def handle_source_acquire(args: argparse.Namespace, index_path: Path) -> None:
    try:
        results = acquire(index_path, limit=args.limit, force=args.force)
    except (RuntimeError, KeyError) as exc:
        raise SystemExit(str(exc)) from exc
    if not results:
        print("Nothing to acquire — all registered videos already downloaded.")
        return
    ok = sum(1 for r in results if r.get("status") == "complete")
    for r in results:
        if r.get("status") == "error":
            print(f"  {r.get('label')} | error: {r.get('error')}")
    print(f"Downloaded {ok}/{len(results)} video(s).")


def handle_process_run(args: argparse.Namespace, index_path: Path) -> None:
    indices = None
    if args.items:
        try:
            indices = parse_index_selection(args.items)
        except ValueError as exc:
            raise SystemExit(f"Invalid -i/--items value: {exc}") from exc
    try:
        results = run_processor(index_path, args.pr, indices, force=args.force)
    except (ValueError, KeyError) as exc:
        raise SystemExit(str(exc)) from exc
    if not results:
        print("No matching assets to process.")
        return
    done = sum(1 for _, r in results if r.get("status") == "complete")
    skipped = sum(1 for _, r in results if r.get("status") == "skipped")
    ingested = sum(r.get("count", 0) for _, r in results if r.get("status") == "complete")
    tail = f" (skipped {skipped} already done)" if skipped else ""
    print(f"Processed {done} asset(s) with {args.pr}: {ingested} shots ingested{tail}.")


def handle_status(_: argparse.Namespace, index_path: Path) -> None:
    s = summarize(load_index(index_path))
    if s["total"] == 0:
        print("No assets registered.")
        return
    print(f"Assets: {s['total']}")
    print(f"Downloaded (media=video): {s['downloaded']}/{s['total']}  "
          f"| media breakdown: {s['media']}")
    print(f"Shots ingested: {s['shots_ingested']}/{s['total']} assets, "
          f"{s['total_shots']} shots total")
    print(f"Clips cut: {s['clips']} across {s['clip_assets']} asset(s)")
    if s.get("acquiring"):
        a = s["acquiring"]
        print(f"  acquiring: {a.get('done')}/{a.get('total')} {a.get('label','')}")
    if s.get("cutting"):
        c = s["cutting"]
        print(f"  cutting: {c.get('done')}/{c.get('total')} {c.get('label','')}")


def handle_search(args: argparse.Namespace, index_path: Path) -> None:
    index = load_index(index_path)
    results = search_shots(index, limit=args.limit, **filters_from_args(args))
    if not results:
        print("No matching shots.")
        return
    last = None
    for r in results:
        if r.get("label") != last:
            print(f"\n# {r.get('label')}  ({r.get('video_id')})")
            last = r.get("label")
        stamp = format_hms(frames_to_seconds(r.get("begin_frame"), r.get("fps", 30)))
        extra = f" run={r['run_length']}" if r.get("kind") == "break_and_run" else ""
        print(f"  [{stamp}] {r.get('type') or r.get('kind')} | {r.get('player') or '?'}{extra}")
    print(f"\n{len(results)} match(es).")


def handle_slice(args: argparse.Namespace, index_path: Path) -> None:
    results = slice_shots(
        index_path,
        filters_from_args(args),
        pad=args.pad,
        start_seconds=args.start_seconds,
        end_seconds=args.end_seconds,
        break_end_seconds=args.break_end_seconds,
        output_dir=args.output,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
        limit=args.limit,
    )
    if not results:
        print("No matching shots to slice.")
        return
    cut = skipped = needs_video = 0
    for r in results:
        st = r.get("status")
        if st == "needs_video":
            needs_video += 1
            continue
        if st == "exists":
            skipped += 1
            continue
        if st in ("complete", "dry_run"):
            cut += 1
            print(f"  [{r.get('start')}-{r.get('end')}s] {r.get('type')} | "
                  f"{r.get('player') or '?'} -> {r.get('output')}")
        elif st == "error":
            print(f"  error: {r.get('error')}")
    verb = "Would cut" if args.dry_run else "Cut"
    tail = f" (skipped {skipped} on disk)" if skipped else ""
    print(f"{verb} {cut} clip(s){tail}.")
    if needs_video:
        print(f"{needs_video} match(es) have no downloaded video yet — "
              f"run `source acquire --video` first.")


# ---- parser ----------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="index.py",
        description="poolmine CLI for database, download, shots, search and slice.",
        allow_abbrev=False,
    )
    parser.add_argument("--project", metavar="DIR",
                        help="Project workspace (default: cwd or $POOLMINE_HOME).")
    parser.add_argument("--index", default=None,
                        help="Path to database.json (default: <project>/database/database.json).")
    parser.add_argument("-p", "--print", dest="print_index", action="store_true",
                        help="Print stored video paths and a count.")
    parser.add_argument("--version", action="version", version="poolmine 0.1.0")

    sub = parser.add_subparsers(dest="command")

    index_p = sub.add_parser("index", help="Index commands")
    index_sub = index_p.add_subparsers(dest="index_command")
    index_sub.add_parser("init", help="Create database.json if missing").set_defaults(func=handle_index_init)
    index_sub.add_parser("list", help="List registered assets").set_defaults(func=handle_index_list)

    source_p = sub.add_parser("source", help="Register sources and download videos")
    source_sub = source_p.add_subparsers(dest="source_command")
    reg = source_sub.add_parser("register", help="Enumerate a source into assets")
    reg.add_argument("--type", choices=list_sources(), required=True)
    reg.add_argument("--ref", required=True, help="Export dir (export) or channel URL (youtube).")
    reg.add_argument("--limit", type=int)
    reg.set_defaults(func=handle_source_register)
    rec = source_sub.add_parser("reconcile", help="Adopt already-downloaded videos into the index")
    rec.set_defaults(func=handle_source_reconcile)
    acq = source_sub.add_parser("acquire", help="Download the full video for registered assets")
    acq.add_argument("--video", action="store_true", help="(default; kept for parity)")
    acq.add_argument("--limit", type=int, help="Max videos to download this run.")
    acq.add_argument("--force", action="store_true", help="Re-download even if present.")
    acq.set_defaults(func=handle_source_acquire)

    proc = sub.add_parser("process", help="Ingest shot annotations")
    proc.add_argument("--pr", default="shots", choices=list_processors())
    proc.add_argument("-i", "--items", help="1-based asset indices (see -p / index list).")
    proc.add_argument("--force", action="store_true", help="Reprocess assets already complete.")
    proc.set_defaults(func=handle_process_run)

    status_p = sub.add_parser("status", help="Show download / shots / slice progress")
    status_p.set_defaults(func=handle_status)

    search_p = sub.add_parser("search", help="Find shots by criteria")
    add_filter_args(search_p)
    search_p.set_defaults(func=handle_search)

    slice_p = sub.add_parser("slice", help="Cut a clip per matched shot")
    add_filter_args(slice_p)
    slice_p.add_argument("--pad", type=float, default=1.5, help="Seconds of padding each side (default 1.5).")
    slice_p.add_argument("--start-seconds", dest="start_seconds", type=float, default=0.0,
                         help="Extra offset applied to each clip start (default 0).")
    slice_p.add_argument("--end-seconds", dest="end_seconds", type=float, default=0.0,
                         help="Extra tail added after each clip (default 0).")
    slice_p.add_argument("--break-end-seconds", dest="break_end_seconds", type=float, default=0.0,
                         help="Extra tail for break shots, to capture the spread (default 0).")
    slice_p.add_argument("--output", default="output", help="Output directory (default: output).")
    slice_p.add_argument("--dry-run", dest="dry_run", action="store_true",
                         help="List clips that would be cut without rendering.")
    slice_p.add_argument("--overwrite", action="store_true", help="Re-cut clips already on disk.")
    slice_p.set_defaults(func=handle_slice)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    root = workspace.resolve_root(args.project)
    ref = getattr(args, "ref", None)
    if ref and Path(ref).expanduser().exists():
        args.ref = str(Path(ref).expanduser().resolve())
    explicit_index = args.index is not None
    if explicit_index:
        args.index = str(Path(args.index).expanduser().resolve())
    workspace.enter(root)
    index_path = Path(args.index) if explicit_index else DEFAULT_INDEX_PATH

    if args.print_index:
        index = load_index(index_path)
        paths = [a.get("database", {}).get("path") for a in index.get("assets", [])
                 if a.get("database", {}).get("path")]
        for i, p in enumerate(paths, start=1):
            print(f"{i}: {p}")
        print(f"Total downloaded: {len(paths)}")
        return
    if not hasattr(args, "func"):
        parser.print_help()
        return
    args.func(args, index_path)


if __name__ == "__main__":
    main()
