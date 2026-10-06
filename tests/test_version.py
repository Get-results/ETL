from pathlib import Path

from src.version import APP_VERSION, SHA_LENGTH, UNKNOWN_SHA, build_identity, resolve_git_sha

SHA = "9077b9305a184ab4272fc19e35745f1c088e46dd"
SHORT_SHA = SHA[:SHA_LENGTH]


def _init_git_dir(root: Path, head: str) -> Path:
    git_dir = root / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text(head)
    return git_dir


class TestResolveGitSha:
    """Ordre de résolution : variable d'env > fichier GIT_SHA > dépôt git > unknown."""

    def test_env_has_priority_over_file(self, tmp_path):
        (tmp_path / "GIT_SHA").write_text("deadbeefdeadbeef\n")
        assert resolve_git_sha(tmp_path, {"APP_GIT_SHA": SHA}) == SHORT_SHA

    def test_file_written_by_dockerfile(self, tmp_path):
        (tmp_path / "GIT_SHA").write_text(f"{SHA}\n")
        assert resolve_git_sha(tmp_path, {}) == SHORT_SHA

    def test_detached_head(self, tmp_path):
        _init_git_dir(tmp_path, f"{SHA}\n")
        assert resolve_git_sha(tmp_path, {}) == SHORT_SHA

    def test_branch_with_loose_ref(self, tmp_path):
        git_dir = _init_git_dir(tmp_path, "ref: refs/heads/master\n")
        (git_dir / "refs" / "heads").mkdir(parents=True)
        (git_dir / "refs" / "heads" / "master").write_text(f"{SHA}\n")
        assert resolve_git_sha(tmp_path, {}) == SHORT_SHA

    def test_branch_with_packed_ref(self, tmp_path):
        git_dir = _init_git_dir(tmp_path, "ref: refs/heads/master\n")
        (git_dir / "packed-refs").write_text(
            "# pack-refs with: peeled fully-peeled sorted\n"
            f"0000000000000000000000000000000000000000 refs/heads/other\n"
            f"{SHA} refs/heads/master\n"
        )
        assert resolve_git_sha(tmp_path, {}) == SHORT_SHA

    def test_worktree_reads_refs_from_main_repo(self, tmp_path):
        main_git = tmp_path / "main" / ".git"
        worktree_git = main_git / "worktrees" / "wt"
        worktree_git.mkdir(parents=True)
        (main_git / "refs" / "heads").mkdir(parents=True)
        (main_git / "refs" / "heads" / "feat").write_text(f"{SHA}\n")
        (worktree_git / "HEAD").write_text("ref: refs/heads/feat\n")
        (worktree_git / "commondir").write_text("../..\n")

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / ".git").write_text(f"gitdir: {worktree_git}\n")

        assert resolve_git_sha(worktree, {}) == SHORT_SHA

    def test_unknown_without_any_source(self, tmp_path):
        assert resolve_git_sha(tmp_path, {}) == UNKNOWN_SHA

    def test_blank_values_are_ignored(self, tmp_path):
        (tmp_path / "GIT_SHA").write_text("\n")
        assert resolve_git_sha(tmp_path, {"APP_GIT_SHA": "  "}) == UNKNOWN_SHA


class TestBuildIdentity:
    def test_contains_version_and_sha(self):
        identity = build_identity()
        assert identity.startswith(f"v{APP_VERSION} (")
        assert identity.endswith(")")


class TestHealthEndpoint:
    def test_health_exposes_version_and_sha(self):
        from scraping_scheduler import app

        with app.test_client() as client:
            body = client.get("/health").get_json()

        assert body["status"] == "ok"
        assert body["version"] == APP_VERSION
        assert body["git_sha"]
