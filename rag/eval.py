"""
eval.py
-------
Minimal evaluation loop for the RAG pipeline.

Runs a set of questions against the pipeline and scores each answer.
Gives you a number you can compare across pipeline changes — so you know
whether a new chunker / threshold / reranker actually helps or hurts.

Usage:
    # Run with the default eval set:
    python eval.py --index your_index_name

    # Run with your own questions file (JSON):
    python eval.py --index your_index_name --questions my_eval.json

    # Skip the LLM call (measure retrieval quality only, much faster):
    python eval.py --index your_index_name --retrieval-only

Questions file format (JSON):
    [
        {
            "question": "What is the return policy?",
            "expected": "30 days",          // keyword(s) that must appear in answer
            "must_retrieve": "return"       // keyword that must appear in retrieved chunks
        },
        ...
    ]

Output:
    Retrieval recall  : how often the right chunk was found (0.0 – 1.0)
    Answer recall     : how often the answer contained the expected keyword
    Avg FAISS distance: lower is better — tells you if threshold needs tuning
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.WARNING,    # suppress INFO noise during eval
)
logger = logging.getLogger("eval")

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mika_project.settings")

import django
sys.path.insert(0, str(BASE_DIR))
django.setup()

from embedder import Embedder
from reranker import Reranker
from searcher import Search


# ── Default eval set (replace/extend with your own domain questions) ──────────

DEFAULT_QUESTIONS = [
    {
        "question": "What is this about?",
        "expected": "",
        "must_retrieve": "",
    },
    {
        "question": "Can you summarise the main points?",
        "expected": "",
        "must_retrieve": "",
    },
]


# ─────────────────────────────────────────────────────────────────────────────

def run_eval(index_name: str, questions: list[dict],
             retrieval_only: bool = False, top_k: int = 5):

    from django.conf import settings
    index_dir   = Path(settings.INDEX_DIR)
    index_path  = str(index_dir / f"{index_name}.faiss")
    chunks_path = str(index_dir / f"{index_name}.pkl")

    if not Path(index_path).exists():
        print(f"[ERROR] Index '{index_name}' not found at {index_path}")
        sys.exit(1)

    print(f"\n{'═'*60}")
    print(f"  Mika RAG Evaluation")
    print(f"  Index  : {index_name}")
    print(f"  Mode   : {'retrieval only' if retrieval_only else 'full pipeline'}")
    print(f"  Questions: {len(questions)}")
    print(f"{'═'*60}\n")

    embedder = Embedder()
    reranker = Reranker()
    search   = Search(
        index_path=index_path,
        chunks_path=chunks_path,
        embedder=embedder,
        reranker=reranker,
    )

    retrieval_hits  = 0
    answer_hits     = 0
    total_latency   = 0.0
    best_distances  = []

    for i, q in enumerate(questions, 1):
        question      = q["question"]
        expected      = q.get("expected", "").lower()
        must_retrieve = q.get("must_retrieve", "").lower()

        print(f"[{i}/{len(questions)}] {question}")
        t0 = time.time()

        # Stage 1: retrieval
        vec = embedder.embedder.encode([question], convert_to_numpy=True)
        from django.conf import settings as _s
        import faiss as _faiss
        idx = _faiss.read_index(index_path)
        dists, idxs = idx.search(vec, 20)
        best_dist = float(dists[0][0]) if len(dists[0]) else 9.9
        best_distances.append(best_dist)

        context = search.query(question, top_k=top_k)

        # Retrieval recall
        if must_retrieve:
            hit = must_retrieve in context.lower()
            retrieval_hits += int(hit)
            marker = "✓" if hit else "✗"
            print(f"  Retrieval [{marker}]  best L2={best_dist:.3f}  keyword='{must_retrieve}'")
        else:
            print(f"  Retrieval      best L2={best_dist:.3f}")

        if retrieval_only:
            total_latency += time.time() - t0
            print()
            continue

        # Full pipeline: call Gemini
        from main_gemini import MainGemini
        session = MainGemini(user_id="__eval__", index_name=index_name)
        result  = session.query(question)
        answer  = (result.get("text") or "").lower()

        if expected:
            hit = expected in answer
            answer_hits += int(hit)
            marker = "✓" if hit else "✗"
            print(f"  Answer  [{marker}]  expected='{expected}'")
            if not hit:
                print(f"  Answer preview: {answer[:120]}…")

        total_latency += time.time() - t0
        print()

    # ── Summary ───────────────────────────────────────────────────────────────
    n = len(questions)
    has_retrieval_targets = sum(1 for q in questions if q.get("must_retrieve"))
    has_answer_targets    = sum(1 for q in questions if q.get("expected"))

    print(f"{'─'*60}")
    print(f"  Results")
    print(f"{'─'*60}")
    if has_retrieval_targets:
        recall = retrieval_hits / has_retrieval_targets
        print(f"  Retrieval recall : {retrieval_hits}/{has_retrieval_targets}  ({recall:.0%})")
    if has_answer_targets and not retrieval_only:
        recall = answer_hits / has_answer_targets
        print(f"  Answer recall    : {answer_hits}/{has_answer_targets}  ({recall:.0%})")
    avg_dist = sum(best_distances) / len(best_distances) if best_distances else 0
    print(f"  Avg best L2 dist : {avg_dist:.3f}  (threshold={search.threshold})")
    print(f"  Avg latency      : {total_latency / n:.1f}s per question")
    print(f"{'═'*60}\n")

    return {
        "retrieval_recall": retrieval_hits / has_retrieval_targets if has_retrieval_targets else None,
        "answer_recall":    answer_hits    / has_answer_targets    if has_answer_targets    else None,
        "avg_best_l2":      avg_dist,
        "avg_latency_s":    total_latency / n,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Evaluate the Mika RAG pipeline")
    parser.add_argument("--index",          required=True, help="Index name (without .faiss)")
    parser.add_argument("--questions",      default=None,  help="Path to JSON questions file")
    parser.add_argument("--retrieval-only", action="store_true", help="Skip LLM, test retrieval only")
    parser.add_argument("--top-k",          type=int, default=5, help="Chunks to return after reranking")
    args = parser.parse_args()

    if args.questions:
        with open(args.questions) as f:
            questions = json.load(f)
    else:
        questions = DEFAULT_QUESTIONS
        print("[INFO] No --questions file provided. Using built-in placeholder questions.")
        print("[INFO] Create a JSON file with your domain questions for meaningful results.\n")

    run_eval(
        index_name=args.index,
        questions=questions,
        retrieval_only=args.retrieval_only,
        top_k=args.top_k,
    )


if __name__ == "__main__":
    main()
