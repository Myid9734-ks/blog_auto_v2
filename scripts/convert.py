"""
convert.py
output/content.json → output/naver/, output/tistory/ 파일 변환

사용법:
    python3 scripts/convert.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.constants import (
    CATEGORY_MAP,
    CONTENT_JSON,
    NAVER_DIR,
    TISTORY_DIR,
)
from shared.utils import ensure_dirs


class ConvertError(Exception):
    pass


def load_content() -> dict:
    if not CONTENT_JSON.exists():
        raise ConvertError(f"파일 없음: {CONTENT_JSON}")
    try:
        return json.loads(CONTENT_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConvertError(f"JSON 파싱 실패: {e}")


def segments_to_html(segments: list) -> str:
    parts = []
    image_counter = 1
    for seg in segments:
        t = seg["type"]
        if t in ("intro", "text", "outro"):
            parts.append(f'<p>{seg["content"]}</p>')
        elif t == "heading":
            parts.append(f'<h3>{seg["content"]}</h3>')
        elif t == "image":
            parts.append(f"{{{{IMAGE_{image_counter}}}}}")
            image_counter += 1
    return "\n\n".join(parts)


def map_category(category: str, platform: str) -> str:
    if category not in CATEGORY_MAP:
        raise ConvertError(
            f"카테고리 매핑 없음: '{category}' "
            f"(agent_guide.md 카테고리 목록 확인)"
        )
    return CATEGORY_MAP[category][platform]


def generate_slug() -> str:
    return f"post-{datetime.now().strftime('%Y%m%d')}"


def write_platform_files(directory: Path, files: dict[str, str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        (directory / filename).write_text(content, encoding="utf-8")


def convert_naver(data: dict, html: str, slug: str) -> None:
    write_platform_files(NAVER_DIR, {
        "title.txt":    data["title"],
        "content.html": html,
        "hashtags.txt": ",".join(data["hashtags"]),
        "category.txt": map_category(data["category"], "naver"),
        "slug.txt":     slug,
    })


def convert_tistory(data: dict, html: str) -> None:
    write_platform_files(TISTORY_DIR, {
        "title.txt":    data["title"],
        "content.html": html,
        "hashtags.txt": ",".join(data["hashtags"]),
        "category.txt": map_category(data["category"], "tistory"),
    })


def main():
    ensure_dirs()
    try:
        data = load_content()
        html = segments_to_html(data["segments"])
        slug = generate_slug()
        convert_naver(data, html, slug)
        convert_tistory(data, html)
        print(f"✅ 변환 완료: {data['title']}")
        print(f"   - slug    : {slug}")
        print(f"   - 네이버  : {map_category(data['category'], 'naver')}")
        print(f"   - 티스토리: {map_category(data['category'], 'tistory')}")
    except ConvertError as e:
        print(f"❌ 변환 실패: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
