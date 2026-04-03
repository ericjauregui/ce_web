from __future__ import annotations

import json
import math
import re
from threading import Lock
from dataclasses import dataclass
from collections import defaultdict, OrderedDict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
import unicodedata

from domains.file_cache import load_json_cached


_products_cache_lock = Lock()
_products_cache: dict[str, tuple[int, int, list[dict[str, Any]]]] = {}
_search_index_cache_lock = Lock()
_search_index_cache: dict[int, "SearchIndex"] = {}
_search_results_cache_lock = Lock()
_search_results_cache: "OrderedDict[tuple[int, str], list[dict[str, Any]]]" = OrderedDict()
_search_language_map_lock = Lock()
_search_language_map: dict[str, set[str]] | None = None
_search_language_map_path = Path(__file__).resolve().parent.parent / "catalog" / "search_language_map.json"
_search_normalizer = re.compile(r"[^a-z0-9]+")
_search_vowels = frozenset("aeiou")
_search_index_field_weights: dict[str, float] = {
    "code": 7.0,
    "name": 6.0,
    "aliases": 5.5,
    "tags": 4.5,
    "collection": 7.5,
    "description": 1.0,
}
_search_relation_fields = frozenset({"name", "aliases", "tags", "collection"})
_search_min_token_length = 2
_search_min_term_score = 1.8
_search_minimum_score = 3.0
_search_result_cache_size = 256


@dataclass
class SearchIndex:
    token_scores: list[dict[str, float]]
    token_signal: list[dict[str, float]]
    token_df: dict[str, int]
    token_idf: dict[str, float]
    postings: dict[str, list[int]]
    related_terms: dict[str, list[tuple[str, float]]]
    vocabulary: list[str]
    compact_fields: list[str]
    term_expansion_cache: dict[tuple[str, bool], dict[str, float]]


@dataclass
class Section:
    key: str
    title: str
    items: list[dict[str, Any]]


def normalize_product(product: dict[str, Any]) -> dict[str, Any]:
    code = (product.get("code") or "").strip()
    name = (product.get("name") or "").strip() or code
    description = (product.get("description") or "").strip()
    collection = (product.get("collection") or "other").strip() or "other"
    image = (product.get("image") or "").strip()
    tags = product.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    aliases = product.get("aliases") or []
    if not isinstance(aliases, list):
        aliases = []

    output = dict(product)
    output.update(
        {
            "id": code.lower(),
            "code": code,
            "name": name,
            "description": description,
            "collection": collection,
            "image": image,
            "tags": tags,
            "aliases": aliases,
        }
    )
    return output


def load_products(catalog_path: Path) -> list[dict[str, Any]]:
    if not catalog_path.exists():
        return []

    resolved = str(catalog_path.resolve())
    stat = catalog_path.stat()
    stamp = (stat.st_mtime_ns, stat.st_size)

    with _products_cache_lock:
        cached = _products_cache.get(resolved)
        if cached and cached[0] == stamp[0] and cached[1] == stamp[1]:
            return cached[2]

    raw = load_json_cached(catalog_path, [])
    normalized = [normalize_product(item) for item in (raw or [])]

    # Warm the search assets once per catalog snapshot so first customer queries
    # do not pay the full index + language map build penalty.
    build_search_index(normalized)
    load_search_language_map()

    with _products_cache_lock:
        _products_cache[resolved] = (stamp[0], stamp[1], normalized)

    return normalized


def products_by_code(products: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_code: dict[str, dict[str, Any]] = {}
    for product in products:
        code = product.get("code")
        if isinstance(code, str) and code:
            by_code[code] = product
    return by_code


def find_product_by_code(products: list[dict[str, Any]], code: str) -> dict[str, Any] | None:
    target = (code or "").strip().lower()
    if not target:
        return None

    for product in products:
        product_code = str(product.get("code") or "").strip().lower()
        if product_code == target:
            return product

    return None


def load_social(social_path: Path) -> dict[str, Any]:
    if social_path.exists():
        return load_json_cached(social_path, {})
    return {"tiktok": {"profile_url": ""}, "instagram": {"profile_url": "", "reels_url": ""}}


def load_collections_cfg(collections_path: Path) -> dict[str, Any]:
    if collections_path.exists():
        return load_json_cached(collections_path, {})
    return {"order": [], "labels": {}}


def load_search_language_map() -> dict[str, set[str]]:
    global _search_language_map

    with _search_language_map_lock:
        if _search_language_map is not None:
            return _search_language_map

        rows = load_json_cached(_search_language_map_path, {"equivalents": []})
        equivalent_groups = rows.get("equivalents") if isinstance(rows, dict) else []
        mapping: dict[str, set[str]] = defaultdict(set)

        for group in equivalent_groups or []:
            if not isinstance(group, list):
                continue
            normalized_group = {
                compact_search_text(term)
                for term in group
                if isinstance(term, str) and compact_search_text(term)
            }
            for term in normalized_group:
                mapping[term].update(item for item in normalized_group if item != term)

        _search_language_map = {key: set(value) for key, value in mapping.items()}
        return _search_language_map


def _ascii_search_text(value: Any) -> str:
    normalized_value = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    return normalized_value.encode("ascii", "ignore").decode("ascii")


def normalize_search_text(value: Any) -> str:
    ascii_value = _ascii_search_text(value)
    normalized_characters: list[str] = []
    for index, character in enumerate(ascii_value):
        if character.isalnum():
            normalized_characters.append(character)
            continue

        if character.isspace():
            normalized_characters.append(" ")
            continue

        previous_is_alnum = index > 0 and ascii_value[index - 1].isalnum()
        next_is_alnum = index + 1 < len(ascii_value) and ascii_value[index + 1].isalnum()
        if previous_is_alnum and next_is_alnum:
            continue

        normalized_characters.append(" ")

    return " ".join("".join(normalized_characters).split())


def compact_search_text(value: Any) -> str:
    ascii_value = _ascii_search_text(value)
    return _search_normalizer.sub("", ascii_value)


def tokenize_search_text(value: Any) -> list[str]:
    normalized = normalize_search_text(value)
    if not normalized:
        return []
    return [token for token in normalized.split() if len(token) >= _search_min_token_length]


def singularize_search_token(token: str) -> str:
    token = compact_search_text(token)
    if len(token) <= 3:
        return token
    if token.endswith("ies") and len(token) > 4:
        return f"{token[:-3]}y"
    if token.endswith("ces") and len(token) > 4:
        return f"{token[:-3]}z"
    if token.endswith("es") and len(token) > 4:
        return token[:-2]
    if token.endswith("s") and len(token) > 3:
        return token[:-1]
    return token


def expand_search_token(token: str) -> set[str]:
    normalized_token = compact_search_text(token)
    if not normalized_token or len(normalized_token) < _search_min_token_length:
        return set()

    forms = {normalized_token, singularize_search_token(normalized_token)}
    expanded = {item for item in forms if len(item) >= _search_min_token_length}

    language_map = load_search_language_map()
    for form in tuple(expanded):
        for related in language_map.get(form, set()):
            expanded.add(related)
            expanded.add(singularize_search_token(related))

    return {item for item in expanded if len(item) >= _search_min_token_length}


def consonant_skeleton(token: str) -> str:
    normalized_token = compact_search_text(token)
    return "".join(character for character in normalized_token if character not in _search_vowels)


def abbreviation_matches(query_token: str, candidate_token: str) -> bool:
    normalized_query = compact_search_text(query_token)
    normalized_candidate = compact_search_text(candidate_token)
    if len(normalized_query) < 3 or len(normalized_query) > 4 or len(normalized_candidate) < 5:
        return False
    if any(character in _search_vowels for character in normalized_query):
        return False

    query_skeleton = consonant_skeleton(normalized_query)
    candidate_skeleton = consonant_skeleton(normalized_candidate)
    if not query_skeleton or not candidate_skeleton:
        return False

    return candidate_skeleton.startswith(query_skeleton)


def iter_product_search_fields(product: dict[str, Any]) -> list[tuple[str, float, str]]:
    return [
        (str(product.get("code", "")), _search_index_field_weights["code"], "code"),
        (str(product.get("name", "")), _search_index_field_weights["name"], "name"),
        (" ".join(product.get("aliases", []) or []), _search_index_field_weights["aliases"], "aliases"),
        (" ".join(product.get("tags", []) or []), _search_index_field_weights["tags"], "tags"),
        (str(product.get("collection", "")), _search_index_field_weights["collection"], "collection"),
        (str(product.get("description", "")), _search_index_field_weights["description"], "description"),
    ]


def build_search_index(products: list[dict[str, Any]]) -> SearchIndex:
    cache_key = id(products)
    with _search_index_cache_lock:
        cached = _search_index_cache.get(cache_key)
        if cached is not None:
            return cached

    token_scores_by_product: list[dict[str, float]] = []
    token_signal_by_product: list[dict[str, float]] = []
    compact_fields_by_product: list[str] = []
    token_doc_occurrence: dict[str, set[int]] = defaultdict(set)
    co_occurrence: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for index, product in enumerate(products):
        product_scores: dict[str, float] = {}
        product_signals: dict[str, float] = {}
        relation_terms: set[str] = set()
        compact_parts: list[str] = []

        for field_value, field_weight, field_name in iter_product_search_fields(product):
            if not field_value:
                continue

            compact_field = compact_search_text(field_value)
            if compact_field and field_name != "description":
                compact_parts.append(compact_field)
            if compact_field and field_name == "code":
                previous_score = product_scores.get(compact_field, 0.0)
                product_scores[compact_field] = max(previous_score, field_weight)
                previous_signal = product_signals.get(compact_field, 0.0)
                product_signals[compact_field] = max(previous_signal, field_weight)
                token_doc_occurrence[compact_field].add(index)
                relation_terms.add(compact_field)

            for token in tokenize_search_text(field_value):
                for expanded_token in expand_search_token(token):
                    previous_score = product_scores.get(expanded_token, 0.0)
                    product_scores[expanded_token] = max(previous_score, field_weight)
                    previous_signal = product_signals.get(expanded_token, 0.0)
                    product_signals[expanded_token] = max(previous_signal, field_weight)
                    token_doc_occurrence[expanded_token].add(index)
                    if field_name in _search_relation_fields:
                        relation_terms.add(expanded_token)

        relation_list = list(relation_terms)
        for left_index in range(len(relation_list)):
            left_term = relation_list[left_index]
            for right_index in range(left_index + 1, len(relation_list)):
                right_term = relation_list[right_index]
                co_occurrence[left_term][right_term] += 1.0
                co_occurrence[right_term][left_term] += 1.0

        token_scores_by_product.append(product_scores)
        token_signal_by_product.append(product_signals)
        compact_fields_by_product.append(" ".join(compact_parts))

    token_df = {token: len(indexes) for token, indexes in token_doc_occurrence.items()}
    document_count = max(1, len(products))
    token_idf = {
        token: math.log1p((document_count + 1) / (doc_count + 1))
        for token, doc_count in token_df.items()
    }
    postings = {
        token: sorted(indexes)
        for token, indexes in token_doc_occurrence.items()
    }
    related_terms: dict[str, list[tuple[str, float]]] = {}
    for token, neighbors in co_occurrence.items():
        ranked_neighbors = sorted(neighbors.items(), key=lambda item: item[1], reverse=True)[:8]
        related_terms[token] = [(neighbor, weight) for neighbor, weight in ranked_neighbors]

    index_model = SearchIndex(
        token_scores=token_scores_by_product,
        token_signal=token_signal_by_product,
        token_df=token_df,
        token_idf=token_idf,
        postings=postings,
        related_terms=related_terms,
        vocabulary=sorted(token_df.keys()),
        compact_fields=compact_fields_by_product,
        term_expansion_cache={},
    )
    with _search_index_cache_lock:
        _search_index_cache[cache_key] = index_model
    return index_model


def expand_query_terms(query_token: str, index_model: SearchIndex, *, allow_related: bool) -> dict[str, float]:
    normalized_query_token = compact_search_text(query_token)
    cache_key = (normalized_query_token, allow_related)
    cached = index_model.term_expansion_cache.get(cache_key)
    if cached is not None:
        return cached

    expansions: dict[str, float] = {}
    for token in expand_search_token(normalized_query_token):
        expansions[token] = max(expansions.get(token, 0.0), 1.0)

    if not expansions:
        index_model.term_expansion_cache[cache_key] = expansions
        return expansions

    vocabulary = index_model.vocabulary
    base_terms = tuple(expansions.keys())
    for base_term in base_terms:
        for candidate in vocabulary:
            if candidate in expansions:
                continue

            if abbreviation_matches(base_term, candidate):
                expansions[candidate] = max(expansions.get(candidate, 0.0), 0.71)
                continue

            minimum_length = min(len(base_term), len(candidate))
            if minimum_length < 4:
                continue

            similarity = SequenceMatcher(None, base_term, candidate).ratio()
            if similarity >= 0.9:
                expansions[candidate] = max(expansions.get(candidate, 0.0), 0.87)
                continue
            if similarity >= 0.82:
                expansions[candidate] = max(expansions.get(candidate, 0.0), 0.73)

        if allow_related:
            for related_term, relation_weight in index_model.related_terms.get(base_term, []):
                if relation_weight < 4:
                    continue
                related_idf = index_model.token_idf.get(related_term, 0.0)
                if related_idf < 1.0:
                    continue
                expansions[related_term] = max(
                    expansions.get(related_term, 0.0),
                    min(0.6, 0.35 + relation_weight * 0.03),
                )

    index_model.term_expansion_cache[cache_key] = expansions
    return expansions


def product_match_score(product_index: int, query: str, index_model: SearchIndex) -> float | None:
    query_tokens = tokenize_search_text(query)
    if not query_tokens:
        return 0.0
    allow_related = len(query_tokens) > 1

    product_token_scores = index_model.token_scores[product_index]
    product_token_signal = index_model.token_signal[product_index]
    compact_query = compact_search_text(query)

    total_score = 0.0
    strong_signal_seen = False

    if compact_query and compact_query in index_model.compact_fields[product_index]:
        total_score += 4.0
        strong_signal_seen = True

    for query_token in query_tokens:
        candidate_terms = expand_query_terms(query_token, index_model, allow_related=allow_related)
        if not candidate_terms:
            return None

        best_term_score = 0.0
        best_term_signal = 0.0
        for candidate_term, candidate_weight in candidate_terms.items():
            token_weight = product_token_scores.get(candidate_term)
            if token_weight is None:
                continue

            token_idf = index_model.token_idf.get(candidate_term, 0.0)
            candidate_score = token_weight * candidate_weight * token_idf
            if candidate_score > best_term_score:
                best_term_score = candidate_score
                best_term_signal = product_token_signal.get(candidate_term, 0.0)

        if best_term_score < _search_min_term_score:
            return None

        total_score += best_term_score
        if best_term_signal >= 4.0:
            strong_signal_seen = True

    if not strong_signal_seen:
        return None
    return total_score


def filter_products(products: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    normalized_query = normalize_search_text(query)
    if not normalized_query:
        return products

    cache_key = (id(products), normalized_query)
    with _search_results_cache_lock:
        cached = _search_results_cache.get(cache_key)
        if cached is not None:
            _search_results_cache.move_to_end(cache_key)
            return cached

    index_model = build_search_index(products)

    query_tokens = tokenize_search_text(normalized_query)
    if not query_tokens:
        return products

    candidate_indexes: set[int] | None = None
    allow_related = len(query_tokens) > 1
    for query_token in query_tokens:
        expanded_terms = expand_query_terms(query_token, index_model, allow_related=allow_related)
        term_candidates: set[int] = set()
        for expanded_term in expanded_terms.keys():
            term_candidates.update(index_model.postings.get(expanded_term, []))

        if not term_candidates:
            with _search_results_cache_lock:
                _search_results_cache[cache_key] = []
                _search_results_cache.move_to_end(cache_key)
                while len(_search_results_cache) > _search_result_cache_size:
                    _search_results_cache.popitem(last=False)
            return []

        if candidate_indexes is None:
            candidate_indexes = term_candidates
        else:
            candidate_indexes.intersection_update(term_candidates)
            if not candidate_indexes:
                with _search_results_cache_lock:
                    _search_results_cache[cache_key] = []
                    _search_results_cache.move_to_end(cache_key)
                    while len(_search_results_cache) > _search_result_cache_size:
                        _search_results_cache.popitem(last=False)
                return []

    if candidate_indexes is None:
        return []

    lexical_scores: dict[int, float] = {}
    for index in sorted(candidate_indexes):
        score = product_match_score(index, normalized_query, index_model)
        if score is not None and score >= _search_minimum_score:
            lexical_scores[index] = score

    scored_products: list[tuple[float, int, dict[str, Any]]] = []
    for index in sorted(lexical_scores.keys()):
        scored_products.append((lexical_scores[index], index, products[index]))

    scored_products.sort(key=lambda item: (-item[0], item[1]))
    results = [product for _, _, product in scored_products]

    with _search_results_cache_lock:
        _search_results_cache[cache_key] = results
        _search_results_cache.move_to_end(cache_key)
        while len(_search_results_cache) > _search_result_cache_size:
            _search_results_cache.popitem(last=False)

    return results


def build_sections(
    products: list[dict[str, Any]],
    cfg: dict[str, Any],
    *,
    preserve_input_order: bool = False,
) -> list[Section]:
    order: list[str] = cfg.get("order") or []
    ordered_keys = set(order)
    labels: dict[str, str] = cfg.get("labels") or {}

    by_collection: dict[str, list[dict[str, Any]]] = {}
    input_order: list[str] = []
    for product in products:
        collection_key = product.get("collection", "other")
        if collection_key not in by_collection:
            input_order.append(collection_key)
        by_collection.setdefault(collection_key, []).append(product)

    sections: list[Section] = []
    if preserve_input_order:
        for key in input_order:
            items = by_collection.get(key, [])
            if items:
                sections.append(Section(key=key, title=labels.get(key, key.replace("-", " ").title()), items=items))
        return sections

    for key in order:
        items = by_collection.get(key, [])
        if items:
            sections.append(Section(key=key, title=labels.get(key, key.replace("-", " ").title()), items=items))

    for key, items in by_collection.items():
        if key in ordered_keys:
            continue
        sections.append(Section(key=key, title=labels.get(key, key.replace("-", " ").title()), items=items))

    return sections
