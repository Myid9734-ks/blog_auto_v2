"""
upload_naver.py
output/naver/ 파일을 읽어 네이버 블로그에 자동 업로드한다.
setup_naver.py로 최초 로그인 후 실행해야 한다.

사용법:
    python3 scripts/upload_naver.py
"""

import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.constants import (
    IMAGE_PATHS_JSON,
    NAVER_DIR,
    NAVER_PROFILE,
    UPLOAD_MAX_RETRIES,
)
from shared.utils import ensure_dirs

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
NAVER_BLOG_ID    = os.getenv("NAVER_BLOG_ID", "")
NAVER_WRITE_URL  = f"https://blog.naver.com/{NAVER_BLOG_ID}/postwrite"

IMG_PAT = re.compile(r"<img\s[^>]*/?>|<img\s[^>]*>", re.IGNORECASE)


class UploadError(Exception):
    pass


class LoginError(UploadError):
    pass


def send_telegram(message: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": message},
            timeout=10,
        )
    except Exception:
        pass


def read_post_files() -> dict:
    try:
        return {
            "title":    (NAVER_DIR / "title.txt").read_text(encoding="utf-8").strip(),
            "content":  (NAVER_DIR / "content.html").read_text(encoding="utf-8").strip(),
            "hashtags": (NAVER_DIR / "hashtags.txt").read_text(encoding="utf-8").strip(),
            "category": (NAVER_DIR / "category.txt").read_text(encoding="utf-8").strip(),
        }
    except FileNotFoundError as e:
        raise UploadError(f"업로드 파일 없음: {e} (convert.py를 먼저 실행하세요)")


def load_image_paths() -> list:
    if not IMAGE_PATHS_JSON.exists():
        raise UploadError(
            f"이미지 경로 파일 없음: {IMAGE_PATHS_JSON} (generate_image.py를 먼저 실행하세요)"
        )
    return json.loads(IMAGE_PATHS_JSON.read_text(encoding="utf-8"))


def prepare_content(content: str, image_paths: list) -> str:
    """{{IMAGE_N}} 플레이스홀더를 로컬 경로 img 태그로 변환."""
    for i, path in enumerate(image_paths):
        placeholder = f"{{{{IMAGE_{i + 1}}}}}"
        if placeholder in content:
            content = content.replace(
                placeholder,
                f'<img src="{path}" style="max-width:100%;" alt="이미지{i + 1}">',
            )
    return content


def split_segments(content: str) -> list[dict]:
    """img 태그를 기준으로 text/image 세그먼트로 분리."""
    segments = []
    image_index = 0
    last_end = 0

    for m in IMG_PAT.finditer(content):
        text_before = content[last_end : m.start()].strip()
        if text_before:
            segments.append({"type": "html", "content": text_before})
        segments.append({"type": "image", "index": image_index})
        image_index += 1
        last_end = m.end()

    text_after = content[last_end:].strip()
    if text_after:
        segments.append({"type": "html", "content": text_after})

    return segments


def get_editor_frame(page):
    """postwrite URL을 포함하는 frame 반환."""
    for frame in page.frames:
        if "postwrite" in frame.url or "PostWriteForm" in frame.url:
            return frame
    return page


def click_first_visible(locator, timeout: int = 5000, force: bool = False) -> bool:
    try:
        count = locator.count()
    except Exception:
        return False
    for idx in range(count):
        try:
            if locator.nth(idx).is_visible(timeout=1000):
                locator.nth(idx).click(timeout=timeout, force=force)
                return True
        except Exception:
            continue
    return False


def verify_login(page) -> bool:
    page.goto("https://blog.naver.com", wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    return "nid.naver.com" not in page.url


def open_editor(page) -> None:
    page.goto(NAVER_WRITE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    if "nid.naver.com" in page.url or "nidlogin" in page.url:
        raise LoginError("글쓰기 페이지 이동 중 로그인 화면으로 리다이렉트됨")

    # 이전 글 이어쓰기 팝업 처리
    ef = get_editor_frame(page)
    try:
        popup = ef.locator("div.se-popup-alert-confirm")
        if popup.is_visible(timeout=3000):
            btn = popup.locator("button").filter(has_text="확인")
            (btn.first if btn.count() > 0 else popup.locator("button").last).click()
            page.wait_for_timeout(1000)
    except Exception:
        pass


def fill_title(page, ef, title: str) -> None:
    area = ef.locator(
        "div.se-title-text p.se-text-paragraph, div.se-title-text span.se-placeholder"
    ).first
    area.click(force=True)
    page.wait_for_timeout(500)
    page.keyboard.press("Meta+a")
    page.wait_for_timeout(200)
    page.keyboard.type(title, delay=30)
    page.wait_for_timeout(300)
    print("  제목 입력 완료")


def focus_body(page, ef) -> None:
    """제목 칸에서 벗어나 본문 영역으로 포커스 이동."""
    # 본문 placeholder 클릭 (빈 에디터의 '내용을 입력하세요' 영역)
    placeholder = ef.locator(
        "div.se-section-text span.se-placeholder, "
        "div.se-component-content span.se-placeholder"
    ).last
    try:
        if placeholder.count() > 0 and placeholder.is_visible(timeout=2000):
            placeholder.click(force=True)
            page.wait_for_timeout(300)
            return
    except Exception:
        pass
    # 폴백: Tab으로 이동
    page.keyboard.press("Tab")
    page.wait_for_timeout(500)


def paste_html(context, page, ef, html_fragment: str) -> None:
    """HTML을 새 탭에서 복사해 에디터에 붙여넣기."""
    doc = (
        '<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"></head>'
        f"<body>{html_fragment}</body></html>"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tmp:
        tmp.write(doc)
        tmp_path = Path(tmp.name)
    try:
        tab = context.new_page()
        tab.goto(tmp_path.as_uri())
        tab.wait_for_timeout(600)
        tab.keyboard.press("Meta+a")
        tab.wait_for_timeout(200)
        tab.keyboard.press("Meta+c")
        tab.wait_for_timeout(400)
        tab.close()

        # 본문 끝으로 커서 이동 (제목 칸 제외한 마지막 content 영역)
        try:
            ef.locator(
                "div.se-section-content div.se-component-content, "
                "div.se-section-text p.se-text-paragraph"
            ).last.click(force=True)
        except Exception:
            pass
        page.wait_for_timeout(300)
        page.keyboard.press("Meta+v")
        page.wait_for_timeout(1200)
    finally:
        tmp_path.unlink(missing_ok=True)


def upload_image_file(page, ef, image_path: str) -> None:
    print(f"    이미지 업로드: {Path(image_path).name}")
    for sel in [
        "button.se-image-toolbar-button",
        "button.se-insert-menu-button-image",
        'button[data-name="image"]',
    ]:
        btn = ef.locator(sel)
        try:
            if btn.count() > 0:
                with page.expect_file_chooser(timeout=5000) as fc:
                    btn.first.click(timeout=2000)
                fc.value.set_files(image_path)
                page.wait_for_timeout(3500)
                return
        except Exception:
            continue
    raise UploadError(f"이미지 업로드 버튼 없음: {image_path}")


def select_category(page, ef, category: str) -> None:
    try:
        trigger = ef.locator(
            "span.text__sraQE, button[class*='category'], [class*='category_select']"
        ).first
        trigger.click(timeout=5000)
        page.wait_for_timeout(1000)
        ef.locator("[class*='option_category'] li, [role='option']").filter(
            has_text=category
        ).first.click(timeout=5000)
        page.wait_for_timeout(500)
        print(f"  카테고리 선택: {category}")
    except Exception:
        print("  카테고리 선택 건너뜀")


def fill_tags(page, ef, hashtags: str) -> None:
    try:
        tag_input = ef.locator(
            "input#tag-input, input[placeholder*='태그'], input[placeholder*='tag']"
        ).first
        tag_input.click(timeout=5000)
        for tag in [t.strip() for t in hashtags.split(",") if t.strip()]:
            tag_input.fill(tag)
            tag_input.press("Enter")
            page.wait_for_timeout(300)
        print("  태그 입력 완료")
    except Exception:
        print("  태그 입력 건너뜀")


def publish_open(page, ef) -> None:
    close = ef.locator("button.se-help-panel-close-button")
    if close.count() > 0 and close.first.is_visible():
        close.first.click()
        page.wait_for_timeout(500)

    btn = ef.locator(
        "button.publish_btn__m9KHH, button[class*='publish_btn'], button:has-text('발행')"
    )
    if not click_first_visible(btn, timeout=5000):
        raise UploadError("발행 버튼을 찾을 수 없음")
    page.wait_for_timeout(2000)


def publish_confirm(page, ef) -> None:
    # 패널 안의 최종 발행 버튼 = 'button:has-text("발행")' 중 마지막 것
    btn = ef.locator("button:has-text('발행')").last
    try:
        btn.wait_for(state="visible", timeout=10000)
        btn.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        btn.click(force=True)
        page.wait_for_timeout(3000)
        print("  최종 발행 완료")
    except Exception as e:
        raise UploadError(f"최종 발행 버튼을 찾을 수 없음: {e}")


def upload(context, page, data: dict) -> None:
    print("  [1] 로그인 상태 확인")
    if not verify_login(page):
        raise LoginError("로그인 세션 없음 — setup_naver.py를 다시 실행하세요")

    print("  [2] 글쓰기 페이지 열기")
    open_editor(page)
    ef = get_editor_frame(page)

    print(f"  [3] 제목 입력: {data['title']}")
    fill_title(page, ef, data["title"])

    print("  [4] 본문+이미지 순차 입력")
    focus_body(page, ef)
    image_paths = load_image_paths()
    content = prepare_content(data["content"], image_paths)
    for seg in split_segments(content):
        if seg["type"] == "html":
            paste_html(context, page, ef, seg["content"])
        else:
            idx = seg["index"]
            if idx < len(image_paths):
                upload_image_file(page, ef, image_paths[idx])

    print("  [5] 발행 버튼 클릭")
    publish_open(page, ef)

    print(f"  [6] 카테고리 선택: {data['category']}")
    select_category(page, ef, data["category"])

    print(f"  [7] 태그 입력: {data['hashtags']}")
    fill_tags(page, ef, data["hashtags"])

    print("  [8] 최종 발행")
    publish_confirm(page, ef)
    print("  ✅ 업로드 완료")


def run_with_retry(data: dict) -> bool:
    for attempt in range(1, UPLOAD_MAX_RETRIES + 1):
        print(f"\n[시도 {attempt}/{UPLOAD_MAX_RETRIES}]")
        try:
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(NAVER_PROFILE),
                    channel="chrome",
                    headless=False,
                    slow_mo=100,
                    viewport={"width": 1280, "height": 900},
                    args=["--disable-blink-features=AutomationControlled"],
                    ignore_default_args=["--enable-automation"],
                )
                page = context.pages[0] if context.pages else context.new_page()
                upload(context, page, data)
                context.close()
            send_telegram(f"✅ 네이버 블로그 업로드 완료\n제목: {data['title']}")
            return True

        except LoginError as e:
            print(f"  로그인 오류: {e}")
            send_telegram(f"❌ 네이버 블로그 업로드 실패 (로그인)\n{e}")
            return False
        except PlaywrightTimeoutError as e:
            print(f"  타임아웃: {e}")
        except Exception as e:
            print(f"  오류: {e}")

        if attempt < UPLOAD_MAX_RETRIES:
            wait = attempt * 10
            print(f"  {wait}초 후 재시도...")
            time.sleep(wait)

    send_telegram(f"❌ 네이버 블로그 업로드 실패 (3회)\n제목: {data['title']}")
    return False


def main():
    ensure_dirs()
    if not NAVER_BLOG_ID:
        print("❌ .env에 NAVER_BLOG_ID가 없음")
        sys.exit(1)

    try:
        data = read_post_files()
    except UploadError as e:
        print(f"❌ {e}")
        sys.exit(1)

    print(f"업로드 시작: {data['title']}")
    success = run_with_retry(data)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
