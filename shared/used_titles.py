"""
used_titles.py
기발행 제목 목록(logs/used_titles.json)을 읽고 기록하는 단일 진입점.

validate.py  : is_duplicate_title()로 중복 제목 검증
cleanup.py   : record_title()로 발행 완료된 제목 기록
"""

import json

from shared.constants import USED_TITLES_JSON


def load_used_titles() -> list[str]:
    if not USED_TITLES_JSON.exists():
        return []
    try:
        return json.loads(USED_TITLES_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise RuntimeError(f"used_titles.json 읽기 실패: {e}")


def is_duplicate_title(title: str) -> bool:
    return title in load_used_titles()


def record_title(title: str) -> None:
    titles = load_used_titles()
    if title in titles:
        return
    titles.append(title)
    try:
        USED_TITLES_JSON.parent.mkdir(parents=True, exist_ok=True)
        USED_TITLES_JSON.write_text(
            json.dumps(titles, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as e:
        raise RuntimeError(f"used_titles.json 쓰기 실패: {e}")
