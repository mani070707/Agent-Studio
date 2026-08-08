import math


def ranking_metrics(retrieved: list[str], relevant: list[str]) -> dict[str, float | int]:
    """Binary-relevance metrics over stable document or chunk identifiers."""
    relevant_set = set(relevant)
    if not relevant_set:
        return {}
    hits = [1 if item in relevant_set else 0 for item in retrieved]
    found = len(relevant_set.intersection(retrieved))
    recall = found / len(relevant_set)
    precision = sum(hits) / len(retrieved) if retrieved else 0.0
    first = next((index for index, hit in enumerate(hits, 1) if hit), None)
    dcg = sum(hit / math.log2(index + 1) for index, hit in enumerate(hits, 1))
    ideal_hits = min(len(relevant_set), len(retrieved))
    ideal = sum(1 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    return {"recall": recall, "precision": precision, "mrr": 1 / first if first else 0.0,
            "ndcg": dcg / ideal if ideal else 0.0, "relevant_found": found}


def output_metrics(actual: dict | None, expected: dict, fields: list[str]) -> tuple[float, list[dict]]:
    compared = fields or list(expected)
    mismatches = [{"field": field, "expected": expected.get(field),
                   "actual": (actual or {}).get(field)} for field in compared
                  if (actual or {}).get(field) != expected.get(field)]
    return (1.0 if not mismatches else 0.0), mismatches


def citation_metrics(citations: list[dict], retrieved: list[dict], expected_documents: list[str]) -> dict[str, float | int]:
    valid = {item.get("source_id") for item in retrieved}
    cited = [item.get("source_id") for item in citations]
    invented = sum(1 for source_id in cited if source_id not in valid)
    precision = (len(cited) - invented) / len(cited) if cited else (1.0 if not expected_documents else 0.0)
    cited_documents = {item.get("document_id") for item in citations if item.get("source_id") in valid}
    recall = (len(cited_documents.intersection(expected_documents)) / len(set(expected_documents))
              if expected_documents else 1.0)
    return {"citation_validity": 1.0 if invented == 0 else 0.0, "citation_precision": precision,
            "citation_recall": recall, "invented_source_count": invented}
