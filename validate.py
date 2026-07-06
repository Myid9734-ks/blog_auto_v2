"""
validate.py
OpenClaw 에이전트가 출력한 글(JSON)을 검증하는 스크립트.
writing_guidelines.txt의 규칙을 코드로 강제한다.

사용법:
    python3 validate.py output/content_raw.json
    또는
    from validate import validate_ai_output
    data = validate_ai_output(raw_text)
"""

import json
import sys

from shared.constants import (
    ALLOWED_RISK_LEVELS,
    ALLOWED_TYPES,
    CHAR_MAX,
    CHAR_MIN,
    DISCLAIMER_KEYWORDS,
    HASHTAG_MAX,
    HASHTAG_MIN,
    HEADING_MAX,
    HEADING_MIN,
    IMAGE_MAX,
    IMAGE_MIN,
    REQUIRED_FIELDS,
    RISK_SENSITIVE,
    SENSITIVE_BANNED_PHRASES,
    TITLE_MAX_LEN,
)
from shared.used_titles import is_duplicate_title


class ValidationError(Exception):
    pass


def strip_code_fence(raw_text: str) -> str:
    """AI가 실수로 ```json 코드블록을 붙였을 경우 제거"""
    cleaned = raw_text.strip()
    if not cleaned.startswith("```"):
        return cleaned
    lines = cleaned.split("\n")
    lines = lines[1:]  # 첫 줄(```json 또는 ```) 제거
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]  # 닫는 ``` 제거
    return "\n".join(lines).strip()


def parse_json(raw_text: str) -> dict:
    cleaned = strip_code_fence(raw_text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValidationError(f"JSON 파싱 실패: {e}")


def validate_top_level_fields(data: dict) -> None:
    for field in REQUIRED_FIELDS:
        if field not in data:
            raise ValidationError(f"필수 필드 누락: '{field}'")


def validate_title(title: str) -> None:
    if not isinstance(title, str) or not title.strip():
        raise ValidationError("title이 비어있음")
    if len(title) > TITLE_MAX_LEN:
        raise ValidationError(f"title이 {TITLE_MAX_LEN}자 초과 ({len(title)}자): {title}")


def validate_title_not_duplicate(title: str) -> None:
    if is_duplicate_title(title):
        raise ValidationError(f"이미 발행된 제목과 중복됨: '{title}' (logs/used_titles.json 확인)")


def validate_risk_level(risk_level: str) -> None:
    if risk_level not in ALLOWED_RISK_LEVELS:
        raise ValidationError(
            f"risk_level 값이 잘못됨: '{risk_level}' "
            f"({' 또는 '.join(sorted(ALLOWED_RISK_LEVELS))}만 허용)"
        )


def validate_hashtags(hashtags) -> None:
    count = len(hashtags) if isinstance(hashtags, list) else "N/A"
    if not isinstance(hashtags, list) or not (HASHTAG_MIN <= len(hashtags) <= HASHTAG_MAX):
        raise ValidationError(
            f"hashtags는 {HASHTAG_MIN}~{HASHTAG_MAX}개여야 함 (현재 {count}개)"
        )


def validate_segment_fields(seg: dict, index: int) -> None:
    if "type" not in seg:
        raise ValidationError(f"segments[{index}]에 'type' 필드 없음")
    if seg["type"] not in ALLOWED_TYPES:
        raise ValidationError(f"segments[{index}]의 type이 허용되지 않음: '{seg['type']}'")
    if seg["type"] == "image":
        if "prompt" not in seg or not seg["prompt"].strip():
            raise ValidationError(f"segments[{index}] (image)에 prompt가 없음")
    else:
        if "content" not in seg or not seg["content"].strip():
            raise ValidationError(f"segments[{index}] ({seg['type']})에 content가 없음")


def validate_segments_basic(segments) -> None:
    if not isinstance(segments, list) or len(segments) == 0:
        raise ValidationError("segments가 비어있거나 리스트가 아님")
    for i, seg in enumerate(segments):
        validate_segment_fields(seg, i)


def validate_intro_outro_positions(segments: list, types_list: list) -> None:
    intro_count = types_list.count("intro")
    outro_count = types_list.count("outro")
    if intro_count != 1:
        raise ValidationError(f"intro는 정확히 1개여야 함 (현재 {intro_count}개)")
    if outro_count != 1:
        raise ValidationError(f"outro는 정확히 1개여야 함 (현재 {outro_count}개)")
    if types_list[0] != "intro":
        raise ValidationError("intro는 segments의 맨 처음에 위치해야 함")
    if types_list[-1] != "outro":
        raise ValidationError("outro는 segments의 맨 마지막에 위치해야 함")


def validate_headings(segments: list, types_list: list) -> None:
    heading_count = types_list.count("heading")
    if not (HEADING_MIN <= heading_count <= HEADING_MAX):
        raise ValidationError(
            f"heading은 {HEADING_MIN}~{HEADING_MAX}개여야 함 (현재 {heading_count}개)"
        )
    for i, seg in enumerate(segments):
        if seg["type"] != "heading":
            continue
        if i + 1 >= len(segments):
            raise ValidationError(f"segments[{i}] heading 뒤에 아무것도 없음 (text가 와야 함)")
        if segments[i + 1]["type"] != "text":
            raise ValidationError(
                f"segments[{i}] heading('{seg['content']}') 바로 다음은 "
                f"text여야 하는데 '{segments[i + 1]['type']}'이 옴"
            )


def validate_images(segments: list, types_list: list) -> None:
    image_count = types_list.count("image")
    if not (IMAGE_MIN <= image_count <= IMAGE_MAX):
        raise ValidationError(
            f"image는 {IMAGE_MIN}~{IMAGE_MAX}개여야 함 (현재 {image_count}개)"
        )
    for i, seg in enumerate(segments):
        if seg["type"] != "image" or i == 0:
            continue
        prev_type = segments[i - 1]["type"]
        if prev_type in ("intro", "outro"):
            raise ValidationError(
                f"segments[{i}] image가 '{prev_type}' 바로 뒤에 배치됨 "
                "(intro/outro 직후에는 image 배치 금지)"
            )


def validate_char_count(segments: list) -> int:
    total = sum(
        len(s["content"]) for s in segments if s["type"] in ("intro", "text", "outro")
    )
    if not (CHAR_MIN <= total <= CHAR_MAX):
        raise ValidationError(
            f"전체 글자수가 기준({CHAR_MIN:,}~{CHAR_MAX:,}자)을 벗어남: {total:,}자"
        )
    return total


def validate_sensitive_rules(segments: list) -> None:
    outro_content = segments[-1]["content"]
    if not any(kw in outro_content for kw in DISCLAIMER_KEYWORDS):
        raise ValidationError(
            "risk_level이 sensitive인데 outro에 면책 문구가 없음 "
            f"(다음 키워드 중 하나 필요: {', '.join(DISCLAIMER_KEYWORDS)})"
        )
    full_text = " ".join(
        s.get("content", "") for s in segments if s["type"] in ("intro", "text", "outro")
    )
    for phrase in SENSITIVE_BANNED_PHRASES:
        if phrase in full_text:
            raise ValidationError(f"sensitive 등급에서 금지된 단정 표현 발견: '{phrase}'")


def validate_ai_output(raw_text: str) -> dict:
    data = parse_json(raw_text)
    validate_top_level_fields(data)
    validate_title(data["title"])
    validate_title_not_duplicate(data["title"])
    validate_risk_level(data["risk_level"])
    validate_hashtags(data["hashtags"])
    validate_segments_basic(data["segments"])

    types_list = [s["type"] for s in data["segments"]]
    validate_intro_outro_positions(data["segments"], types_list)
    validate_headings(data["segments"], types_list)
    validate_images(data["segments"], types_list)
    total_chars = validate_char_count(data["segments"])

    if data["risk_level"] == RISK_SENSITIVE:
        validate_sensitive_rules(data["segments"])

    data["_total_chars"] = total_chars
    return data


def main():
    if len(sys.argv) < 2:
        print("사용법: python3 validate.py <json파일경로>")
        sys.exit(1)

    path = sys.argv[1]
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_text = f.read()
    except FileNotFoundError:
        print(f"❌ 파일을 찾을 수 없음: {path}")
        sys.exit(1)
    except OSError as e:
        print(f"❌ 파일 읽기 오류: {e}")
        sys.exit(1)

    try:
        data = validate_ai_output(raw_text)
        print(f"✅ 검증 통과: {data['title']}")
        print(f"   - risk_level: {data['risk_level']}")
        print(f"   - segments 개수: {len(data['segments'])}")
        print(f"   - 전체 글자수: {data['_total_chars']:,}자")
        sys.exit(0)
    except ValidationError as e:
        print(f"❌ 검증 실패: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
