"""Read-only filesystem access for Jarvis tools.

Every operation is sandboxed to a list of allowed root directories. Roots
come from the JARVIS_ROOTS env var (comma-separated paths) and default to
~/Documents, ~/Downloads, ~/Desktop.

Path validation: the user-supplied path is expanded, made absolute, and
resolved (which follows symlinks). The resolved path must sit inside one
of the allowed roots — otherwise the operation is denied. This rejects
both `..` escapes and symlink jumps to outside the sandbox.
"""

from __future__ import annotations

import os
import platform
import subprocess
from datetime import datetime
from pathlib import Path

from .config import log


MAX_READ_BYTES = 200_000     # cap for read_file
MAX_RESULTS    = 60          # cap for list / search results

TEXT_EXTS = {
    ".txt", ".md", ".rst", ".log", ".csv", ".json", ".yaml", ".yml",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".scss",
    ".java", ".c", ".cpp", ".h", ".rb", ".go", ".rs", ".swift",
    ".sh", ".env", ".cfg", ".ini", ".toml", ".xml",
}


def _default_roots() -> list[Path]:
    home = Path.home()
    return [home / "Documents", home / "Downloads", home / "Desktop"]


def _load_roots() -> list[Path]:
    env = os.getenv("JARVIS_ROOTS", "").strip()
    if not env:
        return _default_roots()
    out: list[Path] = []
    for raw in env.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            out.append(Path(raw).expanduser().resolve())
        except OSError:
            pass
    return out or _default_roots()


class FilesystemBrain:
    def __init__(self) -> None:
        self.roots = [r for r in _load_roots() if r.exists() and r.is_dir()]
        log.info(f"Filesystem roots: {[str(r) for r in self.roots]}")

    # ── Path validation ────────────────────────────────────────────────
    def _inside_any_root(self, p: Path) -> bool:
        for root in self.roots:
            try:
                p.relative_to(root)
                return True
            except ValueError:
                continue
        return False

    def _resolve(self, raw: str) -> Path | None:
        if not raw:
            return None
        raw = raw.strip().strip("'\"")
        # "Documents", "Downloads", etc. → match against root basenames.
        for root in self.roots:
            if raw.lower() == root.name.lower():
                return root
        p = Path(raw).expanduser()
        if not p.is_absolute():
            # Try each root with `raw` appended; pick the first that exists.
            for root in self.roots:
                candidate = root / raw
                try:
                    resolved = candidate.resolve()
                except OSError:
                    continue
                if self._inside_any_root(resolved) and resolved.exists():
                    return resolved
            # Fall back to first root + raw (may not exist).
            if self.roots:
                p = self.roots[0] / raw
            else:
                return None
        try:
            resolved = p.resolve()
        except OSError:
            return None
        return resolved if self._inside_any_root(resolved) else None

    # ── Operations ─────────────────────────────────────────────────────
    def list_dir(self, path: str = "") -> str:
        if not path:
            return self._list_roots()
        target = self._resolve(path)
        if target is None or not target.exists():
            return f"Path not found or not allowed: {path}"
        if not target.is_dir():
            return f"{path} is not a directory."

        entries: list[str] = []
        for child in sorted(
            target.iterdir(),
            key=lambda c: (not c.is_dir(), c.name.lower()),
        ):
            if child.name.startswith("."):
                continue
            kind = "dir " if child.is_dir() else "file"
            try:
                size_s = self._human_size(child.stat().st_size) if child.is_file() else "    "
            except OSError:
                size_s = "    "
            entries.append(f"{kind}  {size_s:>8}  {child.name}")
            if len(entries) >= MAX_RESULTS:
                entries.append(f"... (showing first {MAX_RESULTS})")
                break

        if not entries:
            return f"{target} is empty."
        return f"Contents of {target}:\n" + "\n".join(entries)

    def _list_roots(self) -> str:
        if not self.roots:
            return "No roots configured."
        return "Available roots:\n" + "\n".join(f"- {r}" for r in self.roots)

    def search_files(self, query: str, root: str = "") -> str:
        if not query:
            return "Empty query."
        roots = [self._resolve(root)] if root else list(self.roots)
        roots = [r for r in roots if r is not None and r.is_dir()]
        if not roots:
            return "No valid root to search."

        q = query.lower()
        hits: list[Path] = []
        for r in roots:
            for p in r.rglob("*"):
                if p.is_dir():
                    continue
                rel_parts = p.relative_to(r).parts
                if any(part.startswith(".") for part in rel_parts):
                    continue
                if q in p.name.lower():
                    hits.append(p)
                    if len(hits) >= MAX_RESULTS:
                        break
            if len(hits) >= MAX_RESULTS:
                break

        if not hits:
            return f"No files matching '{query}'."
        return f"Found {len(hits)} file(s):\n" + "\n".join(str(h) for h in hits)

    def search_content(self, query: str, root: str = "") -> str:
        if not query:
            return "Empty query."
        roots = [self._resolve(root)] if root else list(self.roots)
        roots = [r for r in roots if r is not None and r.is_dir()]
        if not roots:
            return "No valid root to search."

        q = query.lower()
        hits: list[str] = []
        for r in roots:
            for p in r.rglob("*"):
                if p.is_dir():
                    continue
                rel_parts = p.relative_to(r).parts
                if any(part.startswith(".") for part in rel_parts):
                    continue
                if p.suffix.lower() not in TEXT_EXTS:
                    continue
                try:
                    if p.stat().st_size > MAX_READ_BYTES:
                        continue
                    text = p.read_text(errors="ignore")
                except OSError:
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if q in line.lower():
                        snippet = line.strip()[:120]
                        hits.append(f"{p}:{i}: {snippet}")
                        break
                if len(hits) >= MAX_RESULTS:
                    break
            if len(hits) >= MAX_RESULTS:
                break

        if not hits:
            return f"No matches for '{query}' in text files."
        return f"Found {len(hits)} match(es):\n" + "\n".join(hits)

    def read_file(self, path: str) -> str:
        target = self._resolve(path)
        if target is None or not target.exists():
            return f"File not found or not allowed: {path}"
        if not target.is_file():
            return f"{path} is not a regular file."
        try:
            size = target.stat().st_size
            if size > MAX_READ_BYTES:
                with open(target, "r", errors="ignore") as f:
                    head = f.read(MAX_READ_BYTES)
                return f"[truncated to first {MAX_READ_BYTES} bytes]\n{head}"
            return target.read_text(errors="ignore")
        except OSError as e:
            return f"Could not read {path}: {e}"

    def file_info(self, path: str) -> str:
        target = self._resolve(path)
        if target is None or not target.exists():
            return f"Not found or not allowed: {path}"
        try:
            st = target.stat()
        except OSError as e:
            return f"Could not stat {path}: {e}"
        kind = "directory" if target.is_dir() else "file"
        size = self._human_size(st.st_size) if target.is_file() else "—"
        mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
        return f"{target}\nKind: {kind}\nSize: {size}\nModified: {mtime}"

    def open_path(self, path: str) -> str:
        target = self._resolve(path)
        if target is None or not target.exists():
            return f"Not found or not allowed: {path}"
        system = platform.system()
        try:
            if system == "Darwin":
                subprocess.Popen(["open", str(target)])
            elif system == "Windows":
                os.startfile(str(target))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(target)])
            return f"Opened {target.name}."
        except Exception as e:
            return f"Could not open: {e}"

    # ── Helpers ────────────────────────────────────────────────────────
    @staticmethod
    def _human_size(n: int) -> str:
        size = float(n)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.0f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"
