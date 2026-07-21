"""
setup_tistory.py
티스토리 최초 수동 로그인 — 쿠키를 config/tistory_cookies.json 에 저장한다.
이후 upload_tistory.py는 이 쿠키를 복원해 자동 로그인 상태를 유지한다.

사용법:
    python3 scripts/setup_tistory.py
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from shared.constants import TISTORY_COOKIES, TISTORY_PROFILE
from shared.utils import ensure_dirs

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

TISTORY_BLOG_ID   = os.getenv("TISTORY_BLOG_ID", "")
TISTORY_LOGIN_URL = "https://www.tistory.com/auth/login"


def get_manage_url() -> str:
    if not TISTORY_BLOG_ID:
        print("❌ .env에 TISTORY_BLOG_ID가 없습니다.")
        sys.exit(1)
    return f"https://{TISTORY_BLOG_ID}.tistory.com/manage"


def verify_login(page, manage_url: str) -> bool:
    page.goto(manage_url, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    current_url = page.url.lower()
    return (
        "accounts.kakao.com" not in current_url
        and "auth/login" not in current_url
        and manage_url.lower() in current_url
    )


def save_cookies(context) -> None:
    cookies = context.cookies()
    for c in cookies:
        if c.get("expires", -1) == -1:
            c["expires"] = time.time() + 86400 * 30
    TISTORY_COOKIES.write_text(
        json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  쿠키 저장 완료: {TISTORY_COOKIES} ({len(cookies)}개)")


def main():
    ensure_dirs()
    manage_url = get_manage_url()

    print("=" * 50)
    print("티스토리 최초 로그인")
    print("=" * 50)
    print("브라우저가 열리면 카카오 계정으로 로그인 후 Enter를 누르세요.")
    print("'로그인 상태 유지'를 반드시 체크하세요.")
    print("=" * 50)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(TISTORY_PROFILE),
            channel="chrome",
            headless=False,
            slow_mo=100,
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(TISTORY_LOGIN_URL)

        input("\n로그인 완료 후 Enter를 누르세요... ")

        try:
            logged_in = verify_login(page, manage_url)
        except PlaywrightError:
            print("❌ 브라우저 창이 이미 닫혀 있습니다.")
            print("   로그인 후 창을 닫지 말고 그대로 둔 채 터미널에서 Enter를 누르세요.")
            sys.exit(1)

        if not logged_in:
            context.close()
            print("❌ 로그인 확인 실패 — 다시 시도하세요.")
            sys.exit(1)

        save_cookies(context)
        context.close()

    print(f"\n✅ 로그인 완료")
    print("이제 python3 scripts/upload_tistory.py 를 실행하세요.")


if __name__ == "__main__":
    main()
