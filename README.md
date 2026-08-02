# journeymap

Renders an animated 3D journey-map MP4 from Logseq journal `current-position:: lat, lng` entries, or from a hand-authored positions JSON file.

https://github.com/user-attachments/assets/b1d546c8-41ae-4056-9815-e59e68259c43

## Setup

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # if uv is missing
uv sync
```

Requirements:

- Python ≥ 3.12
- `ffmpeg` on `$PATH` (`libx264`)
- OpenGL offscreen support (PyVista / VTK)
- Network access to fetch OSM map tiles at render time (or a warm tile cache)

## Usage

```bash
# From your Logseq journals directory → local MP4
uv run journeymap generate --journals ~/Documents/saillog/journals --output ~/git/sailingnomads/static/journey-map.mp4

# Also dump clustered stops as JSON
uv run journeymap generate --journals ~/saillog/journals -o journey-map.mp4 --json journey.json

# From a positions JSON file (no Logseq required)
uv run journeymap generate --positions journey.json -o journey-map.mp4

uv run journeymap version
```

Journal convention: files named `YYYY_MM_DD.md` containing `current-position:: <lat>, <lng>` anywhere in the file. Nearby consecutive stops are clustered; days-at-stop drive hold timing in the animation.

## Positions JSON

You can skip Logseq and feed clustered stops directly. The file shape is defined by [`schemas/journey.schema.json`](schemas/journey.schema.json).

Example `journey.json`:

```json
{
  "positions": [
    {"date": "2025-09-13", "lat": 45.5127, "lng": 13.5954, "days": 126},
    {"date": "2026-01-17", "lat": 43.5088, "lng": 16.4402, "days": 10},
    {"date": "2026-01-27", "lat": 42.6507, "lng": 18.0944, "days": 5}
  ]
}
```

| Field | Type | Meaning |
|-------|------|---------|
| `positions` | array | Chronological route stops (already clustered) |
| `date` | string | ISO date `YYYY-MM-DD` for the stop |
| `lat` / `lng` | number | Decimal degrees |
| `days` | integer ≥ 1 | Days at the stop; longer stays hold a bit longer in the animation |

This is the same format written by `--json` when generating from journals.

## Tile cache

OSM tiles are cached under `~/.cache/journeymap/tiles/`. The full-globe base
texture is baked from low-zoom OSM tiles and cached as
`~/.cache/journeymap/earth_osm_z3_2048x1024.png` (higher-res tiles still drape
for close-ups).

## Development

```bash
uv sync
uv run pytest
```
