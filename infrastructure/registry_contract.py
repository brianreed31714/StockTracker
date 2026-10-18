"""Infrastructure registry contract; stdlib-only and safe for CI/deployment preflight.

This module NEVER starts, stops, or trades. Active-manifest values are a
local runtime input, not something assumed from GitHub documentation.
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import json
from pathlib import Path, PurePosixPath
import py_compile
import re

REGISTRY_PATH = "infrastructure/registry.json"
ALLOWED_RELEASE = {
    "CryptoTracker": {"trader", "smart_money", "dashboard"},
    "StockTracker": {"trader", "geo_feed", "dashboard"},
}
REQUIRED_COMPONENTS = {
    "CryptoTracker": {"supervisor", "deployment_agent", "trader", "smart_money", "smart_money_rpc", "dashboard", "daily_review"},
    "StockTracker": {"supervisor", "deployment_agent", "trader", "geo_feed", "dashboard", "daily_review"},
}


class RegistryError(ValueError):
    pass


def safe_path(root: Path, value: str, *, must_exist: bool = False) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise RegistryError("Paths must be nonempty repository-relative POSIX strings")
    rel = PurePosixPath(value)
    if rel.is_absolute() or any(p in {".", ".."} for p in rel.parts) or ":" in value:
        raise RegistryError("Unsafe registry path")
    result = (root / str(rel)).resolve()
    if not result.is_relative_to(root.resolve()):
        raise RegistryError("Registry path escapes repository")
    if must_exist and not result.is_file():
        raise RegistryError(f"Declared source file missing: {value}")
    return result


def config_values(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise RegistryError(f"Tracked settings missing: {path.name}")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            values[key] = value.strip().strip("\"'")
    return values


def _registry(root: Path) -> dict:
    path = safe_path(root, REGISTRY_PATH, must_exist=True)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RegistryError("Unreadable infrastructure registry") from exc
    if not isinstance(data, dict):
        raise RegistryError("Infrastructure registry must be an object")
    return data


def validate_registry(root: Path, *, check_local_safety: bool = False) -> dict:
    """Fail closed on invalid dependencies, missing files, or unsafe settings.

    check_local_safety additionally examines a local .env *only for the
    three forbidden enablement flags*, never printing or persisting secrets.
    """
    root = Path(root).resolve()
    data = _registry(root)
    project = data.get("project")
    if project not in REQUIRED_COMPONENTS:
        raise RegistryError("Unknown registry project")
    if data.get("schema_version") != 1 or data.get("platform") != "Windows":
        raise RegistryError("Unsupported registry schema/platform")
    if data.get("mode") != "PAPER_ONLY":
        raise RegistryError("Registry would not preserve paper-only mode")
    if data.get("registry_policy") != "fail_closed_before_process_change":
        raise RegistryError("Missing fail-closed deployment policy")

    settings = config_values(safe_path(root, data["settings_file"], must_exist=True))
    for key, expected in data["safety"]["tracked_settings"].items():
        if settings.get(key, "").lower() != str(expected).lower():
            raise RegistryError(f"Protected tracked setting mismatch: {key}")
    if check_local_safety:
        local_path = safe_path(root, data["local_secrets_file"])
        if local_path.is_file():
            local_values = config_values(local_path)
            for key in data["safety"].get("effective_settings_must_not_enable", []):
                if str(local_values.get(key, "")).lower() in {"true", "1", "yes", "on"}:
                    raise RegistryError(f"Local runtime overrides protected safety switch: {key}")

    components = data.get("components")
    if not isinstance(components, list):
        raise RegistryError("Registry components must be a list")
    by_id = {}
    release_seen = set()
    for component in components:
        cid = component.get("id")
        if not isinstance(cid, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", cid) or cid in by_id:
            raise RegistryError(f"Invalid or duplicate component: {cid}")
        by_id[cid] = component
        safe_path(root, component["entrypoint"], must_exist=True)
        source_files = component.get("source_files")
        if not isinstance(source_files, list) or not source_files:
            raise RegistryError(f"{cid}: no declared source files")
        for path in source_files:
            safe_path(root, path, must_exist=True)
        if component["entrypoint"] not in source_files:
            raise RegistryError(f"{cid}: entrypoint must be in source_files")
        release = component.get("deployment_component")
        if release is not None:
            if release not in ALLOWED_RELEASE[project] or release != cid or release in release_seen:
                raise RegistryError(f"Invalid deployment component mapping: {cid}")
            release_seen.add(release)
            if not component.get("script_pattern") or not fnmatch.fnmatch(
                PurePosixPath(component["entrypoint"]).name, component["script_pattern"]
            ):
                raise RegistryError(f"Entrypoint doesn't match release script pattern: {cid}")
        if not isinstance(component.get("depends_on"), list):
            raise RegistryError(f"{cid}: invalid dependency list")
        for f in component.get("health", {}).get("artifact", "").splitlines():
            if f:
                safe_path(root, f)
    if not REQUIRED_COMPONENTS[project].issubset(by_id):
        raise RegistryError("Required infrastructure components missing")
    if release_seen != ALLOWED_RELEASE[project]:
        raise RegistryError("Missing deployable component contract")
    for cid, component in by_id.items():
        for dependency in component["depends_on"]:
            if dependency not in by_id or dependency == cid:
                raise RegistryError(f"{cid}: broken dependency {dependency}")
        for optional in component.get("dependency_optional", []):
            if optional not in component["depends_on"]:
                raise RegistryError(f"{cid}: optional dependency is not declared")
        for imported in component.get("code_imports", []):
            if imported not in component["depends_on"]:
                raise RegistryError(f"{cid}: imported Python module not in dependencies: {imported}")
        manager = component.get("managed_by")
        if manager is not None and manager not in by_id:
            raise RegistryError(f"{cid}: unknown supervisor {manager}")
        if component.get("manifest_key") and not component.get("deployment_component"):
            raise RegistryError(f"{cid}: only deployable components can use active manifest")
        if component.get("config_key") and component["config_key"] not in settings:
            raise RegistryError(f"{cid}: missing configured entrypoint key")
        if component.get("config_key") and not fnmatch.fnmatch(
            PurePosixPath(settings[component["config_key"]]).name, component["script_pattern"]
        ):
            raise RegistryError(f"{cid}: configured script doesn't match expected family")

    visiting, completed = set(), set()
    def visit(cid: str) -> None:
        if cid in visiting:
            raise RegistryError(f"Dependency cycle including {cid}")
        if cid in completed:
            return
        visiting.add(cid)
        for other in by_id[cid]["depends_on"]:
            visit(other)
        visiting.remove(cid)
        completed.add(cid)
    for cid in by_id:
        visit(cid)

    # Prove that local Python imports are covered by the owning component
    # or a declared dependency. This catches a missing module edge BEFORE
    # the Windows release agent can stop a service.
    for cid, comp in by_id.items():
        entry = safe_path(root, comp["entrypoint"])
        if entry.suffix != ".py":
            continue
        closure = {cid}
        stack = list(comp["depends_on"])
        while stack:
            dependency = stack.pop()
            if dependency in closure:
                continue
            closure.add(dependency)
            stack.extend(by_id[dependency]["depends_on"])
        allowed_sources = {
            src for dep_id in closure for src in by_id[dep_id]["source_files"]
        }
        try:
            tree = ast.parse(entry.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeError) as exc:
            raise RegistryError(f"{cid}: invalid Python entrypoint") from exc
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                relmodule = name.replace(".", "/") + ".py"
                candidates = [relmodule]
                if "/" not in relmodule:
                    parent = PurePosixPath(comp["entrypoint"]).parent
                    candidates.append(str(parent / relmodule))
                for path in candidates:
                    if (root / path).is_file() and path not in allowed_sources:
                        raise RegistryError(f"{cid}: undeclared local import {path}")

    tasks = data.get("scheduled_tasks")
    if not isinstance(tasks, list) or not tasks:
        raise RegistryError("No scheduled task contract")
    task_names = set()
    for task in tasks:
        if task["name"] in task_names or not task["name"].startswith(project + " "):
            raise RegistryError("Duplicate or cross-project task name")
        task_names.add(task["name"])
        safe_path(root, task["installer"], must_exist=True)
        safe_path(root, task["script"], must_exist=True)
    safe_path(root, data["runtime_manifest"])
    output = safe_path(root, data["inventory_output"])
    if not output.is_relative_to((root / "deploy" / "state").resolve()):
        raise RegistryError("Runtime inventory must remain in ignored local state")
    return data


def components_by_id(registry: dict) -> dict[str, dict]:
    return {x["id"]: x for x in registry["components"]}


def release_preflight(root: Path, components: list[str], files: dict[str, str]) -> dict:
    """Pre-destructive validation for a local agent deployment request.

    The existing agent must also verify approved Git blobs and its own
    paper-trading invariants; this is an additional registry contract.
    """
    root = Path(root).resolve()
    registry = validate_registry(root, check_local_safety=True)
    by_id = components_by_id(registry)
    if not isinstance(components, list) or not components or len(components) != len(set(components)):
        raise RegistryError("No components or duplicate deployment components")
    if not isinstance(files, dict):
        raise RegistryError("Missing deployment file map")
    compiled_dependency_files = set()
    for cid in components:
        if cid not in by_id or by_id[cid].get("deployment_component") != cid:
            raise RegistryError(f"Unregistered release component: {cid}")
        rel = str(files.get(cid, "")).replace("\\", "/")
        if not fnmatch.fnmatch(PurePosixPath(rel).name, by_id[cid]["script_pattern"]):
            raise RegistryError(f"{cid}: proposed script doesn't match registry")
        target = safe_path(root, rel, must_exist=True)
        py_compile.compile(str(target), doraise=True)
        # Compile declared dependencies transitively, not just the changed file.
        pending, visited = [cid], set()
        while pending:
            dependency = pending.pop()
            if dependency in visited:
                continue
            visited.add(dependency)
            pending.extend(by_id[dependency]["depends_on"])
            for source in by_id[dependency]["source_files"]:
                if source.endswith(".py") and source not in compiled_dependency_files:
                    py_compile.compile(str(safe_path(root, source, must_exist=True)), doraise=True)
                    compiled_dependency_files.add(source)
        if cid == "trader":
            code = target.read_text(encoding="utf-8", errors="replace")
            for marker in registry["safety"]["trader_source_markers"]:
                if marker not in code:
                    raise RegistryError(f"Trader missing paper-safety marker: {marker}")
    return registry


def change_impact(registry: dict, changed_paths: list[str]) -> dict:
    """Conservative code ownership + downstream verification plan.

    Ownership is a *test planning aid*, not permission to stop a dependent.
    Unowned Python source is called out rather than silently ignored.
    """
    by_id = components_by_id(registry)
    changed = {x.replace("\\", "/") for x in changed_paths}
    owners = set()
    uncovered = []
    for path in sorted(changed):
        matched = {cid for cid, c in by_id.items() if path in c["source_files"]}
        if path == ".env.config" or path in {"infrastructure/registry.json", "infrastructure/registry_contract.py"}:
            matched |= set(by_id)
        if (not matched and path.endswith(".py")
                and not PurePosixPath(path).name.startswith("test_")
                and not path.startswith(("tests/", "analysis/"))):
            uncovered.append(path)
        owners |= matched
    impacted = set(owners)
    while True:
        next_set = impacted | {
            cid for cid, comp in by_id.items()
            if any(other in impacted for other in comp["depends_on"])
        }
        if next_set == impacted:
            break
        impacted = next_set
    # Only code imports propagate mandatory reloads. Data consumers still
    # require verification, but not necessarily a destructive restart.
    must_reload = set(owners)
    while True:
        next_set = must_reload | {
            cid for cid, comp in by_id.items()
            if any(other in must_reload for other in comp.get("code_imports", []))
        }
        if next_set == must_reload:
            break
        must_reload = next_set
    return {
        "source_owners": sorted(owners),
        "verification_dependencies": sorted(impacted - owners),
        "deployable_owners": sorted(cid for cid in owners if by_id[cid].get("deployment_component")),
        "required_reload_components": sorted(cid for cid in must_reload if by_id[cid].get("deployment_component")),
        "non_deployable_reload_owners": sorted(cid for cid in must_reload if not by_id[cid].get("deployment_component")),
        "unmapped_python_files": uncovered,
    }


def enforce_changed_release_scope(registry: dict, changed_paths: list[str],
                                  requested_components: list[str]) -> dict:
    """Reject partial releases whose source dependencies require reload.

    Verification-only data consumers are NOT forced to restart.
    """
    impact = change_impact(registry, changed_paths)
    if impact["unmapped_python_files"]:
        raise RegistryError(
            "Unregistered Python sources in approved commit: "
            + ", ".join(impact["unmapped_python_files"][:8])
        )
    missing = sorted(set(impact["required_reload_components"]) - set(requested_components))
    if missing:
        raise RegistryError("Approved change requires additional component reload: " + ", ".join(missing))
    return impact


def enforce_commit_release_scope(root: Path, commit: str,
                                 requested_components: list[str]) -> dict:
    """Inspect exact approved Git commit without pulling or executing it."""
    import subprocess
    root = Path(root).resolve()
    registry = validate_registry(root, check_local_safety=True)
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{7,40}", commit):
        raise RegistryError("Approved commit must be a Git SHA")
    result = subprocess.run(
        ["git", "-C", str(root), "diff-tree", "--root", "--no-commit-id",
         "--name-only", "-r", commit],
        text=True, capture_output=True, timeout=15,
    )
    if result.returncode:
        raise RegistryError("Could not inspect approved Git commit file impact")
    return enforce_changed_release_scope(
        registry, result.stdout.splitlines(), requested_components
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only infrastructure registry validator")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--local-safety", action="store_true")
    parser.add_argument("--changed-path", action="append", default=[])
    args = parser.parse_args()
    data = validate_registry(args.root, check_local_safety=args.local_safety)
    result = {"project": data["project"], "schema_version": data["schema_version"],
              "components": len(data["components"]), "tasks": len(data["scheduled_tasks"]),
              "paper_only": True, "registry_valid": True}
    if args.changed_path:
        result["change_impact"] = change_impact(data, args.changed_path)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
