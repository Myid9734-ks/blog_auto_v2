"""
cleanup.py
업로드 완료 후 사용된 이미지와 output 파일을 삭제한다.

사용법:
    python3 scripts/cleanup.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.constants import (
    CONTENT_JSON,
    IMAGE_PATHS_JSON,
    IMAGES_DIR,
    NAVER_DIR,
    TISTORY_DIR,
)
from shared.used_titles import record_title


def delete_file(path: Path, deleted: list, skipped: list) -> None:
    if path.exists():
        path.unlink()
        deleted.append(str(path))
    else:
        skipped.append(str(path))


def delete_dir_contents(directory: Path, deleted: list, skipped: list) -> None:
    if not directory.exists():
        skipped.append(str(directory) + "/ (없음)")
        return
    for f in sorted(directory.iterdir()):
        if f.is_file():
            delete_file(f, deleted, skipped)


def record_published_title() -> None:
    if not CONTENT_JSON.exists():
        return
    try:
        data = json.loads(CONTENT_JSON.read_text(encoding="utf-8"))
        record_title(data["title"])
    except (json.JSONDecodeError, KeyError, OSError, RuntimeError) as e:
        print(f"⚠️  제목 기록 실패: {e}")


def main():
    deleted = []
    skipped = []

    # 삭제 전 발행된 제목 기록 (logs/used_titles.json, 중복 방지용)
    record_published_title()

    # 이미지 파일 삭제 (image_paths.json 기준)
    if IMAGE_PATHS_JSON.exists():
        try:
            image_paths = json.loads(IMAGE_PATHS_JSON.read_text(encoding="utf-8"))
            for path_str in image_paths:
                delete_file(Path(path_str), deleted, skipped)
        except (json.JSONDecodeError, Exception) as e:
            print(f"⚠️  image_paths.json 읽기 실패: {e}")

    # output 파일 삭제
    delete_file(CONTENT_JSON, deleted, skipped)
    delete_file(IMAGE_PATHS_JSON, deleted, skipped)
    delete_dir_contents(NAVER_DIR, deleted, skipped)
    delete_dir_contents(TISTORY_DIR, deleted, skipped)

    print(f"✅ 삭제 완료: {len(deleted)}개")
    for f in deleted:
        print(f"   삭제: {f}")

    if skipped:
        print(f"   건너뜀 (없음): {len(skipped)}개")


if __name__ == "__main__":
    main()
