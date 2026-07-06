"""
debug_naver.py
네이버 블로그 에디터 구조 + 이미지 업로드 응답 분석
실행: python3 scripts/debug_naver.py
결과: /tmp/naver_upload_responses.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright

from shared.constants import IMAGE_PATHS_JSON, NAVER_PROFILE

OUT = Path("/tmp/naver_upload_responses.json")
NAVER_BLOG_ID = ""

import os
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
NAVER_BLOG_ID = os.getenv("NAVER_BLOG_ID", "")
NAVER_WRITE_URL = f"https://blog.naver.com/PostWriteForm.naver?blogId={NAVER_BLOG_ID}&type=1"


def main():
    image_paths = json.loads(IMAGE_PATHS_JSON.read_text(encoding="utf-8"))
    test_image  = image_paths[0]
    print(f"테스트 이미지: {test_image}")

    all_responses = []

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(NAVER_PROFILE),
            channel="chrome",
            headless=False,
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # ── 모든 네트워크 응답 캡처 ───────────────────────────────────────
        def on_response(resp):
            try:
                body = resp.text()
            except Exception:
                body = "(읽기 실패)"
            entry = {
                "url":     resp.url,
                "status":  resp.status,
                "method":  resp.request.method,
                "ct":      resp.headers.get("content-type", ""),
                "body200": body[:400],
            }
            all_responses.append(entry)
            if resp.request.method == "POST":
                print(f"\n[POST] {resp.url[-80:]}")
                print(f"  status={resp.status}  ct={entry['ct']}")
                print(f"  body: {body[:300]}")

        page.on("response", on_response)

        page.goto(NAVER_WRITE_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        # ── 에디터 iframe 구조 출력 ───────────────────────────────────────
        frames_info = page.evaluate("""
            () => [...document.querySelectorAll('iframe')].map(f => ({
                id:  f.id,
                name: f.name,
                src: (f.src || '').slice(0, 80),
                ce:  (() => {
                    try { return f.contentDocument?.body?.contentEditable; }
                    catch(e) { return 'cross-origin'; }
                })()
            }))
        """)
        print("\n=== iframe 목록 ===")
        for fr in frames_info:
            print(f"  id={fr['id']} name={fr['name']} ce={fr['ce']}  src={fr['src']}")

        # ── 이미지 버튼 셀렉터 탐색 ──────────────────────────────────────
        btns = page.evaluate("""
            () => [...document.querySelectorAll('button,a,[role="button"]')]
                  .filter(el => {
                      const t = (el.title||'') + (el.getAttribute('data-name')||'')
                              + (el.className||'') + (el.getAttribute('aria-label')||'');
                      return /image|photo|사진|img/i.test(t);
                  })
                  .map(el => ({
                      tag:  el.tagName,
                      id:   el.id,
                      cls:  el.className.slice(0,60),
                      title: el.title,
                      dataName: el.getAttribute('data-name'),
                      ariaLabel: el.getAttribute('aria-label'),
                  }))
        """)
        print("\n=== 이미지 관련 버튼 ===")
        for b in btns:
            print(f"  {b}")

        # ── 이미지 업로드 시도 ────────────────────────────────────────────
        print(f"\n이미지 업로드 시도: {Path(test_image).name}")
        all_responses.clear()

        for sel in [
            'button[data-name="image"]',
            '.se-toolbar .se-btn-image',
            'button[title*="사진"]',
            'button[title*="이미지"]',
        ]:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=600):
                    with page.expect_file_chooser(timeout=6000) as fc:
                        loc.click()
                    fc.value.set_files(test_image)
                    print(f"  파일 선택 완료 ({sel}), 응답 대기 중...")
                    page.wait_for_timeout(6000)
                    break
            except Exception as e:
                print(f"  {sel} 실패: {e}")

        # ── 에디터 내 img 태그 확인 ───────────────────────────────────────
        imgs = page.evaluate("""
            () => {
                const out = [];
                for (const f of document.querySelectorAll('iframe')) {
                    try {
                        const imgs = [...f.contentDocument.querySelectorAll('img[src]')];
                        imgs.forEach(img => out.push({iframe: f.id||f.name, src: img.src.slice(0,100)}));
                    } catch(e) {}
                }
                return out;
            }
        """)
        print("\n=== 에디터 내 img 태그 ===")
        for img in imgs:
            print(f"  iframe={img['iframe']}  src={img['src']}")

        # ── POST 응답 목록 ────────────────────────────────────────────────
        post_resps = [r for r in all_responses if r["method"] == "POST"]
        print(f"\n업로드 후 POST 응답 수: {len(post_resps)}")
        for r in post_resps:
            print(f"  [{r['status']}] {r['url'][-80:]}")
            print(f"       ct={r['ct']}")
            print(f"       body={r['body200'][:200]}")

        OUT.write_text(
            json.dumps({"frames": frames_info, "buttons": btns, "post_responses": post_resps, "editor_imgs": imgs},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n결과 저장: {OUT}")

        input("\n확인 후 Enter를 눌러 종료...")
        ctx.close()


if __name__ == "__main__":
    main()
