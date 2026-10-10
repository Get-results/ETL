"""
Identité du build : version applicative et commit git.

Permet de vérifier dans les logs (et sur /health) quelle version du scraper
tourne réellement en prod, plutôt que celle qu'on croit avoir déployée.
"""
import os
from pathlib import Path
from typing import Mapping, Optional

APP_VERSION = "1.3.1"

UNKNOWN_SHA = "unknown"
SHA_LENGTH = 12

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def resolve_git_sha(root: Path = PROJECT_ROOT, env: Optional[Mapping[str, str]] = None) -> str:
    """
    Cherche le SHA du commit, dans l'ordre :
    1. variable d'environnement APP_GIT_SHA (CI, `docker run -e`) ;
    2. fichier GIT_SHA à la racine, écrit par le Dockerfile au build ;
    3. dépôt git local (exécution en dev) ;
    sinon "unknown".
    """
    env = os.environ if env is None else env
    candidates = (
        env.get("APP_GIT_SHA", ""),
        _read_text(root / "GIT_SHA"),
        _sha_from_git_dir(root / ".git"),
    )
    for sha in candidates:
        sha = sha.strip()
        if sha:
            return sha[:SHA_LENGTH]
    return UNKNOWN_SHA


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _sha_from_git_dir(dot_git: Path) -> str:
    """Lit HEAD sans invoquer git. Gère un dépôt classique et un worktree (`.git` fichier)."""
    git_dir = dot_git
    if dot_git.is_file():  # worktree : ".git" contient "gitdir: <chemin>"
        pointer = _read_text(dot_git).strip()
        if not pointer.startswith("gitdir:"):
            return ""
        git_dir = (dot_git.parent / pointer[len("gitdir:"):].strip()).resolve()

    head = _read_text(git_dir / "HEAD").strip()
    if not head:
        return ""
    if not head.startswith("ref:"):
        return head  # HEAD détaché : le SHA est directement dans le fichier

    ref = head[len("ref:"):].strip()
    # Dans un worktree, les refs vivent dans le dépôt principal (fichier "commondir").
    common = _read_text(git_dir / "commondir").strip()
    search_dirs = [git_dir] + ([(git_dir / common).resolve()] if common else [])
    for directory in search_dirs:
        loose = _read_text(directory / ref).strip()
        if loose:
            return loose
        for line in _read_text(directory / "packed-refs").splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == ref:
                return parts[0]
    return ""


GIT_SHA = resolve_git_sha()


def build_identity() -> str:
    """Ex. `v1.2.0 (9077b9305a18)` — à logger au démarrage de chaque point d'entrée."""
    return f"v{APP_VERSION} ({GIT_SHA})"
