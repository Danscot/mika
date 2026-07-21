"""
services.py
-----------
Thin wrappers around the original RAG modules (builder.py, git_builder.py, etc.).
All paths are resolved from Django settings so the rest of the app stays clean.

The RAG_DIR setting must point at the folder containing your existing scripts:
  builder.py, git_builder.py, chunker.py, embedder.py, indexer.py,
  crawler.py, storage.py

INDEX_DIR is where Django saves finished .faiss + .pkl pairs.
UPLOAD_DIR is a scratch folder for incoming PDF uploads.
"""

import sys
import os
import logging
import uuid
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


def _ensure_rag_on_path():
    """Add RAG_DIR to sys.path so we can import the original scripts."""
    rag = str(settings.RAG_DIR)
    if rag not in sys.path:
        sys.path.insert(0, rag)


# ── helpers ───────────────────────────────────────────────────────────────────

def _index_paths(index_name: str):
    """Return (faiss_path, pkl_path) for a given index name."""
    base = settings.INDEX_DIR / index_name
    return str(base) + ".faiss", str(base) + ".pkl"


def list_indexes():
    """Return a list of existing index names (stems of .faiss files)."""
    return sorted(
        p.stem for p in settings.INDEX_DIR.glob("*.faiss")
    )


# ── ingestion workers ─────────────────────────────────────────────────────────

def ingest_url(url: str, index_name: str, append: bool) -> dict:
    """
    Crawl a website with Firecrawl and build/update a FAISS index.

    Returns a dict with keys: chunks, vectors, index_name
    """
    _ensure_rag_on_path()
    from builder import Builder  # noqa: PLC0415

    index_path, chunks_path = _index_paths(index_name)

    if append and Path(index_path).exists():
        # Load existing chunks, crawl new ones, merge manually
        import faiss, pickle
        from chunker import Chunker
        from embedder import Embedder
        from indexer import Indexer
        from storage import Storage
        from crawler import Crawler

        crawler  = Crawler()
        chunker  = Chunker()
        embedder = Embedder()
        storage  = Storage()

        logger.info("Crawling %s …", url)
        docs = crawler.crawler_job(url)
        new_chunks = chunker.chunk_docs(docs)
        new_embeddings = embedder.embed(new_chunks)

        old_index = faiss.read_index(index_path)
        with open(chunks_path, "rb") as f:
            old_chunks = pickle.load(f)

        indexer = Indexer(old_index.d)
        indexer.index = old_index
        merged_index = indexer.append_to_index(new_embeddings)
        merged_chunks = old_chunks + new_chunks

        storage.save_index(merged_index, index_path)
        storage.save_chunks(merged_chunks, chunks_path)

        return {
            "chunks":     len(merged_chunks),
            "vectors":    merged_index.ntotal,
            "index_name": index_name,
        }

    # New index
    builder = Builder()
    builder.build_base(url, index_path=index_path, chunks_path=chunks_path)

    import faiss, pickle
    idx = faiss.read_index(index_path)
    with open(chunks_path, "rb") as f:
        chunks = pickle.load(f)

    return {
        "chunks":     len(chunks),
        "vectors":    idx.ntotal,
        "index_name": index_name,
    }


def ingest_github(repo_url: str, index_name: str, append: bool,
                  extensions: list[str] | None = None) -> dict:
    """
    Clone/pull a GitHub repo and build/update a FAISS index.
    """
    _ensure_rag_on_path()
    from git_builder import GitHubBuilder  # noqa: PLC0415

    index_path, chunks_path = _index_paths(index_name)

    # Use a stable cache dir per repo (avoid re-cloning on every run)
    repo_slug = repo_url.rstrip("/").split("/")[-1]
    repo_dir  = str(settings.INDEX_DIR / f"_repo_{repo_slug}")

    builder = GitHubBuilder(repo_url=repo_url, repo_dir=repo_dir)

    # Patch file extensions if provided
    if extensions:
        original_load = builder.load_files
        builder.load_files = lambda: original_load(exts=extensions)

    builder.build_base(
        index_path=index_path,
        chunks_path=chunks_path,
        append=append,
    )

    import faiss, pickle
    idx = faiss.read_index(index_path)
    with open(chunks_path, "rb") as f:
        chunks = pickle.load(f)

    return {
        "chunks":     len(chunks),
        "vectors":    idx.ntotal,
        "index_name": index_name,
    }


def ingest_pdf(pdf_path: str, index_name: str, append: bool) -> dict:
    """
    Extract text from a PDF, chunk it, embed it, and build/update a FAISS index.

    Uses PyMuPDF (fitz) for text extraction — install with:
        pip install pymupdf
    """
    _ensure_rag_on_path()
    import fitz  # PyMuPDF
    import faiss, pickle
    from chunker  import Chunker
    from embedder import Embedder
    from indexer  import Indexer
    from storage  import Storage

    logger.info("Extracting text from PDF: %s", pdf_path)
    doc  = fitz.open(pdf_path)
    text = "\n".join(page.get_text() for page in doc)
    doc.close()

    chunker  = Chunker()
    embedder = Embedder()
    storage  = Storage()

    new_chunks     = chunker.chunk_text(text)
    new_chunks     = [c.strip() for c in new_chunks if c.strip()]
    new_embeddings = embedder.embed(new_chunks)

    index_path, chunks_path = _index_paths(index_name)

    if append and Path(index_path).exists():
        old_index = faiss.read_index(index_path)
        with open(chunks_path, "rb") as f:
            old_chunks = pickle.load(f)

        indexer = Indexer(old_index.d)
        indexer.index = old_index
        merged_index  = indexer.append_to_index(new_embeddings)
        merged_chunks = old_chunks + new_chunks
    else:
        dim     = new_embeddings.shape[1]
        indexer = Indexer(dim)
        merged_index  = indexer.build_index(new_embeddings)
        merged_chunks = new_chunks

    storage.save_index(merged_index, index_path)
    storage.save_chunks(merged_chunks, chunks_path)

    # Clean up temp upload
    try:
        os.remove(pdf_path)
    except OSError:
        pass

    return {
        "chunks":     len(merged_chunks),
        "vectors":    merged_index.ntotal,
        "index_name": index_name,
    }
