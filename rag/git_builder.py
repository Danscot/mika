"""
git_builder.py
--------------
Clone/pull a GitHub repo and collect its source files as text.
The actual FAISS indexing is handled by services.py (_build_or_append).
"""

import os
import logging
import git

logger = logging.getLogger(__name__)


class GitHubBuilder:

    DEFAULT_EXTS = [".py", ".js", ".ts", ".md", ".txt", ".java", ".cpp",
                    ".c", ".h", ".cs", ".rb", ".go", ".rs", ".json", ".yaml",
                    ".yml", ".toml", ".sh", ".html", ".css"]

    def __init__(self, repo_url: str, repo_dir: str = "repo_cache"):
        self.repo_url = repo_url
        self.repo_dir = repo_dir
        # NOTE: Embedder/Storage intentionally NOT instantiated here.
        # All indexing is now handled by services._build_or_append.

    def clone_repo(self):
        """Clone the repo if it doesn't exist locally, otherwise pull latest."""
        if not os.path.exists(self.repo_dir):
            logger.info("Cloning %s → %s", self.repo_url, self.repo_dir)
            git.Repo.clone_from(self.repo_url, self.repo_dir)
        else:
            logger.info("Repo cache exists at %s — pulling latest", self.repo_dir)
            try:
                repo = git.Repo(self.repo_dir)
                repo.remotes.origin.pull()
            except Exception as exc:
                logger.warning("Git pull failed (%s) — continuing with cached copy", exc)

    def load_files(self, exts: list[str] | None = None) -> list[str]:
        """
        Walk self.repo_dir and return a list of file-content strings for
        every file whose extension is in `exts`.

        Each entry is formatted as:
            "FILE: relative/path/to/file.py\\n<file content>"

        Returns an empty list if no matching files are found (caller should
        check and raise a meaningful error rather than silently producing an
        empty index).
        """
        if not os.path.isdir(self.repo_dir):
            raise FileNotFoundError(
                f"Repo directory '{self.repo_dir}' does not exist. "
                "Make sure clone_repo() was called first."
            )

        target_exts = set(exts or self.DEFAULT_EXTS)
        docs: list[str] = []
        skipped = 0

        for root, dirs, files in os.walk(self.repo_dir):
            # Skip hidden dirs (.git, .github, __pycache__, node_modules, …)
            dirs[:] = [
                d for d in dirs
                if not d.startswith(".") and d not in ("node_modules", "__pycache__", "dist", "build")
            ]

            for filename in files:
                _, ext = os.path.splitext(filename)
                if ext.lower() not in target_exts:
                    continue

                abs_path = os.path.join(root, filename)
                rel_path = os.path.relpath(abs_path, self.repo_dir)

                try:
                    with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    if not content.strip():
                        skipped += 1
                        continue

                    docs.append(f"FILE: {rel_path}\n{content}")

                except Exception as exc:
                    logger.warning("Could not read %s: %s", rel_path, exc)

        logger.info(
            "load_files: found %d non-empty files (skipped %d empty), extensions=%s, dir=%s",
            len(docs), skipped, sorted(target_exts), self.repo_dir,
        )

        return docs
