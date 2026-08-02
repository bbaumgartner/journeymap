# journeymap

Renders an animated 3D journey-map MP4 from Logseq journal `current-position:: lat, lng` entries.

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

uv run journeymap version
```

Journal convention: files named `YYYY_MM_DD.md` containing `current-position:: <lat>, <lng>` anywhere in the file. Nearby consecutive stops are clustered; days-at-stop drive hold timing in the animation.

## Tile cache

OSM tiles are cached under `~/.cache/journeymap/tiles/`.

## Development

```bash
uv sync
uv run pytest
```
