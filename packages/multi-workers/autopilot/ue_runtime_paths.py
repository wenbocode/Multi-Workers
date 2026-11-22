"""Literal Windows UE runtime write faces used by Dual workspaces."""
from __future__ import annotations

import os
import re
import stat
from pathlib import Path


def external_write_root(absolute: str) -> str | None:
    # A host sandbox can redirect LOCALAPPDATA away from the UE user profile.
    local_roots = [os.environ.get("LOCALAPPDATA")]
    if profile := os.environ.get("USERPROFILE"):
        local_roots.append(os.path.join(profile, "AppData", "Local"))
    for local in local_roots:
        if not local or not Path(local).is_absolute():
            continue
        local_dir = Path(local).as_posix()
        ubt = f"{local_dir}/UnrealBuildTool"
        if absolute.lower() == ubt.lower() or absolute.lower().startswith(ubt.lower() + "/"):
            return local_dir
        ue = (Path(local) / "UnrealEngine").as_posix()
        prefix = ue + "/"
        if not absolute.lower().startswith(prefix.lower()):
            continue
        parts = absolute[len(prefix):].split("/")
        if len(parts) >= 2 and (
            (re.fullmatch(r"[0-9]+\.[0-9]+", parts[0])
             and re.fullmatch(r"Saved(?:_[A-Za-z0-9_-]+)?", parts[1], re.IGNORECASE | re.ASCII))
            or (parts[0].lower() == "common" and parts[1].lower() == "deriveddatacache")
        ):
            return ue

    if (data := os.environ.get("ProgramData")) and Path(data).is_absolute():
        epic = Path(data) / "Epic"
        marker = epic / "NotAllowedUnattendedBugReports"
        if absolute.lower() == marker.as_posix().lower():
            try:
                info = marker.lstat()
                if stat.S_ISREG(info.st_mode) and info.st_size == 0:
                    return epic.as_posix()
            except OSError:
                pass
    return None


def is_engine_project_output(engine: str, absolute: str) -> bool:
    """Recognize build output folders belonging to an existing UE project."""
    root = Path(engine) / "Engine"
    try:
        parts = Path(absolute).relative_to(root).parts
    except ValueError:
        return False
    if ".." in parts:
        return False
    for index, part in enumerate(parts):
        if index >= 2 and parts[0].lower() == "plugins" and part.lower() in ("binaries", "intermediate", "saved"):
            extension = ".uplugin"
        elif index >= 3 and tuple(p.lower() for p in parts[:2]) == ("source", "programs") and part.lower() in ("obj", "bin", "uatobj", "uatbin"):
            extension = ".csproj"
        else:
            continue
        if any(not re.fullmatch(r"[A-Za-z0-9_. -]+", name) for name in parts[:index]):
            return False
        project = root.joinpath(*parts[:index])
        try:
            if any(item.suffix.lower() == extension and stat.S_ISREG(item.lstat().st_mode) for item in project.iterdir()):
                return True
        except OSError:
            continue
    return False
