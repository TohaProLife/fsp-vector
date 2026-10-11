"""Original public programming tasks. Expected values remain outside sandboxes."""
from __future__ import annotations

TASKS = {
    "merge-ranges-v1": {
        "title": "Объединение интервалов активности",
        "prompt": "Реализуйте solve(data). data — массив пар [start, end] с целыми start <= end. Верните отсортированные непересекающиеся интервалы, объединив пересекающиеся и соприкасающиеся. Пустой вход даёт []. Вход менять нельзя. До 10 000 интервалов.",
        "examples": [{"input": [[1, 4], [3, 7], [10, 12]], "output": [[1, 7], [10, 12]]}],
        "cases": [[], [[1, 4], [3, 7], [10, 12]], [[0, 0]], [[5, 8], [1, 5], [2, 3]],
                  [[-8, -4], [-5, 2], [2, 4]], [[9, 10], [1, 2], [5, 6]],
                  [[i * 2, i * 2 + 3] for i in range(300)], [[4, 4], [4, 4], [3, 5]]],
    },
    "rolling-count-v1": {
        "title": "Счётчик событий в окне",
        "prompt": "Реализуйте solve(data). data содержит times (неубывающий массив целых времён событий) и window (положительное целое). Для каждого события t верните число уже поступивших событий s, для которых t-window < s <= t. При одинаковом времени события поступают в порядке массива. До 10 000 событий; решение не должно перебирать всё окно заново.",
        "examples": [{"input": {"times": [1, 2, 4, 4, 7], "window": 3}, "output": [1, 2, 2, 3, 1]}],
        "cases": [{"times": [], "window": 1}, {"times": [1, 2, 4, 4, 7], "window": 3},
                  {"times": [3, 3, 3], "window": 1}, {"times": [-5, -4, 0, 1], "window": 2},
                  {"times": [0, 2, 4, 6], "window": 2}, {"times": list(range(1000)), "window": 91}],
    },
}


def expected(task_id: str, data):
    if task_id == "merge-ranges-v1":
        output = []
        for start, end in sorted(data):
            if output and start <= output[-1][1]:
                output[-1][1] = max(output[-1][1], end)
            else:
                output.append([start, end])
        return output
    if task_id == "rolling-count-v1":
        # Deliberately independent straightforward reference for bounded hidden cases.
        return [sum(t - data["window"] < s <= t for s in data["times"][:i + 1])
                for i, t in enumerate(data["times"])]
    raise ValueError("Unknown trusted task")


def public_catalog():
    return [{"id": key, **{k: v for k, v in task.items() if k != "cases"},
             "languages": ["python", "javascript"], "source": "original_programming_practice",
             "changes_category": False} for key, task in TASKS.items()]
