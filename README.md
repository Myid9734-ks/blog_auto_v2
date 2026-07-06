# blog_auto_v2

네이버 블로그 · 티스토리 동시 발행을 위한 블로그 자동화 파이프라인. AI 에이전트(OpenClaw)가 글을 작성하면, 이 저장소의 스크립트가 검증 → 변환 → 이미지 생성 → 업로드 → 정리까지 처리한다.

## 동작 흐름

```
1. AI가 output/content.json 작성 (writing_guidelines.txt 규칙 준수)
2. python3 validate.py output/content.json   # 형식/글자수/중복 제목 검증
3. python3 scripts/convert.py                # 네이버·티스토리용 HTML 변환
4. python3 scripts/generate_image.py         # gpt-image-1로 이미지 생성 및 삽입
5. python3 scripts/upload_naver.py           # 네이버 블로그 발행
6. python3 scripts/upload_tistory.py         # 티스토리 발행
7. python3 scripts/cleanup.py                # 임시 파일 정리 + 발행 제목 기록
```

전체 실행 순서와 각 단계의 산출 파일은 [agent_guide.md](agent_guide.md)에 상세히 정리되어 있다.

## 디렉터리 구조

| 경로 | 설명 |
|------|------|
| `shared/constants.py` | 경로, 글자수/개수 제한 등 모든 설정값의 Single Source of Truth |
| `shared/utils.py`, `shared/used_titles.py` | 공통 유틸 및 중복 제목 관리 |
| `scripts/convert.py` | content.json → 플랫폼별 HTML/메타 변환 |
| `scripts/generate_image.py` | 이미지 생성 및 본문 삽입 |
| `scripts/upload_naver.py`, `scripts/upload_tistory.py` | 각 플랫폼 발행 |
| `scripts/cleanup.py` | 발행 후 임시 파일 삭제 및 로그 기록 |
| `scripts/setup_naver.py`, `scripts/setup_tistory.py` | 최초 1회 로그인 세션 저장 |
| `validate.py` | content.json 형식/규칙 검증 |
| `writing_guidelines.txt` | AI 글 작성 규칙 |
| `config/` | 브라우저 로그인 세션 (git 미포함, 최초 설정 시 로컬 생성) |

## 최초 설정

```bash
pip install -r requirements.txt
cp .env.example .env   # 값 채우기

python3 scripts/setup_naver.py     # 네이버 로그인 세션 저장
python3 scripts/setup_tistory.py   # 티스토리 로그인 세션 저장
```

### 환경 변수 (`.env`)

```
OPENAI_API_KEY=
NAVER_ID=
NAVER_PW=
NAVER_BLOG_ID=
TISTORY_ID=
TISTORY_PW=
TISTORY_BLOG_ID=
TELEGRAM_TOKEN=
TELEGRAM_CHAT_ID=
```

## 주의사항

- `validate.py` 통과 전에는 절대 다음 단계로 진행하지 않는다.
- 동일 스크립트를 2회 이상 실행하지 않는다 (중복 포스팅 방지).
- 실행 전 항상 관련 프로세스가 실행 중이지 않은지 확인한다:
  ```bash
  ps aux | grep -E 'convert|generate_image|upload_naver|upload_tistory|cleanup' | grep -v grep
  ```
- `config/`, `.env`, `output/`, `images/`, `logs/used_titles.json`은 로그인 세션·발행 원고·개인정보를 포함하므로 git에 커밋하지 않는다 (`.gitignore` 참고).
