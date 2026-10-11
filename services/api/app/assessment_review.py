"""Public-data submission review; a consistency fingerprint is never approval.

This helper checks presence, representation and bounded input only. It does not
read an oracle, execute SQL, estimate a score or change any category. The API
must authenticate, authorize, lock and check lifecycle before using the result.
"""

import hashlib
import json
import math

from .engines.assessment import public_form


REVIEW_VERSION = "vector-assessment-review-1"
MAX_BODY_BYTES = 100_000
MAX_JSON_BYTES = 16_000
MAX_SQL_BYTES = 12_000
MAX_JSON_NODES = 1_000
MAX_JSON_DEPTH = 20


def _tree_issue(value, *, maximum_nodes=20_000, maximum_depth=32,
                maximum_text_bytes=MAX_BODY_BYTES):
    pending = [(value, 0, frozenset())]
    nodes = text_bytes = 0
    while pending:
        value, depth, ancestors = pending.pop()
        nodes += 1
        if nodes > maximum_nodes or depth > maximum_depth:
            return "limit", "Ответ превышает допустимую сложность структуры."
        if isinstance(value, (dict, list)):
            if id(value) in ancestors:
                return "format", "Ответ должен быть обычным JSON без циклических ссылок."
            if nodes + len(pending) + len(value) > maximum_nodes:
                return "limit", "Ответ превышает допустимую сложность структуры."
            descendants = ancestors | {id(value)}
            if isinstance(value, dict):
                if any(not isinstance(key, str) or len(key) > 256 for key in value):
                    return "format", "Ключи JSON должны быть строками длиной не более 256 символов."
                try:
                    text_bytes += sum(len(key.encode("utf-8")) for key in value)
                except UnicodeError:
                    return "format", "Ответ содержит некорректную Unicode-строку."
                children = value.values()
            else:
                children = value
            pending.extend((child, depth + 1, descendants) for child in children)
        elif isinstance(value, str):
            try:
                text_bytes += len(value.encode("utf-8"))
            except UnicodeError:
                return "format", "Ответ содержит некорректную Unicode-строку."
        elif isinstance(value, float):
            if not math.isfinite(value):
                return "format", "JSON не допускает NaN и Infinity."
        elif isinstance(value, int):
            if not isinstance(value, bool) and value.bit_length() > 16_384:
                return "limit", "Целое число превышает допустимый размер."
        elif value is not None:
            return "format", "Ответ должен содержать только стандартные значения JSON."
        if text_bytes > maximum_text_bytes:
            return "limit", "Ответ превышает допустимый размер текста."
    return None


def _canonical_hash(value, maximum_bytes):
    issue = _tree_issue(value, maximum_text_bytes=maximum_bytes)
    if issue:
        return None, issue
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        return None, ("format", "Не удалось прочитать ответ как стандартный JSON.")
    if len(encoded) > maximum_bytes:
        return None, ("limit", "Ответы превышают допустимый размер.")
    return hashlib.sha256(encoded).hexdigest(), None


def _reject_constant(value):
    raise ValueError("Non-finite JSON number")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _item_issue(item, answer):
    if answer is None or isinstance(answer, str) and not answer.strip():
        return "missing", "Ответ не заполнен."
    kind = item["type"]
    if kind in ("single_choice", "choice"):
        value = answer.get("id", answer.get("value")) if isinstance(answer, dict) else answer
        known = {option["id"] for option in item.get("options", [])}
        if not isinstance(value, str) or value not in known:
            return "format", "Выберите один из вариантов этого задания."
    elif kind == "number":
        value = answer.get("value") if isinstance(answer, dict) else answer
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            return "format", "Введите конечное число; логическое значение не является числом."
        try:
            number = float(value.strip().replace(",", ".")) if isinstance(value, str) else float(value)
        except (ValueError, TypeError, OverflowError):
            return "format", "Введите конечное число."
        if not math.isfinite(number):
            return "format", "Введите конечное число без NaN или Infinity."
    elif kind == "json":
        value = answer
        if isinstance(answer, str):
            try:
                if len(answer.encode("utf-8")) > MAX_JSON_BYTES:
                    return "limit", "JSON-ответ должен занимать не более 16 КБ."
                value = json.loads(answer, parse_constant=_reject_constant,
                                   object_pairs_hook=_unique_object)
            except (ValueError, TypeError, UnicodeError, RecursionError):
                return "format", "Проверьте синтаксис JSON, уникальность ключей и конечность чисел."
        issue = _tree_issue(value, maximum_nodes=MAX_JSON_NODES,
                            maximum_depth=MAX_JSON_DEPTH,
                            maximum_text_bytes=MAX_JSON_BYTES)
        if issue:
            return issue
        # Empty lists and objects are valid answers. Semantic shape is not read
        # from a private oracle and correctness is exclusively the grader's job.
    elif kind == "sql":
        query = answer.get("query") if isinstance(answer, dict) else answer
        if not isinstance(query, str) or not query.strip():
            return "format", "Введите SQL-запрос строкой."
        try:
            if len(query.encode("utf-8")) > MAX_SQL_BYTES:
                return "limit", "SQL-запрос должен занимать не более 12 КБ."
        except UnicodeError:
            return "format", "Запрос содержит некорректную Unicode-строку."
        # Deliberately do not parse, prepare or execute the query here.
    else:
        return "format", "Формат этого задания не поддерживается проверкой перед отправкой."
    return None


def review_submission(public_snapshot, saved_answers, draft_answers=None):
    """Review a prospective merge without modifying any supplied object.

    ``answered`` counts nonempty values, including malformed values. A ready
    review says only that representation checks passed, never that answers are
    correct. Null hashes/tokens indicate uncanonicalizable or oversized input.
    Unknown IDs are reported as global issues without echoing an unknown key.
    """
    if not isinstance(public_snapshot, dict):
        raise ValueError("Invalid public assessment snapshot")
    items = public_snapshot.get("items")
    if not isinstance(items, list) or not items or len(items) > 64:
        raise ValueError("Invalid public assessment items")
    ids = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] or len(item["id"]) > 256 or not isinstance(item.get("type"), str):
            raise ValueError("Invalid public assessment item")
        ids.append(item["id"])
        if item["type"] in ("single_choice", "choice"):
            options = item.get("options")
            if not isinstance(options, list) or not options or any(not isinstance(option, dict) or not isinstance(option.get("id"), str) for option in options) or len({option["id"] for option in options}) != len(options):
                raise ValueError("Invalid public assessment choices")
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate public assessment item IDs")
    # Reuse the existing public allowlist boundary. Extra private envelope/item
    # metadata cannot influence or be returned by this helper.
    public_input = dict(public_snapshot)
    if public_input.get("context") is None:
        public_input.pop("context", None)
    snapshot = public_form(public_input)
    snapshot["scope"] = public_snapshot.get("scope", "global_category")
    snapshot["demo"] = bool(public_snapshot.get("demo", False))
    public_sha, public_issue = _canonical_hash(snapshot, 1_000_000)
    if public_issue:
        raise ValueError("Uncanonicalizable public assessment snapshot")
    issues = []
    if not isinstance(saved_answers, dict):
        saved_answers = {}
        issues.append({"item_id": None, "kind": "format", "detail": "Сохранённые ответы должны быть JSON-объектом."})
    if draft_answers is None:
        draft_answers = {}
    elif not isinstance(draft_answers, dict):
        draft_answers = {}
        issues.append({"item_id": None, "kind": "format", "detail": "Ответы для отправки должны быть JSON-объектом."})
    prospective = {**saved_answers, **draft_answers}
    saved_sha, _ = _canonical_hash(saved_answers, MAX_BODY_BYTES)
    prospective_sha, prospective_issue = _canonical_hash(prospective, MAX_BODY_BYTES)
    # Saved SHA is diagnostic; a repaired final snapshot must not be blocked by
    # an overwritten malformed saved value. Only prospective input is submitted.
    for issue in (prospective_issue,):
        if issue and not any(row["item_id"] is None and (row["kind"], row["detail"]) == issue for row in issues):
            issues.append({"item_id": None, "kind": issue[0], "detail": issue[1]})
    if set(prospective) - set(ids):
        issues.append({"item_id": None, "kind": "format", "detail": "В ответах есть неизвестные задания."})
    answered = 0
    for item in items:
        value = prospective.get(item["id"])
        issue = _item_issue(item, value)
        if issue is None or issue[0] != "missing":
            answered += 1
        if issue:
            issues.append({"item_id": item["id"], "kind": issue[0], "detail": issue[1]})
    token = None
    if prospective_sha is not None:
        token, _ = _canonical_hash({"review_version": REVIEW_VERSION,
                                   "public_form_sha256": public_sha,
                                   "prospective_answers_sha256": prospective_sha}, 1_024)
    # Invalid top-level types are not a reviewable snapshot even after fallback.
    if any(row["detail"] in ("Сохранённые ответы должны быть JSON-объектом.",
                             "Ответы для отправки должны быть JSON-объектом.") for row in issues):
        token = None
    return {"answered": answered, "total": len(items),
            "structural_ready": not issues, "issues": issues,
            "public_form_sha256": public_sha, "saved_answers_sha256": saved_sha,
            "prospective_answers_sha256": prospective_sha, "review_token": token,
            "limitations": ["Проверяются только наличие, формат и размер ответов; правильность и баллы не оцениваются.",
                            "SQL-запрос не выполняется; его синтаксис и результат здесь не проверяются.",
                            "Review token — отпечаток согласованности снимка, а не авторизация, результат экзамена или разрешение присвоить категорию.",
                            "API должен отдельно проверить владельца, время, статус попытки и совпадение итогового снимка под блокировкой строки."]}
