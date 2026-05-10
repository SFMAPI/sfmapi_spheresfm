# sfmapi SphereSfM backend

This package runs sfmapi with a SphereSfM-backed action catalog. The wrapper is AGPL-3.0-or-later; the upstream SphereSfM project is included as a git submodule under `third_party/spheresfm` and keeps its own BSD-3-Clause license.

SphereSfM is a COLMAP-derived spherical-image SfM engine. The sfmapi adapter is Python-based, but real work is executed through the SphereSfM `colmap` executable built from the upstream submodule.

## Layout

- `src/sfmapi_spheresfm/`: Python backend adapter and sfmapi launcher.
- `third_party/spheresfm/`: upstream SphereSfM submodule.
- `tests/`: lightweight contract and HTTP discovery tests.
- `LICENSES/`: copied upstream license notice.

## Setup

```powershell
git submodule update --init --recursive
uv venv
uv sync --extra dev --extra mcp --with-editable ..\sfmapi
```

Build SphereSfM by following its upstream COLMAP-style build instructions, then point this wrapper at the resulting executable.

```powershell
$env:SFMAPI_SPHERESFM_EXECUTABLE="C:\path\to\spheresfm\build\src\exe\Release\colmap.exe"
```

## Run sfmapi

```powershell
uv run sfmapi-spheresfm-api --spheresfm-executable $env:SFMAPI_SPHERESFM_EXECUTABLE --mcp local
```

The launcher configures an in-memory sfmapi demo server: SQLite memory DB, memory blob storage, inline queue, and inline tasks.

## Native Actions

Discover actions:

```powershell
curl "http://127.0.0.1:8000/v1/backend/actions?include_schemas=true"
```

Primary actions:

- `spheresfm.reconstructPanoramaFolder`: database creation, spherical feature extraction, matching, and mapper.
- `spheresfm.convertToCubemap`: runs SphereSfM's `sphere_cubic_reprojecer` command.
- `spheresfm.colmap.<command>`: runs an allow-listed non-GUI command from the SphereSfM executable.

Example panorama reconstruction input:

```json
{
  "image_path": "C:/data/pano/images",
  "workspace_path": "C:/data/pano/colmap",
  "camera_params": "1,3520,1760",
  "matching_mode": "spatial",
  "spatial_is_gps": false,
  "spatial_max_distance": 50
}
```

GUI commands are intentionally omitted from the public action catalog so the API remains server-safe.

## Tests

```powershell
uv run pytest -q
uv run ruff check src tests
```

The default tests mock subprocess execution and do not require a built SphereSfM binary.

