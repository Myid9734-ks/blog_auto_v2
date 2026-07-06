"""
upload_tistory.py
output/tistory/ 파일을 읽어 티스토리에 자동 업로드한다.
setup_tistory.py로 최초 로그인 후 실행해야 한다.

사용법:
    python3 scripts/upload_tistory.py
"""

import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.constants import (
    IMAGE_PATHS_JSON,
    TISTORY_COOKIES,
    TISTORY_DIR,
    UPLOAD_MAX_RETRIES,
)
from shared.utils import ensure_dirs

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TISTORY_BLOG_ID  = os.getenv("TISTORY_BLOG_ID", "")
TISTORY_BLOG_URL = f"https://{TISTORY_BLOG_ID}.tistory.com"


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


def load_cookies() -> list:
    if not TISTORY_COOKIES.exists():
        raise LoginError(f"쿠키 파일 없음: {TISTORY_COOKIES} — setup_tistory.py를 먼저 실행하세요")
    return json.loads(TISTORY_COOKIES.read_text(encoding="utf-8"))


def read_post_files() -> dict:
    try:
        return {
            "title":    (TISTORY_DIR / "title.txt").read_text(encoding="utf-8").strip(),
            "content":  (TISTORY_DIR / "content.html").read_text(encoding="utf-8").strip(),
            "hashtags": (TISTORY_DIR / "hashtags.txt").read_text(encoding="utf-8").strip(),
            "category": (TISTORY_DIR / "category.txt").read_text(encoding="utf-8").strip(),
        }
    except FileNotFoundError as e:
        raise UploadError(f"업로드 파일 없음: {e} (convert.py를 먼저 실행하세요)")


def load_image_paths() -> list:
    if not IMAGE_PATHS_JSON.exists():
        raise UploadError(f"이미지 경로 파일 없음: {IMAGE_PATHS_JSON} (generate_image.py를 먼저 실행하세요)")
    return json.loads(IMAGE_PATHS_JSON.read_text(encoding="utf-8"))


def verify_login(page) -> bool:
    page.goto(f"{TISTORY_BLOG_URL}/manage", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    current_url = page.url.lower()
    body_text = page.inner_text("body")
    return (
        "accounts.kakao.com" not in current_url
        and "auth/login" not in current_url
        and "카카오계정으로 로그인" not in body_text
        and "시작하기" not in body_text
        and current_url.startswith(TISTORY_BLOG_URL.lower() + "/manage")
    )


def open_editor(page) -> None:
    page.goto(f"{TISTORY_BLOG_URL}/manage/newpost", wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    if "accounts.kakao.com" in page.url.lower():
        raise LoginError("글쓰기 페이지 이동 중 로그인 화면으로 리다이렉트됨")


def find_upload_url(page) -> str:
    """TinyMCE fileUpload 플러그인 설정에서 업로드 URL 추출."""
    url = page.evaluate("""
        () => {
            const mce = window.tinyMCE || window.tinymce;
            if (!mce) return '';
            const ed = mce.activeEditor || Object.values(mce.editors || {})[0];
            if (!ed) return '';
            // fileUpload 플러그인 설정 우선
            const fu = ed.settings?.fileUpload;
            if (fu?.upload_url) return fu.upload_url;
            if (ed.settings?.images_upload_url) return ed.settings.images_upload_url;
            return '';
        }
    """)
    if url:
        print(f"  업로드 URL 발견: {url}")
        return url if url.startswith("http") else TISTORY_BLOG_URL + url
    return ""


def upload_image_via_requests(image_path: str, upload_url: str, cookies: list) -> str:
    """requests로 이미지를 직접 업로드하고 CDN URL을 반환한다."""
    session = requests.Session()
    for c in cookies:
        session.cookies.set(c["name"], c["value"], domain=c.get("domain", ""))

    with open(image_path, "rb") as f:
        resp = session.post(
            upload_url,
            files={"file": (Path(image_path).name, f, "image/png")},
            headers={"Referer": f"{TISTORY_BLOG_URL}/manage/newpost"},
            timeout=30,
        )

    print(f"  HTTP {resp.status_code} | {resp.text[:200]}")
    resp.raise_for_status()

    data = resp.json()
    # 응답: {data: {url: "..."}} 또는 {url: "..."}
    url = (
        data.get("data", {}).get("url")
        or data.get("url")
        or data.get("tistory", {}).get("url")
        or ""
    )
    if not url:
        raise UploadError(f"업로드 응답에 URL 없음: {resp.text[:300]}")
    return "https:" + url if url.startswith("//") else url


def upload_image_via_attach_btn(page, image_path: str) -> str:
    """#attach-layer-btn 클릭 → 파일 선택 → CDN URL 캡처"""
    captured_urls: list[str] = []

    def on_response(resp):
        if resp.status == 200 and resp.request.method == "POST":
            try:
                data = resp.json()
                print(f"  POST({resp.url[-60:]}): {str(data)[:150]}")
                url = (
                    data.get("data", {}).get("url")
                    or data.get("url")
                    or data.get("tistory", {}).get("url")
                    or ""
                )
                if url:
                    if url.startswith("//"):
                        url = "https:" + url
                    captured_urls.append(url)
            except Exception:
                pass

    page.on("response", on_response)
    try:
        # 첨부 버튼 클릭 (id="attach-layer-btn")
        page.locator("#attach-layer-btn").click(timeout=5000)
        print("  #attach-layer-btn 클릭")
        page.wait_for_timeout(1500)

        # 드롭다운에서 "내 PC" / 파일업로드 옵션 클릭
        for sel in [
            'text="내 PC에서 사진 추가"',
            'text="사진 추가"',
            'text="파일 첨부"',
            '[data-type="local"]',
            '.attach-item:first-child',
            '.layer-image .btn-local',
        ]:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=1000):
                    loc.click()
                    print(f"  파일 옵션 클릭: {sel}")
                    page.wait_for_timeout(800)
                    break
            except Exception:
                pass

        # file input 직접 조작
        page.wait_for_timeout(500)
        file_input = page.locator('input[type="file"]').first
        if file_input.count() > 0:
            file_input.set_input_files(image_path)
            print("  set_input_files 완료")
            page.wait_for_timeout(5000)
        else:
            # file chooser 방식 시도
            with page.expect_file_chooser(timeout=4000) as fc_info:
                page.locator("#attach-layer-btn").click()
            fc_info.value.set_files(image_path)
            page.wait_for_timeout(5000)

    except Exception as e:
        print(f"  오류: {e}")
    finally:
        page.remove_listener("response", on_response)

    if captured_urls:
        return captured_urls[-1]

    # photosContainer에서 마지막 삽입 이미지 URL 추출
    url = page.evaluate("""
        () => {
            const container = document.querySelector('#photosContainer, .photos-container');
            if (container) {
                const imgs = [...container.querySelectorAll('img[src]')];
                return imgs.at(-1)?.src || '';
            }
            return '';
        }
    """)
    if url and url.startswith("http"):
        return url

    # 에디터 내 마지막 이미지 URL
    url = page.evaluate("""
        () => {
            const iframe = document.querySelector('iframe#editor-tistory_ifr');
            if (iframe) {
                const imgs = [...iframe.contentDocument.querySelectorAll('img[src]')];
                return imgs.at(-1)?.src || '';
            }
            return '';
        }
    """)
    if url and url.startswith("http"):
        return url

    raise UploadError(f"CDN URL 획득 실패: {image_path}")


def upload_images(page, image_paths: list, cookies: list) -> list:
    """이미지 목록을 업로드하고 CDN URL 목록을 반환한다."""
    upload_url = find_upload_url(page)
    cdn_urls = []

    for i, path in enumerate(image_paths):
        print(f"  이미지 업로드 [{i+1}/{len(image_paths)}]: {Path(path).name}")

        if upload_url:
            try:
                url = upload_image_via_requests(path, upload_url, cookies)
                print(f"    CDN: {url}")
                cdn_urls.append(url)
                continue
            except Exception as e:
                print(f"    requests 실패({e}), 첨부 버튼 방식 시도")

        url = upload_image_via_attach_btn(page, path)
        print(f"    CDN: {url}")
        cdn_urls.append(url)

    return cdn_urls


def replace_image_placeholders(content: str, cdn_urls: list, local_paths: list) -> str:
    for i, cdn_url in enumerate(cdn_urls):
        placeholder = f"{{{{IMAGE_{i+1}}}}}"
        if placeholder in content:
            img_tag = f'<img src="{cdn_url}" style="max-width:100%;" alt="이미지{i+1}">'
            content = content.replace(placeholder, img_tag)
        elif i < len(local_paths):
            # 이전 generate_image.py가 로컬 경로로 이미 교체한 경우 → src만 CDN으로 변경
            content = content.replace(f'src="{local_paths[i]}"', f'src="{cdn_url}"')
    return content


def switch_to_html_mode(page) -> None:
    page.on("dialog", lambda dialog: dialog.accept())
    page.evaluate("""
        () => {
            const btns = [...document.querySelectorAll('i.mce-txt')];
            const modeBtn = btns.find(el =>
                el.textContent.trim() === '기본모드' && el.offsetParent !== null
            );
            if (modeBtn) modeBtn.click();
        }
    """)
    page.wait_for_timeout(800)
    page.evaluate("""
        () => {
            const items = [...document.querySelectorAll('#editor-mode-html-tistory')];
            const visible = items.find(el => el.offsetParent !== null);
            if (visible) visible.click();
        }
    """)
    # HTML 에디터가 완전히 초기화될 때까지 대기
    page.wait_for_timeout(2500)


def fill_title(page, title: str) -> None:
    inp = page.locator("textarea#post-title-inp, input#post-title-inp, [placeholder*='제목']").first
    inp.click()
    inp.fill(title)
    page.wait_for_timeout(500)


def fill_content(page, content: str) -> None:
    """TinyMCE API로 본문 주입 후 change 이벤트로 Tistory 플러그인에 알림."""
    result = page.evaluate(
        """(html) => {
            const mce = window.tinyMCE || window.tinymce;
            if (mce) {
                const ed = mce.activeEditor || Object.values(mce.editors || {})[0];
                if (ed && ed.setContent) {
                    ed.setContent(html);
                    ed.undoManager.add();
                    ed.fire('change');
                    const stored = ed.getContent();
                    const imgCount = (stored.match(/<img/gi) || []).length;
                    const firstSrc = (stored.match(/src="([^"]+)"/) || [])[1] || 'none';
                    return 'chars=' + stored.length + ' imgs=' + imgCount + ' src0=' + firstSrc.slice(0, 60);
                }
            }
            // fallback: iframe body
            const iframe = document.querySelector('iframe#editor-tistory_ifr');
            if (iframe && iframe.contentDocument) {
                iframe.contentDocument.body.innerHTML = html;
                return 'iframe-body';
            }
            return 'not-found';
        }""",
        content,
    )
    print(f"  본문 입력: {result}")
    page.wait_for_timeout(1500)


def select_category(page, category: str) -> None:
    page.locator("button#category-btn").click()
    page.wait_for_timeout(1000)
    page.locator("#category-list div.mce-menu-item", has_text=category).first.click()
    page.wait_for_timeout(500)


def fill_tags(page, hashtags: str) -> None:
    tag_input = page.locator("input#tagText")
    for tag in hashtags.split(","):
        tag = tag.strip()
        if tag:
            tag_input.fill(tag)
            tag_input.press("Enter")
            page.wait_for_timeout(300)


def publish(page) -> None:
    page.locator("button#publish-layer-btn").click()
    page.wait_for_timeout(1000)
    page.locator("button#publish-btn").click()
    # 발행 AJAX 완료 보장: 네트워크 idle 대기
    try:
        page.wait_for_load_state("networkidle", timeout=12000)
    except Exception:
        page.wait_for_timeout(5000)
    page.wait_for_timeout(1000)


def upload(page, data: dict, cookies: list) -> None:
    print("  [1] 로그인 상태 확인")
    if not verify_login(page):
        raise LoginError("로그인 세션 없음 — setup_tistory.py를 다시 실행하세요")

    print("  [2] 글쓰기 페이지 열기")
    open_editor(page)

    print("  [3] 이미지 CDN 업로드")
    image_paths = load_image_paths()
    cdn_urls = upload_images(page, image_paths, cookies)
    content = replace_image_placeholders(data["content"], cdn_urls, image_paths)

    print(f"  [4] 제목 입력: {data['title']}")
    fill_title(page, data["title"])

    print(f"  [5] 카테고리 선택: {data['category']}")
    select_category(page, data["category"])

    print(f"  [6] 태그 입력: {data['hashtags']}")
    fill_tags(page, data["hashtags"])

    print("  [7] 본문 입력 (발행 직전)")
    fill_content(page, content)

    # 발행 직전 본문 길이 확인
    char_check = page.evaluate("""
        () => {
            const mce = window.tinyMCE || window.tinymce;
            const ed = mce && (mce.activeEditor || Object.values(mce.editors||{})[0]);
            return ed ? ('chars=' + ed.getContent().length) : 'no-editor';
        }
    """)
    print(f"  [8] 발행 (본문 {char_check})")
    publish(page)
    print("  ✅ 업로드 완료")


def run_with_retry(data: dict) -> bool:
    try:
        cookies = load_cookies()
    except LoginError as e:
        print(f"❌ {e}")
        return False

    for attempt in range(1, UPLOAD_MAX_RETRIES + 1):
        print(f"\n[시도 {attempt}/{UPLOAD_MAX_RETRIES}]")
        try:
            with sync_playwright() as p:
                context = p.chromium.launch(channel="chrome", headless=False).new_context(
                    viewport={"width": 1280, "height": 900},
                )
                context.add_cookies(cookies)
                page = context.new_page()
                upload(page, data, cookies)
                context.close()
            send_telegram(f"✅ 티스토리 업로드 완료\n제목: {data['title']}")
            return True

        except LoginError as e:
            print(f"  로그인 오류: {e}")
            send_telegram(f"❌ 티스토리 업로드 실패 (로그인)\n{e}")
            return False
        except PlaywrightTimeoutError as e:
            print(f"  타임아웃: {e}")
        except Exception as e:
            print(f"  오류: {e}")

        if attempt < UPLOAD_MAX_RETRIES:
            wait = attempt * 10
            print(f"  {wait}초 후 재시도...")
            time.sleep(wait)

    send_telegram(f"❌ 티스토리 업로드 실패 (3회)\n제목: {data['title']}")
    return False


def main():
    ensure_dirs()
    if not TISTORY_BLOG_ID:
        print("❌ .env에 TISTORY_BLOG_ID가 없음")
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
