# journeymap

Renders an animated 3D journey-map MP4 from Logseq journal
`current-position:: lat, lng` entries. Independent of the
[syndicator](https://github.com/bbaumgartner/syndicator) publish pipeline —
run this whenever you want to refresh the homepage video.

The Hugo site serves the result as `/journey-map.mp4`
(typically committed under `sailingnomads/static/journey-map.mp4`).

## Setup

```bash
git clone git@github.com:bbaumgartner/journeymap.git ~/git/journeymap
cd ~/git/journeymap
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
uv run journeymap generate \
  --journals ~/saillog/journals \
  --output ~/git/sailingnomads/static/journey-map.mp4

# Also dump clustered stops as JSON
uv run journeymap generate \
  --journals ~/saillog/journals \
  -o journey-map.mp4 \
  --json journey.json

uv run journeymap version
```

Journal convention: files named `YYYY_MM_DD.md` containing
`current-position:: <lat>, <lng>` anywhere in the file. Nearby consecutive
stops are clustered; days-at-stop drive hold timing in the animation.

## Tile cache

OSM tiles are cached under `~/.cache/journeymap/tiles/`.

## Development

```bash
uv sync
uv run pytest
```
