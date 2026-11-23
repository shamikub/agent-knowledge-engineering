"""CPU-only reference baselines for the six labs."""

import argparse
from collections import Counter
from datetime import datetime, timedelta
import json
import math
from pathlib import Path
import random

DATA = json.loads((Path(__file__).parent / "data/trip.json").read_text())


def capture():
    start = datetime.fromisoformat("2026-04-12T23:50")
    end = start.replace(hour=6, minute=40)
    if end < start:
        end += timedelta(days=1)
    edges = Counter(
        (first, second)
        for trace in DATA["events"].values()
        for first, second in zip(trace, trace[1:])
    )
    return {
        "arrival": end.isoformat(), "source": "D1",
        "directly_follows": [[*edge, count] for edge, count in sorted(edges.items())],
    }


def review(seed=7, budget=2):
    rows = DATA["labels"]
    randomized = random.Random(seed).sample(rows, budget)
    disagreement = sorted(rows, key=lambda row: row[3] == row[4])[:budget]
    return {
        name: {"reviewed": [row[0] for row in batch],
               "errors_found": sum(row[2] != row[3] for row in batch)}
        for name, batch in [("random", randomized), ("disagreement", disagreement)]
    }


def impact(delay=35):
    arrival = 20 * 60 + 35 + delay
    return {
        "hotel": {"status": "recheck" if arrival > 21 * 60 else "within_limit",
                  "source": "D8"},
        "locker": {"status": "unknown", "missing": "locker closing time"},
        "flexible_train": {"status": "flexible", "source": "D7"},
    }


def bm25(query, documents, k1=1.2, b=0.75):
    terms = [Counter(doc["text"].split()) for doc in documents]
    lengths = [sum(counts.values()) for counts in terms]
    average = sum(lengths) / len(documents)
    scores = [0.0] * len(documents)
    for token in set(query.split()):
        frequency = sum(token in counts for counts in terms)
        idf = math.log1p((len(documents) - frequency + 0.5) / (frequency + 0.5))
        for index, counts in enumerate(terms):
            term_count = counts[token]
            norm = k1 * (1 - b + b * lengths[index] / average)
            scores[index] += idf * term_count * (k1 + 1) / (term_count + norm)
    order = sorted(range(len(documents)), key=lambda index: (-scores[index], documents[index]["id"]))
    return [documents[index]["id"] for index in order]


def rrf(rankings, constant=60):
    scores = Counter()
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] += 1 / (constant + rank)
    return sorted(scores, key=lambda doc_id: (-scores[doc_id], doc_id))


def retrieval(k=3, filter_obsolete=False):
    documents = [doc for doc in DATA["documents"]
                 if not (filter_obsolete and doc.get("obsolete"))]
    rows = []
    for question in DATA["questions"]:
        top = bm25(question["query"], documents)[:k]
        gold = set(question["evidence"])
        hits = gold.intersection(top)
        dcg = sum(1 / math.log2(rank + 1) for rank, item in enumerate(top, 1) if item in gold)
        ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(k, len(gold)) + 1))
        rows.append({"id": question["id"], "top": top, "recall": len(hits) / len(gold),
                     "ndcg": dcg / ideal, "complete": gold <= set(top),
                     "obsolete_hit": "D4" in top})
    return rows


def evaluate():
    corpus = retrieval(k=2) + retrieval(k=3, filter_obsolete=True)
    oracle = [{"id": item["id"], "complete": True} for item in DATA["questions"]]
    documents = {doc["id"]: doc["text"] for doc in DATA["documents"]}
    queries = {question["id"]: set(question["query"].split()) for question in DATA["questions"]}
    baseline = []
    for item in corpus:
        found_terms = set(" ".join(documents[key] for key in item["top"]).split())
        query_terms = queries[item["id"]]
        score = len(query_terms & found_terms) / len(query_terms)
        baseline.append((score, item["complete"] and not item["obsolete_hit"]))
    curve = []
    for threshold in (0.0, 0.5, 0.75, 1.0):
        accepted = [correct for score, correct in baseline if score >= threshold]
        curve.append({"threshold": threshold, "coverage": len(accepted) / len(baseline),
                      "risk": accepted.count(False) / len(accepted) if accepted else None})
    return {"retrieved": corpus, "oracle": oracle, "toy_evidence_curve": curve}


class SimulatedBooking:
    def __init__(self):
        self.actions = {}

    def change_dinner(self, guests, approved, key):
        if not approved:
            return "needs_approval"
        if key in self.actions:
            return "already_applied" if self.actions[key] == guests else "key_conflict"
        if guests not in (2, 3):
            return "invalid_guest_count"
        self.actions[key] = guests
        return "applied"


def capstone(arrival_day=6, arrival_hour=10, other_guests=2):
    booking = SimulatedBooking()
    return {
        "dinner": {"decision": "review_party_size" if arrival_day > 5 or arrival_hour >= 19 else "keep", "sources": ["D9", "D12"]},
        "hotel": {"decision": "keep" if other_guests else "review_checkin", "sources": ["D10", "D12"]},
        "ticket": {"decision": "traveler_C_misses_start" if (arrival_day, arrival_hour) >= (6, 9) else "check_transfer_time", "sources": ["D11", "D12"]},
        "dry_run": [booking.change_dinner(2, False, "trip-dinner"),
                    booking.change_dinner(2, True, "trip-dinner"),
                    booking.change_dinner(2, True, "trip-dinner")],
        "simulated_writes": len(booking.actions),
    }


LABS = {
    "01": capture, "02": review, "03": impact,
    "04": retrieval, "05": evaluate, "06": capstone,
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("lab", choices=LABS)
    parser.add_argument("--k", type=int, choices=range(1, 13), default=3)
    parser.add_argument("--filter-obsolete", action="store_true")
    args = parser.parse_args()
    result = retrieval(args.k, args.filter_obsolete) if args.lab == "04" else LABS[args.lab]()
    print(json.dumps(result, ensure_ascii=False, indent=2))
