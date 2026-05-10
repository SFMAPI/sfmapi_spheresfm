from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

try:
    from app.core.errors import CapabilityUnavailableError, NotFoundError, ValidationError
except ModuleNotFoundError:  # pragma: no cover - allows adapter tests without sfmapi installed

    class CapabilityUnavailableError(RuntimeError):  # type: ignore[no-redef]
        def __init__(self, *, capability: str, reason: str = "") -> None:
            super().__init__(reason or capability)

    class NotFoundError(RuntimeError):  # type: ignore[no-redef]
        pass

    class ValidationError(RuntimeError):  # type: ignore[no-redef]
        pass


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPHERESFM_ROOT = REPO_ROOT / "third_party" / "spheresfm"

SPHERESFM_COMMANDS: tuple[str, ...] = (
    "help",
    "automatic_reconstructor",
    "bundle_adjuster",
    "color_extractor",
    "database_cleaner",
    "database_creator",
    "database_merger",
    "delaunay_mesher",
    "exhaustive_matcher",
    "feature_extractor",
    "feature_importer",
    "hierarchical_mapper",
    "image_deleter",
    "image_filterer",
    "image_rectifier",
    "image_registrator",
    "image_undistorter",
    "image_undistorter_standalone",
    "mapper",
    "matches_importer",
    "model_aligner",
    "model_analyzer",
    "model_comparer",
    "model_converter",
    "model_cropper",
    "model_merger",
    "model_orientation_aligner",
    "model_splitter",
    "model_transformer",
    "patch_match_stereo",
    "point_filtering",
    "point_triangulator",
    "poisson_mesher",
    "project_generator",
    "rig_bundle_adjuster",
    "sequential_matcher",
    "spatial_matcher",
    "sphere_cubic_reprojecer",
    "stereo_fusion",
    "transitive_matcher",
    "vocab_tree_builder",
    "vocab_tree_matcher",
    "vocab_tree_retriever",
)
SPHERESFM_COMMAND_SET = frozenset(SPHERESFM_COMMANDS)
READ_ONLY_COMMANDS = {"help", "model_analyzer", "model_comparer"}
MATCHING_MODES = {"spatial", "vocabtree", "exhaustive", "sequential"}


def _expand_path(value: str | Path) -> Path:
    return Path(os.path.expandvars(str(value).strip().strip('"'))).expanduser()


def _default_executable_candidates() -> list[Path]:
    names = ["colmap.exe", "colmap"] if os.name == "nt" else ["colmap", "colmap.exe"]
    relative_dirs = [
        Path("build") / "src" / "exe" / "Release",
        Path("build") / "src" / "exe" / "Debug",
        Path("build") / "src" / "exe",
        Path("build") / "src" / "exe" / "RelWithDebInfo",
    ]
    return [
        DEFAULT_SPHERESFM_ROOT / relative_dir / name
        for relative_dir in relative_dirs
        for name in names
    ]


def resolve_spheresfm_executable(value: str | Path | None) -> Path | None:
    raw = value or os.environ.get("SFMAPI_SPHERESFM_EXECUTABLE")
    if raw:
        path = _expand_path(raw)
        candidates = [path]
        if path.is_dir():
            candidates = [
                path / "colmap.exe",
                path / "colmap",
                path / "bin" / "colmap.exe",
                path / "bin" / "colmap",
            ]
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        return None

    for candidate in _default_executable_candidates():
        if candidate.exists():
            return candidate.resolve()
    return None


def configure_spheresfm_environment(
    executable: str | Path | None = None,
    *,
    validate: bool = False,
) -> Path | None:
    resolved = resolve_spheresfm_executable(executable)
    if resolved is None:
        if validate:
            raise ValueError(
                "SphereSfM executable not found. Build the upstream submodule and set "
                "SFMAPI_SPHERESFM_EXECUTABLE or pass --spheresfm-executable."
            )
        return None
    os.environ["SFMAPI_SPHERESFM_EXECUTABLE"] = str(resolved)
    existing = os.environ.get("PATH", "")
    parent = str(resolved.parent)
    if parent not in existing.split(os.pathsep):
        os.environ["PATH"] = os.pathsep.join([parent, existing])
    return resolved


class SphereSfMBackend:
    name = "spheresfm"
    version = "0.1.0"
    vendor = "SphereSfM"

    def __init__(self, executable: str | Path | None = None) -> None:
        self._executable_override = _expand_path(executable).resolve() if executable else None

    def capabilities(self) -> set[str]:
        return set()

    def runtime_versions(self) -> dict[str, str]:
        executable = self._find_executable()
        versions = {
            "backend": self.version,
            "spheresfm_root": str(DEFAULT_SPHERESFM_ROOT),
            "spheresfm_executable": str(executable) if executable else "missing",
        }
        commit = self._git_revision(DEFAULT_SPHERESFM_ROOT)
        if commit:
            versions["spheresfm_commit"] = commit
        return versions

    def list_backend_actions(self, *, include_schemas: bool = False) -> list[dict[str, Any]]:
        actions = [
            self._reconstruct_action(include_schemas=include_schemas),
            self._cubemap_action(include_schemas=include_schemas),
        ]
        actions.extend(
            self._command_action(command, include_schemas=include_schemas)
            for command in SPHERESFM_COMMANDS
        )
        return sorted(actions, key=lambda action: str(action["action_id"]))

    def get_backend_action(self, action_id: str) -> dict[str, Any]:
        for action in self.list_backend_actions(include_schemas=True):
            if action["action_id"] == action_id:
                return action
        raise NotFoundError(f"Backend action {action_id!r} not found")

    def validate_backend_action(self, action_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
        try:
            normalized = self._normalize_action_inputs(action_id, dict(inputs or {}))
        except ValidationError as exc:
            return {
                "action_id": action_id,
                "valid": False,
                "errors": [{"field": None, "message": str(exc)}],
                "normalized_inputs": {},
            }
        return {
            "action_id": action_id,
            "valid": True,
            "errors": [],
            "normalized_inputs": normalized,
        }

    def run_backend_action(
        self,
        action_id: str,
        inputs: dict[str, Any],
        *,
        workspace: Path | None = None,
        progress: Any | None = None,
    ) -> dict[str, Any]:
        normalized = self._normalize_action_inputs(action_id, dict(inputs or {}))
        if action_id == "spheresfm.reconstructPanoramaFolder":
            return self._run_reconstruct(normalized, workspace=workspace, progress=progress)
        if action_id == "spheresfm.convertToCubemap":
            return self._run_convert_to_cubemap(normalized, progress=progress)
        if action_id.startswith("spheresfm.colmap."):
            command = action_id.removeprefix("spheresfm.colmap.")
            return self._run_generic_command(command, normalized)
        raise NotFoundError(f"Backend action {action_id!r} not found")

    def _find_executable(self) -> Path | None:
        if self._executable_override is not None:
            return self._executable_override if self._executable_override.exists() else None
        return resolve_spheresfm_executable(None)

    def _require_executable(self) -> Path:
        executable = self._find_executable()
        if executable is None:
            raise CapabilityUnavailableError(
                capability="backend.actions",
                reason=(
                    "SphereSfM executable not found. Build third_party/spheresfm and set "
                    "SFMAPI_SPHERESFM_EXECUTABLE."
                ),
            )
        return executable

    def _git_revision(self, root: Path) -> str | None:
        if not root.exists():
            return None
        try:
            completed = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except OSError:
            return None
        value = completed.stdout.strip()
        return value or None

    def _run_reconstruct(
        self,
        inputs: dict[str, Any],
        *,
        workspace: Path | None,
        progress: Any | None,
    ) -> dict[str, Any]:
        image_path = Path(str(inputs["image_path"]))
        workspace_path = Path(str(inputs["workspace_path"]))
        database_path = Path(str(inputs.get("database_path") or workspace_path / "database.db"))
        sparse_path = Path(str(inputs.get("sparse_path") or workspace_path / "sparse"))
        workspace_path.mkdir(parents=True, exist_ok=True)
        sparse_path.mkdir(parents=True, exist_ok=True)

        matching_mode = str(inputs.get("matching_mode", "spatial"))
        commands: list[tuple[str, dict[str, Any]]] = [
            ("database_creator", {"database_path": database_path}),
            (
                "feature_extractor",
                {
                    "database_path": database_path,
                    "image_path": image_path,
                    "ImageReader.camera_model": "SPHERE",
                    "ImageReader.camera_params": inputs.get("camera_params", "1,3520,1760"),
                    "ImageReader.single_camera": int(bool(inputs.get("single_camera", True))),
                },
            ),
            (
                self._matcher_command(matching_mode),
                self._matcher_options(matching_mode, inputs, database_path),
            ),
            (
                "mapper",
                {
                    "database_path": database_path,
                    "image_path": image_path,
                    "output_path": sparse_path,
                    "Mapper.ba_refine_focal_length": 0,
                    "Mapper.ba_refine_principal_point": 0,
                    "Mapper.ba_refine_extra_params": 0,
                    "Mapper.sphere_camera": 1,
                },
            ),
        ]
        if inputs.get("camera_mask_path"):
            commands[1][1]["ImageReader.camera_mask_path"] = inputs["camera_mask_path"]
        if inputs.get("pose_path"):
            commands[1][1]["ImageReader.pose_path"] = inputs["pose_path"]

        results: list[dict[str, Any]] = []
        total = len(commands)
        for index, (command, options) in enumerate(commands, start=1):
            self._progress(progress, command, index - 1, total)
            results.append(
                self._run_colmap(
                    command,
                    options=options,
                    timeout_seconds=inputs.get("timeout_seconds"),
                )
            )
            self._progress(progress, command, index, total)
        return {
            "steps": results,
            "image_path": str(image_path),
            "workspace_path": str(workspace_path),
            "database_path": str(database_path),
            "sparse_path": str(sparse_path),
        }

    def _run_convert_to_cubemap(
        self,
        inputs: dict[str, Any],
        *,
        progress: Any | None,
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            "image_path": inputs["image_path"],
            "input_path": inputs["input_path"],
            "output_path": inputs["output_path"],
        }
        for key in ("image_ids", "image_size", "field_of_view"):
            if key in inputs:
                options[key] = inputs[key]
        self._progress(progress, "sphere_cubic_reprojecer", 0, 1)
        result = self._run_colmap(
            "sphere_cubic_reprojecer",
            options=options,
            timeout_seconds=inputs.get("timeout_seconds"),
        )
        self._progress(progress, "sphere_cubic_reprojecer", 1, 1)
        return result

    def _run_generic_command(self, command: str, inputs: dict[str, Any]) -> dict[str, Any]:
        self._validate_command(command)
        options = dict(inputs.get("options") or {})
        positional = [str(arg) for arg in inputs.get("args", [])]
        return self._run_colmap(
            command,
            options=options,
            positional=positional,
            cwd=Path(str(inputs["cwd"])) if inputs.get("cwd") else None,
            timeout_seconds=inputs.get("timeout_seconds"),
        )

    def _run_colmap(
        self,
        command: str,
        *,
        options: dict[str, Any] | None = None,
        positional: list[str] | None = None,
        cwd: Path | None = None,
        timeout_seconds: int | float | None = None,
    ) -> dict[str, Any]:
        executable = self._require_executable()
        args = [str(executable), command, *(positional or [])]
        for key, value in (options or {}).items():
            if value is None:
                continue
            args.append(f"--{key}")
            args.append(self._stringify(value))
        try:
            completed = subprocess.run(
                args,
                check=True,
                capture_output=True,
                text=True,
                cwd=str(cwd) if cwd else None,
                timeout=timeout_seconds,
            )
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
            raise ValidationError(f"SphereSfM command failed: {detail}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ValidationError(f"SphereSfM command timed out after {timeout_seconds}s") from exc
        return {
            "command": command,
            "args": args,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    def _matcher_command(self, mode: str) -> str:
        if mode == "vocabtree":
            return "vocab_tree_matcher"
        if mode == "exhaustive":
            return "exhaustive_matcher"
        if mode == "sequential":
            return "sequential_matcher"
        return "spatial_matcher"

    def _matcher_options(
        self,
        mode: str,
        inputs: dict[str, Any],
        database_path: Path,
    ) -> dict[str, Any]:
        options: dict[str, Any] = {"database_path": database_path}
        if mode == "spatial":
            options.update(
                {
                    "SiftMatching.max_error": inputs.get("sift_max_error", 4),
                    "SiftMatching.min_num_inliers": inputs.get("sift_min_num_inliers", 50),
                    "SpatialMatching.is_gps": int(bool(inputs.get("spatial_is_gps", False))),
                    "SpatialMatching.max_distance": inputs.get("spatial_max_distance", 50),
                }
            )
        if mode == "vocabtree" and inputs.get("vocab_tree_path"):
            options["VocabTreeMatching.vocab_tree_path"] = inputs["vocab_tree_path"]
        return options

    def _reconstruct_action(self, *, include_schemas: bool) -> dict[str, Any]:
        descriptor = {
            "action_id": "spheresfm.reconstructPanoramaFolder",
            "backend": self.name,
            "display_name": "SphereSfM panorama reconstruction",
            "description": "Run the documented spherical-image feature, matching, and mapper sequence.",
            "category": "pipeline",
            "stability": "backend_extension",
            "side_effects": "write",
            "long_running": True,
            "supports_progress": True,
            "idempotent": False,
            "gpu_required": True,
            "required_capabilities": [],
            "metadata": {"family": "spheresfm", "source": "SphereSfM README command sequence"},
        }
        if include_schemas:
            descriptor["input_schema"] = self._reconstruct_input_schema()
            descriptor["output_schema"] = self._run_output_schema()
        return descriptor

    def _cubemap_action(self, *, include_schemas: bool) -> dict[str, Any]:
        descriptor = {
            "action_id": "spheresfm.convertToCubemap",
            "backend": self.name,
            "display_name": "SphereSfM cubic reprojection",
            "description": "Convert a spherical reconstruction to cubic/perspective images.",
            "category": "spherical",
            "stability": "backend_extension",
            "side_effects": "write",
            "long_running": True,
            "supports_progress": True,
            "idempotent": False,
            "gpu_required": False,
            "required_capabilities": [],
            "metadata": {"family": "spheresfm", "command": "sphere_cubic_reprojecer"},
        }
        if include_schemas:
            descriptor["input_schema"] = self._cubemap_input_schema()
            descriptor["output_schema"] = self._run_output_schema()
        return descriptor

    def _command_action(self, command: str, *, include_schemas: bool) -> dict[str, Any]:
        read_only = command in READ_ONLY_COMMANDS
        descriptor = {
            "action_id": f"spheresfm.colmap.{command}",
            "backend": self.name,
            "display_name": f"SphereSfM {command}",
            "description": f"Run the upstream SphereSfM `colmap {command}` command.",
            "category": self._command_category(command),
            "stability": "backend_extension",
            "side_effects": "read" if read_only else "write",
            "long_running": not read_only,
            "supports_progress": False,
            "idempotent": read_only,
            "gpu_required": command
            in {
                "feature_extractor",
                "exhaustive_matcher",
                "sequential_matcher",
                "spatial_matcher",
                "vocab_tree_matcher",
                "patch_match_stereo",
            },
            "required_capabilities": [],
            "metadata": {"family": "spheresfm", "command": command},
        }
        if include_schemas:
            descriptor["input_schema"] = self._generic_command_input_schema(command)
            descriptor["output_schema"] = self._run_output_schema()
        return descriptor

    def _reconstruct_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["image_path", "workspace_path"],
            "properties": {
                "image_path": {"type": "string"},
                "workspace_path": {"type": "string"},
                "database_path": {"type": "string"},
                "sparse_path": {"type": "string"},
                "camera_params": {"type": "string", "default": "1,3520,1760"},
                "single_camera": {"type": "boolean", "default": True},
                "camera_mask_path": {"type": "string"},
                "pose_path": {"type": "string"},
                "matching_mode": {
                    "type": "string",
                    "enum": sorted(MATCHING_MODES),
                    "default": "spatial",
                },
                "vocab_tree_path": {"type": "string"},
                "sift_max_error": {"type": "number", "default": 4},
                "sift_min_num_inliers": {"type": "integer", "default": 50},
                "spatial_is_gps": {"type": "boolean", "default": False},
                "spatial_max_distance": {"type": "number", "default": 50},
                "timeout_seconds": {"type": "number"},
            },
        }

    def _cubemap_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["image_path", "input_path", "output_path"],
            "properties": {
                "image_path": {"type": "string"},
                "input_path": {"type": "string"},
                "output_path": {"type": "string"},
                "image_ids": {"type": "string", "default": "0,1,2,3,4,5"},
                "image_size": {"type": "integer", "default": 0},
                "field_of_view": {"type": "number", "default": 45.0},
                "timeout_seconds": {"type": "number"},
            },
        }

    def _generic_command_input_schema(self, command: str) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": f"Positional args passed after `colmap {command}`.",
                },
                "options": {
                    "type": "object",
                    "additionalProperties": {"type": ["string", "number", "integer", "boolean"]},
                    "description": "Named COLMAP/SphereSfM options without leading `--`.",
                },
                "cwd": {"type": "string"},
                "timeout_seconds": {"type": "number"},
            },
        }

    def _run_output_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "args": {"type": "array", "items": {"type": "string"}},
                "returncode": {"type": "integer"},
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
            },
        }

    def _normalize_action_inputs(self, action_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
        self.get_backend_action(action_id)
        if action_id == "spheresfm.reconstructPanoramaFolder":
            for field in ("image_path", "workspace_path"):
                if not inputs.get(field):
                    raise ValidationError(f"{field} is required")
            matching_mode = str(inputs.get("matching_mode", "spatial"))
            if matching_mode not in MATCHING_MODES:
                raise ValidationError(
                    f"matching_mode must be one of: {', '.join(sorted(MATCHING_MODES))}"
                )
            inputs["matching_mode"] = matching_mode
            return inputs
        if action_id == "spheresfm.convertToCubemap":
            for field in ("image_path", "input_path", "output_path"):
                if not inputs.get(field):
                    raise ValidationError(f"{field} is required")
            return inputs
        if action_id.startswith("spheresfm.colmap."):
            command = action_id.removeprefix("spheresfm.colmap.")
            self._validate_command(command)
            args = inputs.get("args", [])
            if args is None:
                args = []
            if not isinstance(args, list):
                raise ValidationError("args must be an array of strings")
            options = inputs.get("options", {})
            if options is None:
                options = {}
            if not isinstance(options, dict):
                raise ValidationError("options must be an object")
            inputs["args"] = [str(arg) for arg in args]
            inputs["options"] = dict(options)
            return inputs
        raise NotFoundError(f"Backend action {action_id!r} not found")

    def _validate_command(self, command: str) -> None:
        if command == "gui":
            raise ValidationError("SphereSfM GUI is not exposed through sfmapi")
        if command not in SPHERESFM_COMMAND_SET:
            raise ValidationError(f"unknown SphereSfM command: {command!r}")

    def _command_category(self, command: str) -> str:
        if "matcher" in command:
            return "matching"
        if command.startswith("feature_"):
            return "features"
        if "mapper" in command or command in {"bundle_adjuster", "point_triangulator"}:
            return "mapping"
        if command.startswith("model_") or command.startswith("image_"):
            return "model"
        if command in {"patch_match_stereo", "stereo_fusion", "poisson_mesher", "delaunay_mesher"}:
            return "dense"
        if command.startswith("database_"):
            return "database"
        if command.startswith("sphere_"):
            return "spherical"
        return "utility"

    def _progress(self, progress: Any | None, phase: str, current: int, total: int) -> None:
        if progress is None:
            return
        try:
            progress.phase_progress(f"spheresfm.{phase}", current=current, total=total)
        except Exception:
            return

    def _stringify(self, value: Any) -> str:
        if isinstance(value, bool):
            return "1" if value else "0"
        return str(value)


__all__ = [
    "DEFAULT_SPHERESFM_ROOT",
    "MATCHING_MODES",
    "SPHERESFM_COMMANDS",
    "SPHERESFM_COMMAND_SET",
    "SphereSfMBackend",
    "configure_spheresfm_environment",
    "resolve_spheresfm_executable",
]
