"""
setup_naver.py
네이버 최초 수동 로그인 — 세션을 config/naver_profile/ 에 저장한다.
이후 upload_naver.py는 이 프로필을 재사용해 자동 로그인 상태를 유지한다.

사용법:
    python3 scripts/setup_naver.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright

from shared.constants import NAVER_PROFILE
from shared.utils import ensure_dirs

NAVER_LOGIN_URL = "https://nid.naver.com/nidlogin.login"
NAVER_HOME_URL  = "https://www.naver.com"


def verify_login(page) -> bool:
    page.goto(NAVER_HOME_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    return page.locator("#account .MyView-module__link_login___HpHMW").count() == 0


def main():
    ensure_dirs()
    print("=" * 50)
    print("네이버 최초 로그인")
    print("=" * 50)
    print(f"프로필 경로: {NAVER_PROFILE}")
    print("브라우저가 열리면 로그인 후 Enter를 누르세요.")
    print("=" * 50)

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
        page.goto(NAVER_LOGIN_URL)

        input("\n로그인 완료 후 Enter를 누르세요... ")

        if not verify_login(page):
            context.close()
            print("❌ 로그인 확인 실패 — 다시 시도하세요.")
            sys.exit(1)

        context.close()

    print(f"\n✅ 로그인 완료 — 세션 저장: {NAVER_PROFILE}")
    print("이제 python3 scripts/upload_naver.py 를 실행하세요.")


if __name__ == "__main__":
    main()
