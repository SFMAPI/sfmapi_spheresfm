from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypedDict

from .backend import SphereSfMBackend


class ProviderManifestDict(TypedDict):
    provider_id: str
    display_name: str
    capabilities: list[str]
    backend_actions: list[str]
    priority_hint: int


class PluginManifestDict(TypedDict):
    plugin_id: str
    display_name: str
    description: str
    package_name: str
    github_url: str
    entry_points: list[str]
    providers: list[ProviderManifestDict]
    runtime_modes: dict[str, Any]
    capabilities: list[str]
    backend_actions: list[str]
    config_schemas: list[str]
    artifact_contracts: list[str]
    licenses: list[dict[str, str]]
    upstream_projects: list[dict[str, str]]
    compatibility: dict[str, Any]
    conformance: dict[str, str]
    trust_tier: str


manifest: PluginManifestDict = {
    "plugin_id": "spheresfm",
    "display_name": "SphereSFM",
    "description": "Backend plugin for spherical Structure-from-Motion workflows.",
    "package_name": "sfmapi-spheresfm",
    "github_url": "https://github.com/SFMAPI/sfmapi_spheresfm.git",
    "entry_points": ["sfmapi_spheresfm.plugin:plugin"],
    "providers": [
        {
            "provider_id": "spheresfm",
            "display_name": "SphereSFM",
            "capabilities": [
                "features.extract.sift",
                "pairs.exhaustive",
                "matches.verify",
                "map.spherical",
                "projection.equirectangular_to_cubemap",
                "projection.equirectangular_to_perspective",
            ],
            "backend_actions": ["spheresfm.*"],
            "priority_hint": 15,
        }
    ],
    "runtime_modes": {
        "uv": {
            "source": "git",
            "url": "https://github.com/SFMAPI/sfmapi_spheresfm.git",
            "ref": "main",
            "package": "sfmapi-spheresfm",
        },
        "docker": {},
        "external_tool": {
            "executable_names": ["spheresfm"],
            "env_vars": ["SFMAPI_SPHERESFM_EXECUTABLE", "SPHERESFM_EXE"],
            "version_args": ["help"],
        },
    },
    "capabilities": [
        "features.extract.sift",
        "pairs.exhaustive",
        "matches.verify",
        "map.spherical",
        "projection.equirectangular_to_cubemap",
        "projection.equirectangular_to_perspective",
    ],
    "backend_actions": ["spheresfm.*"],
    "config_schemas": ["spheresfm.*"],
    "artifact_contracts": [
        "sfmapi.spherical_dataset",
        "sfmapi.reconstruction",
    ],
    "licenses": [{"name": "AGPL-3.0-or-later"}],
    "upstream_projects": [
        {
            "name": "SphereSFM",
            "url": "https://github.com/SFMAPI/SphereSFM",
            "license": "Upstream license",
        }
    ],
    "compatibility": {
        "sfmapi": ">=0.0.1",
        "python": ">=3.12,<3.13",
        "os": ["windows", "linux"],
        "cuda": "optional",
    },
    "conformance": {"status": "not_run", "suite": "sfmapi-bench"},
    "trust_tier": "community",
}


def backend_factory() -> SphereSfMBackend:
    return SphereSfMBackend()


def get_plugin_manifest() -> PluginManifestDict:
    return manifest


def register(
    register_backend: Callable[[str, Callable[[], SphereSfMBackend]], None],
) -> None:
    register_backend("spheresfm", backend_factory)


@dataclass(frozen=True)
class SfmapiBackendPlugin:
    manifest: PluginManifestDict
    backend_name: str
    backend_factory: Callable[[], SphereSfMBackend]

    def get_plugin_manifest(self) -> PluginManifestDict:
        return self.manifest

    def register(
        self,
        register_backend: Callable[[str, Callable[[], SphereSfMBackend]], None],
    ) -> None:
        register_backend(self.backend_name, self.backend_factory)


plugin = SfmapiBackendPlugin(
    manifest=manifest,
    backend_name="spheresfm",
    backend_factory=backend_factory,
)


__all__ = [
    "PluginManifestDict",
    "SfmapiBackendPlugin",
    "backend_factory",
    "get_plugin_manifest",
    "manifest",
    "plugin",
    "register",
]
