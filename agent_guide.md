# AutoPost v2 — OpenClaw 에이전트 가이드

이 파일 하나면 충분하다. 순서대로 따라한다.

---

## 전체 실행 순서

```
1. logs/used_titles.json 을 확인해 기발행 제목과 겹치지 않는 제목을 정한다
2. writing_guidelines.txt 를 읽고 블로그 글을 작성한다
3. output/content.json 에 저장한다
4. python3 validate.py output/content.json 실행
   (제목이 중복이면 여기서 자동으로 거부됨)
5. ✅ 통과 → 다음 단계 진행
   ❌ 실패 → 오류 메시지 확인 후 content.json 수정 → 4번 재실행
6. python3 scripts/convert.py 실행
7. python3 scripts/generate_image.py 실행
8. python3 scripts/upload_naver.py 실행
9. python3 scripts/upload_tistory.py 실행
10. python3 scripts/cleanup.py 실행
    (발행된 제목이 logs/used_titles.json 에 자동 기록됨)
```

---

## 파일 경로

### 1단계 — AI 작성
| 파일 | 설명 |
|------|------|
| `output/content.json` | AI가 작성한 원본 (writing_guidelines.txt 형식) |

### 2단계 — convert.py 실행 후 생성되는 파일
| 파일 | 설명 |
|------|------|
| `output/naver/title.txt` | 제목 |
| `output/naver/content.html` | 본문 HTML (`{{IMAGE_N}}` 포함) |
| `output/naver/hashtags.txt` | 쉼표 구분 태그 |
| `output/naver/category.txt` | 네이버 카테고리 |
| `output/naver/slug.txt` | URL 슬러그 |
| `output/tistory/title.txt` | 제목 |
| `output/tistory/content.html` | 본문 HTML (`{{IMAGE_N}}` 포함) |
| `output/tistory/hashtags.txt` | 쉼표 구분 태그 |
| `output/tistory/category.txt` | 티스토리 카테고리 |

### 3단계 — generate_image.py 실행 후
| 파일 | 설명 |
|------|------|
| `images/*.png` | gpt-image-1 생성 이미지 로컬 저장 |
| `output/image_paths.json` | 생성된 이미지 절대경로 목록 |
| `output/naver/content.html` | `{{IMAGE_N}}` → 로컬 `<img src>` 경로로 교체됨 |
| `output/tistory/content.html` | `{{IMAGE_N}}` → 로컬 `<img src>` 경로로 교체됨 |

### 4단계 — 업로드 스크립트 동작
- `upload_naver.py`: SmartEditor ONE에 이미지 직접 업로드 → 네이버 CDN 변환
- `upload_tistory.py`: `POST attach.json` API로 Kakao CDN 업로드 → TinyMCE 삽입
- 두 스크립트 모두 로컬 경로 → CDN URL 자동 교체 후 발행

### 5단계 — cleanup.py 실행 후 삭제되는 파일
| 파일 | 설명 |
|------|------|
| `images/*.png` | 업로드 완료된 이미지 |
| `output/content.json` | 원본 AI 작성 파일 |
| `output/image_paths.json` | 이미지 경로 목록 |
| `output/naver/*.txt/.html` | 네이버용 변환 파일 |
| `output/tistory/*.txt/.html` | 티스토리용 변환 파일 |

---

## 최초 설정 (최초 1회만)

```bash
# 네이버 로그인 세션 저장 (브라우저에서 수동 로그인 후 Enter)
python3 scripts/setup_naver.py
```

---

## 카테고리

`content.json`의 `category`는 **네이버 카테고리 기준**으로 작성한다.
티스토리 카테고리는 convert.py가 자동으로 매핑한다.

### 네이버 (content.json에 이 값을 그대로 입력)
```
생활정보
경제 정책
금융정보
ETF 산업
저축,투자
주식 투자
부동산 투자
비트코인
스포츠
건강
여행
```

---

## 중복 제목 확인 (전체 실행 순서 1, 4, 10번 참고)

- 1번: 작성 전 `logs/used_titles.json`을 확인해 기발행 제목과 겹치지 않는 제목을 고른다.
- 4번: `validate.py`가 동일 제목을 자동으로 거부한다 (검증 실패 시 다른 제목으로 재작성).
- 10번: `cleanup.py` 실행 시 `content.json`의 title이 `logs/used_titles.json`에 자동 기록된 뒤 삭제되므로, 발행이 끝난 글의 제목은 별도 작업 없이도 다음 글 작성 때 중복 검사 대상이 된다.

---

## 주의사항

- `validate.py` 통과 전에는 절대 다음 단계 진행 금지
- 동일 스크립트 2회 이상 실행 금지 (중복 포스팅 사고)
- 실행 전 항상 프로세스 확인:
  ```bash
  ps aux | grep -E 'convert|generate_image|upload_naver|upload_tistory|cleanup' | grep -v grep
  ```
