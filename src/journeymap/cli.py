"""CLI: extract Logseq positions and render journey-map.mp4."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="journeymap",
        description=(
            "Render an animated journey-map MP4 from Logseq journals or a positions JSON file."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("version", help="Print the journeymap version")

    p_gen = sub.add_parser(
        "generate",
        help="Render journey-map.mp4 from journals or positions JSON",
    )
    source = p_gen.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--journals",
        type=Path,
        help="Path to the Logseq journals/ directory",
    )
    source.add_argument(
        "--positions",
        type=Path,
        help="Path to a journey positions JSON file (see schemas/journey.schema.json)",
    )
    p_gen.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("journey-map.mp4"),
        help="Output MP4 path (default: ./journey-map.mp4)",
    )
    p_gen.add_argument(
        "--json",
        type=Path,
        default=None,
        help="Optional path to also write the clustered positions as JSON (with --journals)",
    )

    args = parser.parse_args(argv)

    if args.command == "version":
        print(f"journeymap {__version__}")
        return 0

    if args.command == "generate":
        from .positions import (
            extract_positions,
            generate_journey_map,
            read_journey_json,
            render_journey_map,
            write_journey_json,
        )

        out = args.output.expanduser()

        if args.positions is not None:
            if args.json is not None:
                print("error: --json is only valid with --journals", file=sys.stderr)
                return 1

            positions_path = args.positions.expanduser().resolve()
            if not positions_path.is_file():
                print(f"error: positions file not found: {positions_path}", file=sys.stderr)
                return 1

            try:
                journey = read_journey_json(positions_path)
            except ValueError as err:
                print(f"error: {err}", file=sys.stderr)
                return 1

            ok = render_journey_map(journey, out)
            if not ok:
                print("error: no positions found or render failed", file=sys.stderr)
                return 1
            print(out.resolve())
            return 0

        journals = args.journals.expanduser().resolve()
        if not journals.is_dir():
            print(f"error: journals directory not found: {journals}", file=sys.stderr)
            return 1

        if args.json is not None:
            journey = extract_positions(journals)
            write_journey_json(journey, args.json.expanduser())
            logging.getLogger(__name__).info(
                "wrote %d positions to %s", len(journey.positions), args.json
            )

        ok = generate_journey_map(journals, out)
        if not ok:
            print("error: no positions found or render failed", file=sys.stderr)
            return 1
        print(out.resolve())
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
