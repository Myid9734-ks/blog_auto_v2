"""
generate_image.py
content.json의 image 프롬프트로 이미지 생성 → images/ 로컬 저장 → output/image_paths.json 기록
{{IMAGE_N}} 교체는 각 플랫폼 업로드 스크립트에서 처리한다.

사용법:
    python3 scripts/generate_image.py
"""

import base64
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.constants import (
    CONTENT_JSON,
    IMAGE_MODEL,
    IMAGE_PATHS_JSON,
    IMAGE_SIZE,
    IMAGES_DIR,
    IMAGE_STYLE_SUFFIX,
    NAVER_DIR,
)
from shared.utils import ensure_dirs

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


class ImageError(Exception):
    pass


def check_env() -> None:
    if not OPENAI_API_KEY:
        raise ImageError(".env에 OPENAI_API_KEY가 없음")


def load_prompts() -> tuple[str, list[str]]:
    if not CONTENT_JSON.exists():
        raise ImageError(f"파일 없음: {CONTENT_JSON} (convert.py를 먼저 실행하세요)")
    data = json.loads(CONTENT_JSON.read_text(encoding="utf-8"))
    slug_file = NAVER_DIR / "slug.txt"
    if not slug_file.exists():
        raise ImageError(f"slug.txt 없음: {slug_file} (convert.py를 먼저 실행하세요)")
    slug    = slug_file.read_text(encoding="utf-8").strip()
    prompts = [s["prompt"] for s in data["segments"] if s["type"] == "image"]
    if not prompts:
        raise ImageError("content.json에 image 프롬프트가 없음")
    return slug, prompts


def save_image(b64_data: str, dest_path: Path) -> None:
    dest_path.write_bytes(base64.b64decode(b64_data))


def generate_images(slug: str, prompts: list[str]) -> list[Path]:
    client = OpenAI(api_key=OPENAI_API_KEY)
    today  = datetime.now().strftime("%Y%m%d")
    paths  = []

    for i, prompt in enumerate(prompts):
        seq         = str(i + 1).zfill(3)
        filename    = f"{today}_{slug}_{seq}.png"
        dest_path   = IMAGES_DIR / filename
        full_prompt = prompt + IMAGE_STYLE_SUFFIX

        print(f"[{i+1}/{len(prompts)}] 생성 중: {filename}")
        response = client.images.generate(
            model=IMAGE_MODEL,
            prompt=full_prompt,
            size=IMAGE_SIZE,
            n=1,
        )
        save_image(response.data[0].b64_json, dest_path)
        print(f"  저장: {dest_path}")
        paths.append(dest_path)

    return paths


def save_image_paths(paths: list[Path]) -> None:
    IMAGE_PATHS_JSON.write_text(
        json.dumps([str(p) for p in paths], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  경로 기록: {IMAGE_PATHS_JSON}")


def main():
    ensure_dirs()
    try:
        check_env()
        slug, prompts = load_prompts()
        print(f"총 {len(prompts)}장 생성 시작 (slug: {slug})\n")
        image_paths = generate_images(slug, prompts)
        save_image_paths(image_paths)
        print("\n✅ 이미지 생성 완료")
    except ImageError as e:
        print(f"❌ 오류: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 예상치 못한 오류: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
