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
            "Extract current-position:: entries from Logseq journals and render "
            "an animated journey-map MP4."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("version", help="Print the journeymap version")

    p_gen = sub.add_parser(
        "generate",
        help="Scan journals and write journey-map.mp4",
    )
    p_gen.add_argument(
        "--journals",
        type=Path,
        required=True,
        help="Path to the Logseq journals/ directory",
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
        help="Optional path to also write the clustered positions as JSON",
    )

    args = parser.parse_args(argv)

    if args.command == "version":
        print(f"journeymap {__version__}")
        return 0

    if args.command == "generate":
        from .positions import extract_positions, generate_journey_map, write_journey_json

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

        ok = generate_journey_map(journals, args.output.expanduser())
        if not ok:
            print("error: no positions found or render failed", file=sys.stderr)
            return 1
        print(args.output.expanduser().resolve())
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
