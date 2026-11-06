"""
Measure how well search finds the right document for a fixed set of test questions
(evaluation/test_questions.json). Compares semantic-only search with hybrid search.

Usage:
    python evaluate_search.py           # results for each question + summary
    python evaluate_search.py --sweep   # summary for a range of MIN_SIMILARITY values

Metrics:
    Top-1    - the expected document was the first result
    Top-5    - the expected document was in the top 5 results
    MRR      - Mean Reciprocal Rank: 1 for 1st place, 0.5 for 2nd, 0.33 for 3rd ... 0 if missing
    No-match - for questions with no correct document, search correctly returned nothing
"""

import json
import sys
from pathlib import Path

from db import init_db
from search import search_documents, is_relevant, MIN_SIMILARITY, MAX_SEARCH_RESULTS

# Each test question has the text and the name of the document that should be found
# ("expected": null means no document answers it, so search should return nothing)
QUESTIONS_FILE = Path(__file__).parent / "evaluation" / "test_questions.json"
# The two search modes being compared
MODES = ["semantic", "hybrid"]


def run_searches(questions, mode):
    """Run every question once with no threshold, so thresholds can be applied afterwards."""
    return [search_documents(q["question"], mode=mode, limit=None, min_similarity=0) for q in questions]


def score(questions, all_results, min_similarity):
    """Calculate Top-1, Top-5, MRR and No-match for one search mode at one threshold."""
    top1 = top5 = rr_total = answerable = 0
    no_match_correct = unanswerable = 0
    ranks = []

    for question, results in zip(questions, all_results):
        # Apply the threshold the same way the app does, to see what the user would be shown
        shown = [r for r in results if is_relevant(r, min_similarity)][:MAX_SEARCH_RESULTS]
        names = [r["name"] for r in shown]

        # Unanswerable question: correct behaviour is to show nothing
        if question["expected"] is None:
            unanswerable += 1
            no_match_correct += not shown
            ranks.append("none" if not shown else f"{len(shown)} shown")
            continue

        # Answerable question: find where the expected document appeared (1 = first, None = missing)
        answerable += 1
        rank = names.index(question["expected"]) + 1 if question["expected"] in names else None
        top1 += rank == 1
        top5 += rank is not None
        rr_total += 1 / rank if rank else 0
        ranks.append(rank or "-")

    return {
        "top1": top1 / answerable,
        "top5": top5 / answerable,
        "mrr": rr_total / answerable,
        "no_match": no_match_correct / unanswerable if unanswerable else 1.0,
        "ranks": ranks,
    }


def print_summary(mode, s, min_similarity):
    """Print one line of results, e.g. 'hybrid  min_similarity=0.30  Top-1 90% ...'."""
    print(f"{mode:<9} min_similarity={min_similarity:.2f}  "
          f"Top-1 {s['top1']:.0%}  Top-5 {s['top5']:.0%}  MRR {s['mrr']:.2f}  No-match {s['no_match']:.0%}")


def main():
    init_db()
    questions = json.loads(QUESTIONS_FILE.read_text())
    # Search once per mode, then score the same results at different thresholds (much faster
    # than searching again for every threshold)
    results = {mode: run_searches(questions, mode) for mode in MODES}

    # --sweep: try several thresholds to choose the best MIN_SIMILARITY value
    if "--sweep" in sys.argv:
        for mode in MODES:
            for threshold in [0.0, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45]:
                print_summary(mode, score(questions, results[mode], threshold), threshold)
            print()
        return

    # Default: a table showing the rank of the expected document for each question, then a summary
    scores = {mode: score(questions, results[mode], MIN_SIMILARITY) for mode in MODES}
    print(f"{'Question':<70} {'Expected':<42} " + " ".join(f"{m:>9}" for m in MODES))
    for i, q in enumerate(questions):
        expected = q["expected"] or "(no answer)"
        print(f"{q['question'][:69]:<70} {expected[:41]:<42} "
              + " ".join(f"{str(scores[m]['ranks'][i]):>9}" for m in MODES))
    print()
    for mode in MODES:
        print_summary(mode, scores[mode], MIN_SIMILARITY)


if __name__ == "__main__":
    main()
