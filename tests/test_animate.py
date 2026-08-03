"""Tests for 3D journey globe animation (PyVista + OSM tiles)."""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import pytest
from PIL import Image

from journeymap.animate import (
    CAM_DIST_CLOSE_MAX,
    CAM_DIST_CLOSE_MIN,
    CAM_DIST_WIDE,
    DETAIL_DIST_MAX,
    IMG_HEIGHT,
    IMG_WIDTH,
    INTRO_HOLD,
    MARKER_SIZE_MAX,
    MAX_HOLD_FRAMES,
    MIN_HOLD_FRAMES,
    OUTRO_HOLD,
    PATH_REF_DISTANCE,
    TILE_ZOOM_MIN,
    ZOOM_IN_FRAMES,
    ZOOM_OUT_FRAMES,
    angular_distance_deg,
    build_frame_states,
    close_camera_distance,
    close_camera_distance_for_span,
    generate_animation,
    great_circle_arch_xyz,
    great_circle_points,
    hold_frames_for_days,
    journey_center,
    latlng_to_tile,
    ll_to_xyz,
    load_earth_texture,
    load_logo,
    marker_size,
    mercator_y_norm_to_lat,
    lat_to_mercator_y_norm,
    osm_zoom_for_distance,
    overview_camera_distance,
    path_arch_peak,
    PATH_ARCH_MAX,
    PATH_RADIUS_R,
    path_tube_radius,
    path_width_px,
    route_marker_size,
    scale_image,
    slerp,
    solid_tile_fetcher,
    tile_bounds,
    tiles_for_journey,
    total_frames,
    view_half_angle_deg,
    visible_tiles,
    xyz_to_ll,
    _linear_interp,
)
from journeymap.positions import JourneyMap, Position, write_journey_json


# ---- sphere math ------------------------------------------------------------


def test_ll_to_xyz_equator():
    v = ll_to_xyz(0.0, 0.0)
    assert abs(np_norm(v) - 1.0) < 1e-9
    assert abs(v[0] - 1.0) < 1e-9


def np_norm(v):
    return math.sqrt(float(v[0] ** 2 + v[1] ** 2 + v[2] ** 2))


def test_ll_xyz_roundtrip():
    for lat, lng in ((0.0, 0.0), (45.0, 13.0), (-30.0, 120.0), (80.0, -170.0)):
        got_lat, got_lng = xyz_to_ll(ll_to_xyz(lat, lng))
        assert abs(got_lat - lat) < 1e-6
        assert abs(((got_lng - lng + 180) % 360) - 180) < 1e-6


def test_slerp_endpoints():
    import numpy as np

    a = ll_to_xyz(0.0, 0.0)
    b = ll_to_xyz(0.0, 90.0)
    assert np.allclose(slerp(a, b, 0.0), a, atol=1e-9)
    assert np.allclose(slerp(a, b, 1.0), b, atol=1e-9)


def test_slerp_midpoint_unit():
    import numpy as np

    a = ll_to_xyz(0.0, 0.0)
    b = ll_to_xyz(0.0, 90.0)
    mid = slerp(a, b, 0.5)
    assert abs(np.linalg.norm(mid) - 1.0) < 1e-9
    lat, lng = xyz_to_ll(mid)
    assert abs(lat) < 1e-6
    assert abs(lng - 45.0) < 1e-4


def test_great_circle_midpoint_roughly_halfway():
    pts = great_circle_points(0.0, 0.0, 0.0, 90.0, 5)
    assert len(pts) == 5
    assert abs(pts[0][0]) < 1e-6 and abs(pts[0][1]) < 1e-6
    assert abs(pts[-1][1] - 90.0) < 1e-4
    assert abs(pts[2][1] - 45.0) < 1.0


def test_path_arch_peak_scales_and_caps():
    assert path_arch_peak(0.0) == 0.0
    assert path_arch_peak(0.05) < path_arch_peak(2.0)
    assert path_arch_peak(40.0) > path_arch_peak(5.0)
    assert path_arch_peak(1e6) == PATH_ARCH_MAX
    # Tiny hops must not get the fixed base lift (that made scribble loops).
    assert path_arch_peak(0.05) < 0.001


def test_great_circle_arch_lifts_midpoint():
    import numpy as np

    pts = great_circle_arch_xyz(45.0, 13.0, 43.5, 16.4, 17)
    assert len(pts) == 17
    r0 = float(np.linalg.norm(pts[0]))
    r_mid = float(np.linalg.norm(pts[8]))
    r1 = float(np.linalg.norm(pts[-1]))
    assert abs(r0 - PATH_RADIUS_R) < 1e-9
    assert abs(r1 - PATH_RADIUS_R) < 1e-9
    assert r_mid > r0 + 0.003


def test_angular_distance_quarter():
    assert abs(angular_distance_deg(0.0, 0.0, 0.0, 90.0) - 90.0) < 1e-6


# ---- tiles ------------------------------------------------------------------


def test_latlng_to_tile_known():
    # Equator / prime meridian area at z=1 → tile near (1, 1) or (0, 0) depending on scheme.
    x, y = latlng_to_tile(0.0, 0.0, 1)
    assert x in (0, 1)
    assert y in (0, 1)


def test_tile_bounds_ordering():
    lat_n, lng_w, lat_s, lng_e = tile_bounds(3, 4, 2)
    assert lat_n > lat_s
    assert lng_e > lng_w


def test_mercator_y_roundtrip():
    for lat in (-60.0, -20.0, 0.0, 20.0, 45.0, 60.0):
        y = lat_to_mercator_y_norm(lat)
        assert abs(mercator_y_norm_to_lat(y) - lat) < 1e-6


def test_mercator_mosaic_mid_not_linear_lat():
    # Over a multi-tile mid-latitude span, image-row midpoint ≠ geographic midpoint.
    # Linear lat draping would put logo markers tens of km north of OSM features.
    z, y0, y1 = 6, 20, 28
    n = 2**z
    lat_n, _, _, _ = tile_bounds(z, 0, y0)
    _, _, lat_s, _ = tile_bounds(z, 0, y1)
    y_mid = (y0 + y1 + 1) / 2 / n
    merc_mid = mercator_y_norm_to_lat(y_mid)
    linear_mid = (lat_n + lat_s) / 2
    assert abs(merc_mid - linear_mid) > 0.5  # > ~50 km


def test_region_patch_uses_mercator_rows():
    from journeymap.animate import _region_patch_mesh
    from PIL import Image

    img = Image.new("RGB", (256, 256), (128, 128, 128))
    z, x0, x1, y0, y1 = 8, 136, 136, 90, 90
    mesh, _tex = _region_patch_mesh(img, z, x0, x1, y0, y1, subdivisions=2)
    # Middle row of vertices (iv=1 of 0..2) should sit at mercator mid-lat.
    n = 2**z
    expect_lat = mercator_y_norm_to_lat((y0 + 0.5) / n)
    # 3x3 grid, row iv=1 starts at index 3
    mid = mesh.points[3 + 1]  # center of middle row
    from journeymap.animate import xyz_to_ll

    got_lat, _ = xyz_to_ll(mid)
    assert abs(got_lat - expect_lat) < 0.02


def test_visible_tiles_empty_when_far():
    assert visible_tiles(45.0, 13.0, CAM_DIST_WIDE) == []
    assert visible_tiles(45.0, 13.0, DETAIL_DIST_MAX) == []


def test_visible_tiles_near_are_capped():
    tiles = visible_tiles(44.5, 15.0, CAM_DIST_CLOSE_MIN)
    assert tiles
    assert len(tiles) <= 96
    zs = {t[0] for t in tiles}
    assert len(zs) == 1
    assert TILE_ZOOM_MIN <= next(iter(zs)) <= 13


def test_tiles_for_journey_stable_and_covers_stops():
    positions = [
        Position(date="a", lat=45.5127, lng=13.5954, days=1),
        Position(date="b", lat=43.5088, lng=16.4402, days=1),
    ]
    a = tiles_for_journey(positions)
    b = tiles_for_journey(positions)
    assert a == b
    assert a
    assert len(a) <= 96
    # Single zoom level for the whole journey mosaic.
    assert len({t[0] for t in a}) == 1


def test_camera_focus_continuous_across_legs():
    positions = [
        Position(date="a", lat=45.0, lng=13.0, days=1),
        Position(date="b", lat=44.0, lng=14.0, days=1),
        Position(date="c", lat=43.0, lng=15.0, days=1),
    ]
    states = build_frame_states(positions)
    travel = [s for s in states if s.use_detail and s.traveler is not None]
    assert len(travel) >= 4
    # Consecutive traveler positions should move a small angular step (no teleport).
    for prev, cur in zip(travel, travel[1:]):
        step = angular_distance_deg(
            prev.traveler[0], prev.traveler[1], cur.traveler[0], cur.traveler[1]
        )
        # Allow a larger step only when starting a new leg (waypoint).
        assert step < 5.0


def test_pitch_is_continuous_on_zoom():
    positions = [Position(date="a", lat=45.0, lng=13.0, days=1)]
    states = build_frame_states(positions)
    zoom = states[INTRO_HOLD : INTRO_HOLD + ZOOM_IN_FRAMES]
    pitches = [s.pitch for s in zoom]
    assert pitches[0] < pitches[-1]
    assert all(0.0 <= p <= 1.0 for p in pitches)
    # No abrupt 0↔1 flip in a single frame beyond a smooth step.
    for a, b in zip(pitches, pitches[1:]):
        assert abs(b - a) < 0.25


def test_camera_pose_keeps_focus_when_pitched():
    """Pitch must orbit the camera, not slide the look-at hundreds of km north."""
    from journeymap.animate import _camera_pose

    lat, lng = 45.5127, 13.5954
    _pos0, focal0, _up0 = _camera_pose(lat, lng, 1.1, pitch=0.0)
    _pos1, focal1, _up1 = _camera_pose(lat, lng, 1.1, pitch=1.0)
    f0_lat, f0_lng = xyz_to_ll(focal0)
    f1_lat, f1_lng = xyz_to_ll(focal1)
    assert abs(f0_lat - lat) < 1e-6
    assert abs(f1_lat - lat) < 1e-6
    assert abs(((f0_lng - lng + 180) % 360) - 180) < 1e-6
    assert abs(((f1_lng - lng + 180) % 360) - 180) < 1e-6
    # Camera should move when pitched (oblique), but focus stays put.
    import numpy as np

    assert np.linalg.norm(_pos1 - _pos0) > 1e-4


def test_osm_zoom_closer_is_higher():
    assert osm_zoom_for_distance(CAM_DIST_CLOSE_MIN) >= osm_zoom_for_distance(1.5)


def test_view_half_angle_positive():
    assert view_half_angle_deg(CAM_DIST_WIDE) > 0
    assert view_half_angle_deg(CAM_DIST_CLOSE_MIN) > 0
    assert view_half_angle_deg(CAM_DIST_CLOSE_MIN) < view_half_angle_deg(CAM_DIST_WIDE)


# ---- camera / timeline ------------------------------------------------------


def test_close_camera_distance_tighter_for_short_span():
    short = [
        Position(date="a", lat=45.5, lng=13.6, days=1),
        Position(date="b", lat=45.4, lng=13.7, days=1),
    ]
    long = [
        Position(date="a", lat=40.0, lng=-74.0, days=1),
        Position(date="b", lat=40.0, lng=0.0, days=1),
    ]
    assert close_camera_distance(short) < close_camera_distance(long)
    assert CAM_DIST_CLOSE_MIN <= close_camera_distance(short) <= CAM_DIST_CLOSE_MAX


def test_close_camera_distance_for_span_pulls_in_for_short_hops():
    assert close_camera_distance_for_span(0.2) < close_camera_distance_for_span(2.0)
    assert close_camera_distance_for_span(2.0) <= close_camera_distance_for_span(20.0)
    assert CAM_DIST_CLOSE_MIN <= close_camera_distance_for_span(0.05) <= CAM_DIST_CLOSE_MAX


def test_build_frame_states_single():
    positions = [Position(date="a", lat=45.0, lng=13.0, days=5)]
    states = build_frame_states(positions)
    assert len(states) == INTRO_HOLD + ZOOM_IN_FRAMES + ZOOM_OUT_FRAMES + OUTRO_HOLD
    assert states[0].marker_indices == [0]
    assert states[0].traveler is None
    assert states[0].distance == CAM_DIST_WIDE
    assert states[-1].distance == pytest.approx(overview_camera_distance(positions))
    assert states[-1].distance < CAM_DIST_WIDE


def test_build_frame_states_zooms_from_wide_to_close():
    positions = [
        Position(date="a", lat=45.5, lng=13.6, days=1),
        Position(date="b", lat=43.5, lng=16.4, days=1),
    ]
    leg_dist = close_camera_distance_for_span(
        angular_distance_deg(45.5, 13.6, 43.5, 16.4)
    )
    states = build_frame_states(positions)
    assert states[0].distance == CAM_DIST_WIDE
    zoom_end = states[INTRO_HOLD + ZOOM_IN_FRAMES - 1]
    assert zoom_end.distance == pytest.approx(leg_dist)
    # Mid-journey tracks the current leg's framing.
    mid = states[INTRO_HOLD + ZOOM_IN_FRAMES]
    assert mid.distance == pytest.approx(leg_dist)
    assert states[-1].distance == pytest.approx(overview_camera_distance(positions))


def test_build_frame_states_zooms_in_for_short_legs():
    positions = [
        Position(date="a", lat=43.57, lng=15.94, days=1),
        Position(date="b", lat=43.59, lng=15.93, days=1),  # ~0.02°
        Position(date="c", lat=39.49, lng=20.26, days=1),  # ~6°
    ]
    states = build_frame_states(positions)
    travel = [s for s in states if s.traveler is not None]
    assert travel
    short_leg = [s for s in travel if s.focus_lat > 43.0]
    long_leg = [s for s in travel if s.focus_lat < 42.0]
    assert short_leg and long_leg
    assert min(s.distance for s in short_leg) < min(s.distance for s in long_leg)
    assert min(s.distance for s in short_leg) < close_camera_distance(positions)


def test_build_frame_states_outro_shows_full_route():
    positions = [
        Position(date="a", lat=45.5, lng=13.6, days=1),
        Position(date="b", lat=43.5, lng=16.4, days=1),
    ]
    states = build_frame_states(positions)
    overview = overview_camera_distance(positions)
    assert states[-1].distance == pytest.approx(overview)
    assert overview < CAM_DIST_WIDE * 0.55
    assert overview >= close_camera_distance(positions)
    assert states[-1].marker_indices == [0, 1]
    assert states[-1].use_detail is False
    assert len(states[-1].path_points) >= 2
    # Zoom-out segment increases distance toward overview (not full globe).
    outro_start = len(states) - OUTRO_HOLD - ZOOM_OUT_FRAMES
    dists = [s.distance for s in states[outro_start : outro_start + ZOOM_OUT_FRAMES]]
    assert dists[0] <= dists[-1]
    assert dists[-1] == pytest.approx(overview)
    assert states[-1].use_detail is False
    assert all(s.marker_indices == [0, 1] for s in states[outro_start:])


def test_overview_markers_are_endpoints_only():
    positions = [
        Position(date="a", lat=45.0, lng=13.0, days=1),
        Position(date="b", lat=44.0, lng=14.0, days=1),
        Position(date="c", lat=43.0, lng=15.0, days=1),
        Position(date="d", lat=42.0, lng=16.0, days=1),
    ]
    states = build_frame_states(positions)
    assert states[-1].marker_indices == [0, 3]


def test_overview_camera_distance_fits_route_not_globe():
    short = [
        Position(date="a", lat=45.5, lng=13.6, days=1),
        Position(date="b", lat=43.5, lng=16.4, days=1),
    ]
    long = [
        Position(date="a", lat=40.0, lng=-74.0, days=1),
        Position(date="b", lat=48.0, lng=2.0, days=1),
    ]
    assert overview_camera_distance(short) < overview_camera_distance(long)
    assert overview_camera_distance(short) < CAM_DIST_WIDE * 0.55
    assert overview_camera_distance(long) <= CAM_DIST_WIDE * 0.55
    # Overview stays close to the tracking distance for short coastal routes.
    assert overview_camera_distance(short) < close_camera_distance(short) * 1.5


def test_route_marker_size_tracks_path_and_stays_small():
    close = route_marker_size(CAM_DIST_CLOSE_MIN)
    mid = route_marker_size(PATH_REF_DISTANCE)
    assert close <= MARKER_SIZE_MAX
    assert mid <= MARKER_SIZE_MAX
    # Within tracking zoom, path width (and markers) stay roughly constant.
    assert close == mid
    assert route_marker_size(CAM_DIST_CLOSE_MIN, render_scale=2) >= close
    assert route_marker_size(CAM_DIST_CLOSE_MIN, render_scale=2) <= MARKER_SIZE_MAX * 2


def test_path_tube_radius_scales_with_zoom():
    close = path_tube_radius(CAM_DIST_CLOSE_MIN)
    mid = path_tube_radius(PATH_REF_DISTANCE)
    far = path_tube_radius(2.0)
    assert close < mid < far
    # On-screen width stays roughly constant across zoom.
    assert path_width_px(CAM_DIST_CLOSE_MIN) == pytest.approx(
        path_width_px(PATH_REF_DISTANCE), rel=0.15
    )



def test_journey_center_midpoint():
    positions = [
        Position(date="a", lat=40.0, lng=10.0, days=1),
        Position(date="b", lat=50.0, lng=20.0, days=1),
    ]
    lat, lng = journey_center(positions)
    assert 40.0 < lat < 50.0
    assert 10.0 < lng < 20.0


def test_build_frame_states_two_has_travel():
    positions = [
        Position(date="a", lat=45.0, lng=13.0, days=5),
        Position(date="b", lat=43.5, lng=16.4, days=3),
    ]
    states = build_frame_states(positions)
    assert any(s.traveler is not None for s in states)
    assert states[-1].marker_indices == [0, 1]


def test_total_frames_matches_states():
    positions = [
        Position(date="a", lat=45.0, lng=13.0, days=1),
        Position(date="b", lat=44.0, lng=14.0, days=1),
    ]
    assert total_frames(positions) == len(build_frame_states(positions))
    assert total_frames([]) == OUTRO_HOLD


# ---- linear_interp / marker / hold ------------------------------------------


def test_linear_interp_endpoints():
    assert _linear_interp(1, 10, 50) == 10
    assert _linear_interp(30, 10, 50) == 50


def test_marker_size_endpoints():
    assert marker_size(1) == 30
    assert marker_size(30) == 100


def test_hold_frames_endpoints():
    assert hold_frames_for_days(1) == MIN_HOLD_FRAMES
    assert hold_frames_for_days(30) == MAX_HOLD_FRAMES
    assert MAX_HOLD_FRAMES <= 8  # keeps stops brief / smooth


# ---- assets / scale ---------------------------------------------------------


def test_scale_image_output_size():
    src = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
    for size in (30, 50, 80, 100):
        assert scale_image(src, size).size == (size, size)


def test_load_logo():
    logo = load_logo()
    assert logo.mode == "RGBA"
    assert logo.size == (400, 400)


def test_load_earth_texture():
    earth = load_earth_texture()
    assert earth.mode == "RGB"
    w, h = earth.size
    assert w == 2 * h


def test_world_osm_tiles_cover_zoom():
    from journeymap.animate import WORLD_TILE_ZOOM, world_osm_tiles

    tiles = world_osm_tiles(2)
    assert len(tiles) == 16
    assert all(t[0] == 2 for t in tiles)
    assert world_osm_tiles(WORLD_TILE_ZOOM)
    n = 2**WORLD_TILE_ZOOM
    assert len(world_osm_tiles()) == n * n


def test_mercator_mosaic_to_equirect_size_and_poles():
    from journeymap.animate import mercator_mosaic_to_equirect

    # Distinct north/south so we can check orientation after warp.
    merc = Image.new("RGB", (256, 256), (0, 80, 160))
    for y in range(32):
        for x in range(256):
            merc.putpixel((x, y), (220, 40, 40))  # north strip
            merc.putpixel((x, 255 - y), (40, 220, 40))  # south strip
    eq = mercator_mosaic_to_equirect(merc, width=128, height=64)
    assert eq.size == (128, 64)
    assert eq.mode == "RGB"
    # Row 0 is north → reddish; last row is south → greenish.
    north = eq.getpixel((64, 0))
    south = eq.getpixel((64, 63))
    assert north[0] > north[2]
    assert south[1] > south[0]


def test_build_osm_earth_texture_uses_cache(tmp_path: Path):
    from journeymap.animate import build_osm_earth_texture

    cache = tmp_path / "earth.png"
    fetcher = solid_tile_fetcher((11, 22, 33))
    first = build_osm_earth_texture(
        fetcher, zoom=1, width=64, height=32, cache_path=cache
    )
    assert first.size == (64, 32)
    assert cache.exists()
    # Second call must hit cache (even if fetcher would differ).
    second = build_osm_earth_texture(
        solid_tile_fetcher((200, 0, 0)),
        zoom=1,
        width=64,
        height=32,
        cache_path=cache,
    )
    assert second.getpixel((0, 0)) == first.getpixel((0, 0))
    assert second.getpixel((0, 0)) == (11, 22, 33)


def test_heal_tile_seams_averages_boundaries():
    from journeymap.animate import _heal_tile_seams

    # Two horizontal tiles: left red, right blue → seam should blend.
    img = Image.new("RGB", (512, 256), (255, 0, 0))
    for y in range(256):
        for x in range(256, 512):
            img.putpixel((x, y), (0, 0, 255))
    healed = _heal_tile_seams(img, 256)
    seam_l = healed.getpixel((255, 128))
    seam_r = healed.getpixel((256, 128))
    assert seam_l == seam_r
    assert seam_l[0] == seam_l[2]  # purple-ish average
    assert 100 < seam_l[0] < 160


def test_solid_tile_fetcher():
    fetcher = solid_tile_fetcher((10, 20, 30))
    img = fetcher(5, 1, 2)
    assert img.size == (256, 256)
    assert img.getpixel((0, 0)) == (10, 20, 30)


# ---- generate_animation -----------------------------------------------------


def test_generate_animation_requires_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("journeymap.animate.shutil.which", lambda _: None)
    journey = JourneyMap(positions=[Position(date="2025-09-13", lat=45.5, lng=13.6, days=5)])
    with pytest.raises(RuntimeError, match="ffmpeg"):
        generate_animation(journey, tmp_path / "out.mp4")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not available")
def test_generate_animation_produces_file(tmp_path: Path):
    pytest.importorskip("pyvista")
    journey = JourneyMap(
        positions=[
            Position(date="2025-09-13", lat=45.5127, lng=13.5954, days=2),
            Position(date="2026-01-17", lat=43.5088, lng=16.4402, days=2),
        ]
    )
    output = tmp_path / "journey.mp4"
    earth = Image.new("RGB", (64, 32), (30, 90, 160))
    logo = Image.new("RGBA", (40, 40), (255, 0, 0, 200))
    generate_animation(
        journey,
        output,
        earth_texture=earth,
        logo=logo,
        tile_fetcher=solid_tile_fetcher((180, 200, 160)),
    )
    assert output.exists()
    assert output.stat().st_size > 0


def test_write_and_roundtrip_json(tmp_path: Path):
    path = tmp_path / "journey.json"
    journey = JourneyMap(
        positions=[Position(date="2025-09-13", lat=45.5, lng=13.6, days=10)]
    )
    write_journey_json(journey, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["positions"][0]["lat"] == 45.5


def test_image_constants():
    assert IMG_WIDTH > 0 and IMG_HEIGHT > 0
