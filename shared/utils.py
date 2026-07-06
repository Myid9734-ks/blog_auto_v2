from shared.constants import (
    CONFIG_DIR,
    IMAGES_DIR,
    LOGS_DIR,
    NAVER_DIR,
    NAVER_PROFILE,
    OUTPUT_DIR,
    TISTORY_DIR,
    TISTORY_PROFILE,
)


def ensure_dirs() -> None:
    for directory in [
        OUTPUT_DIR, NAVER_DIR, TISTORY_DIR,
        IMAGES_DIR, LOGS_DIR,
        CONFIG_DIR, NAVER_PROFILE, TISTORY_PROFILE,
    ]:
        directory.mkdir(parents=True, exist_ok=True)
