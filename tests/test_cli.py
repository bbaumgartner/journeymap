"""CLI smoke tests for generate sources."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from journeymap.cli import main
from journeymap.positions import JourneyMap, Position


def test_generate_requires_source():
    with pytest.raises(SystemExit) as exc:
        main(["generate", "-o", "out.mp4"])
    assert exc.value.code == 2


def test_generate_positions_and_journals_exclusive(tmp_path: Path):
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "generate",
                "--journals",
                str(tmp_path),
                "--positions",
                str(tmp_path / "journey.json"),
                "-o",
                str(tmp_path / "out.mp4"),
            ]
        )
    assert exc.value.code == 2


def test_generate_from_positions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    positions = tmp_path / "journey.json"
    positions.write_text(
        json.dumps(
            {
                "positions": [
                    {"date": "2025-09-13", "lat": 45.5127, "lng": 13.5954, "days": 3},
                    {"date": "2026-01-17", "lat": 43.5088, "lng": 16.4402, "days": 2},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "journey-map.mp4"

    def fake_render(journey: JourneyMap, out_mp4: Path | str) -> bool:
        assert len(journey.positions) == 2
        assert journey.positions[0] == Position(
            date="2025-09-13", lat=45.5127, lng=13.5954, days=3
        )
        Path(out_mp4).write_bytes(b"fake-mp4")
        return True

    monkeypatch.setattr("journeymap.positions.render_journey_map", fake_render)
    assert main(["generate", "--positions", str(positions), "-o", str(out)]) == 0
    assert out.exists()


def test_generate_positions_rejects_json_flag(tmp_path: Path):
    positions = tmp_path / "journey.json"
    positions.write_text('{"positions": []}\n', encoding="utf-8")
    assert (
        main(
            [
                "generate",
                "--positions",
                str(positions),
                "--json",
                str(tmp_path / "out.json"),
                "-o",
                str(tmp_path / "out.mp4"),
            ]
        )
        == 1
    )


def test_generate_positions_invalid_file(tmp_path: Path):
    positions = tmp_path / "journey.json"
    positions.write_text('{"positions": [{"date": "bad"}]}\n', encoding="utf-8")
    assert main(["generate", "--positions", str(positions), "-o", str(tmp_path / "out.mp4")]) == 1
