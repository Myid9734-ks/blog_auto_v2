"""
used_titles.py
기발행 제목 목록(logs/used_titles.json)을 읽고 기록하는 단일 진입점.

validate.py  : is_duplicate_title()로 중복 제목 검증
cleanup.py   : record_title()로 발행 완료된 제목 기록
upload_*.py  : 업로드 성공 직후 제목 기록
"""

import json
import re

from shared.constants import USED_TITLES_JSON


def load_used_titles() -> list[str]:
    if not USED_TITLES_JSON.exists():
        return []
    try:
        return json.loads(USED_TITLES_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise RuntimeError(f"used_titles.json 읽기 실패: {e}")


def normalize_title(title: str) -> str:
    """띄어쓰기/문장부호 차이만 있는 사실상 동일 제목도 같은 것으로 본다."""
    lowered = title.casefold().strip()
    alnum_only = re.sub(r"[^\w]+", "", lowered, flags=re.UNICODE)
    return alnum_only


def is_duplicate_title(title: str) -> bool:
    normalized = normalize_title(title)
    return any(normalize_title(saved) == normalized for saved in load_used_titles())


def record_title(title: str) -> None:
    titles = load_used_titles()
    if is_duplicate_title(title):
        return
    titles.append(title)
    try:
        USED_TITLES_JSON.parent.mkdir(parents=True, exist_ok=True)
        USED_TITLES_JSON.write_text(
            json.dumps(titles, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as e:
        raise RuntimeError(f"used_titles.json 쓰기 실패: {e}")
