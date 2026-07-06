"""
debug_tistory.py
Tistory 에디터 HTML 구조 / TinyMCE 설정 / 업로드 관련 힌트 분석
실행: python3 scripts/debug_tistory.py
결과: /tmp/tistory_toolbar.html  /tmp/tistory_tinymce.json
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from shared.constants import TISTORY_COOKIES

TISTORY_BLOG_ID  = os.getenv("TISTORY_BLOG_ID", "")
TISTORY_BLOG_URL = f"https://{TISTORY_BLOG_ID}.tistory.com"
OUT_HTML = Path("/tmp/tistory_toolbar.html")
OUT_JSON = Path("/tmp/tistory_tinymce.json")


def main():
    cookies = json.loads(TISTORY_COOKIES.read_text(encoding="utf-8"))

    with sync_playwright() as p:
        ctx = p.chromium.launch(channel="chrome", headless=False).new_context(
            viewport={"width": 1280, "height": 900}
        )
        ctx.add_cookies(cookies)
        page = ctx.new_page()
        page.goto(f"{TISTORY_BLOG_URL}/manage/newpost", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        # ── 1. TinyMCE 설정 ────────────────────────────────────────────────
        mce_config = page.evaluate("""
            () => {
                const mce = window.tinyMCE || window.tinymce;
                if (!mce) return {error: 'tinymce not found'};
                const ed = mce.activeEditor || Object.values(mce.editors || {})[0];
                if (!ed) return {error: 'no active editor'};
                return {
                    id: ed.id,
                    plugins: ed.settings?.plugins || [],
                    toolbar: ed.settings?.toolbar || '',
                    images_upload_url: ed.settings?.images_upload_url || '',
                    fileUpload: ed.settings?.fileUpload || null,
                    paste_data_images: ed.settings?.paste_data_images,
                };
            }
        """)
        print("=== TinyMCE 설정 ===")
        print(json.dumps(mce_config, ensure_ascii=False, indent=2))

        # ── 2. 툴바 전체 HTML ─────────────────────────────────────────────
        toolbar_html = page.evaluate("""
            () => {
                const t = document.querySelector('.mce-toolbar-grp')
                       || document.querySelector('.mce-container.mce-panel');
                return t ? t.outerHTML : 'toolbar not found';
            }
        """)
        OUT_HTML.write_text(toolbar_html, encoding="utf-8")
        print(f"\n툴바 HTML → {OUT_HTML}  ({len(toolbar_html)} 바이트)")

        # ── 3. 아이콘 클래스 목록 ─────────────────────────────────────────
        icons = page.evaluate("""
            () => [...document.querySelectorAll('i[class],span[class]')]
                  .filter(e => e.className.includes('mce-i') || e.className.includes('mce-ico'))
                  .map(e => e.className)
        """)
        print("\n=== 아이콘 클래스 목록 ===")
        for ic in icons:
            print(" ", ic)

        # ── 4. 이미지/첨부 관련 힌트 (HTML 소스) ─────────────────────────
        hints = page.evaluate("""
            () => {
                const src = document.documentElement.innerHTML;
                const keys = ['fileUpload','imageUpload','uploadFile','upload','attach','파일','이미지'];
                const out = {};
                for (const k of keys) {
                    const i = src.indexOf(k);
                    if (i >= 0) out[k] = src.slice(Math.max(0,i-60), i+150);
                }
                return out;
            }
        """)
        print("\n=== HTML 소스 업로드 힌트 ===")
        for k, v in hints.items():
            print(f"[{k}] {v}\n")

        # ── 5. 스크립트 소스에서 upload_url 검색 ─────────────────────────
        upload_in_scripts = page.evaluate("""
            async () => {
                const scripts = [...document.querySelectorAll('script[src]')];
                const results = [];
                for (const s of scripts.slice(0, 8)) {
                    try {
                        const r = await fetch(s.src, {credentials: 'include'});
                        const t = await r.text();
                        const m = t.match(/['"](\/[^'"]*(?:upload|attach|image)[^'"]*)['"]/i);
                        if (m) results.push({src: s.src.slice(-60), match: m[0]});
                    } catch(e) {}
                }
                return results;
            }
        """)
        print("=== JS 파일 upload/attach URL 검색 ===")
        for r in upload_in_scripts:
            print(f"  {r['src']}: {r['match']}")

        # ── 6. iframe 목록 ────────────────────────────────────────────────
        iframes = page.evaluate("""
            () => [...document.querySelectorAll('iframe')].map(f=>({
                id: f.id, name: f.name, src: f.src?.slice(0,80)
            }))
        """)
        print("\n=== iframe 목록 ===")
        for fr in iframes:
            print(" ", fr)

        result = {
            "mce_config": mce_config,
            "icons": icons,
            "hints_keys": list(hints.keys()),
            "upload_in_scripts": upload_in_scripts,
            "iframes": iframes,
        }
        OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n전체 결과 → {OUT_JSON}")
        ctx.close()


if __name__ == "__main__":
    main()
