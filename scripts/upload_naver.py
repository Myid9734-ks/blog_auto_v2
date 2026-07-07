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


def dismiss_draft_popup(page, timeout_ms: int = 8000) -> None:
    """이전에 작성 중이던 글을 이어서 쓸지 묻는 팝업 처리.
    자동화는 항상 output 파일 기준으로 새 글을 작성해야 하므로 '취소'를 눌러
    옛 임시저장 글을 버리고 새로 시작한다. 팝업이 언제/어느 frame에 뜰지 알 수
    없으므로(비동기 렌더링), locator.is_visible(timeout=...)의 timeout은 무시되고
    즉시 스냅샷만 반환한다는 점에 유의해 wait_for로 매번 새로 프레임 목록을 훑으며
    폴링한다. 한 번만 확인하면 팝업이 늦게 뜨는 경우 놓친다."""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        for scope in (page, *page.frames):
            try:
                popup = scope.locator("text=작성 중인 글이 있습니다")
                if popup.count() == 0:
                    continue
                popup.first.wait_for(state="visible", timeout=1000)
            except Exception:
                continue
            try:
                cancel_btn = scope.locator("button:has-text('취소')")
                cancel_btn.first.wait_for(state="visible", timeout=1000)
                cancel_btn.first.click()
                page.wait_for_timeout(1000)
                return
            except Exception:
                continue
        page.wait_for_timeout(300)


def open_editor(page) -> None:
    page.goto(NAVER_WRITE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    if "nid.naver.com" in page.url or "nidlogin" in page.url:
        raise LoginError("글쓰기 페이지 이동 중 로그인 화면으로 리다이렉트됨")

    dismiss_draft_popup(page)


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


def debug_dump_publish_state(page, ef) -> None:
    """발행 실패 원인 파악용: 스크린샷 + '발행' 버튼 후보들의 상태를 /tmp에 저장."""
    try:
        page.screenshot(path="/tmp/naver_publish_debug.png")
    except Exception:
        pass
    try:
        info = ef.evaluate(
            """
            () => [...document.querySelectorAll('button')]
                .filter(b => (b.textContent || '').includes('발행'))
                .map(b => {
                    const r = b.getBoundingClientRect();
                    return {
                        text: (b.textContent || '').trim(),
                        cls: b.className,
                        disabled: b.disabled,
                        visible: r.width > 0 && r.height > 0,
                        rect: { x: r.x, y: r.y, w: r.width, h: r.height },
                    };
                })
            """
        )
        Path("/tmp/naver_publish_debug.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  디버그 정보 저장: /tmp/naver_publish_debug.png, /tmp/naver_publish_debug.json")
    except Exception as e:
        print(f"  디버그 정보 저장 실패: {e}")


def find_publish_confirm_button(ef):
    """상단 '발행' 토글 버튼과 패널 안 최종 확인 버튼 모두 텍스트가 '발행'이고
    CSS 클래스명은 해시가 붙어 로드마다 바뀌므로 신뢰할 수 없다.
    대신 위치로 구분한다: 토글 버튼은 항상 상단(y가 작음), 확인 버튼은 항상
    패널 맨 아래(y가 가장 큼)에 있으므로 화면에서 가장 아래에 있는 후보를 고른다."""
    candidates = ef.locator("button:has-text('발행')")
    count = candidates.count()
    best = None
    best_y = -1.0
    for idx in range(count):
        cand = candidates.nth(idx)
        try:
            if not cand.is_visible(timeout=500):
                continue
            box = cand.bounding_box()
            if box and box["y"] > best_y:
                best_y = box["y"]
                best = cand
        except Exception:
            continue
    return best


def verify_recent_post(page, blog_id: str, title: str) -> bool:
    """URL 변화만으로는 발행 성공을 신뢰할 수 없을 때(네이버 에디터 URL 포맷이
    실행마다 달라 postwrite 문자열 유무로 판단이 불가능한 경우가 있음) 블로그
    메인에서 방금 쓴 글이 실제로 올라갔는지 재확인한다. 이 확인 없이 실패로
    단정하면 이미 발행된 글을 다음 재시도에서 중복 발행하게 된다."""
    try:
        page.goto(f"https://blog.naver.com/{blog_id}", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        frame = page.frame(name="mainFrame") or page
        return frame.locator(f"text={title}").count() > 0
    except Exception:
        return False


def publish_confirm(page, ef, title: str) -> None:
    btn = find_publish_confirm_button(ef)
    if btn is None:
        raise UploadError("최종 발행 버튼을 찾을 수 없음 (후보 없음)")

    network_log = []

    def on_request(req):
        if req.method == "POST":
            network_log.append(
                {"type": "request", "url": req.url, "postData": (req.post_data or "")[:500]}
            )

    def on_response(res):
        if res.request.method == "POST":
            try:
                body = res.text()[:500]
            except Exception:
                body = "(읽기 실패)"
            network_log.append(
                {"type": "response", "url": res.url, "status": res.status, "body": body}
            )

    page.on("request", on_request)
    page.on("response", on_response)
    try:
        btn.wait_for(state="visible", timeout=10000)
        btn.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        url_before = page.url
        try:
            btn.click(timeout=5000)
        except PlaywrightTimeoutError:
            btn.click(timeout=5000, force=True)

        # 발행 성공 여부 검증: 실제 발행되면 에디터 URL을 벗어나 포스트 URL로 이동한다.
        # "postwrite" 문자열 유무로 판단하면 네이버 에디터 URL 포맷이 실행마다 달라 오탐이
        # 생기므로, 클릭 직전 URL과 달라졌는지만 확인한다.
        try:
            page.wait_for_url(lambda url: url != url_before, timeout=15000)
            print("  최종 발행 완료")
        except PlaywrightTimeoutError:
            if verify_recent_post(page, NAVER_BLOG_ID, title):
                print("  URL 변화는 감지되지 않았지만 블로그에 글이 실제로 올라간 것을 확인 → 발행 성공 처리")
                return
            debug_dump_publish_state(page, ef)
            Path("/tmp/naver_publish_network.json").write_text(
                json.dumps(network_log, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print("  네트워크 로그 저장: /tmp/naver_publish_network.json")
            raise UploadError(
                f"발행 버튼 클릭 후에도 편집 페이지에 머물러 있음 (발행 실패 추정, 현재 URL: {page.url})"
            )
    except UploadError:
        raise
    except Exception as e:
        raise UploadError(f"최종 발행 버튼을 찾을 수 없음: {e}")
    finally:
        page.remove_listener("request", on_request)
        page.remove_listener("response", on_response)


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
    publish_confirm(page, ef, data["title"])
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
                # 발행 확인 등 네이티브 dialog는 기본적으로 Playwright가 자동 취소하므로,
                # 반드시 수락하도록 핸들러를 등록해야 발행이 실제로 진행된다.
                page.on("dialog", lambda dialog: dialog.accept())
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
