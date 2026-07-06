#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "=== [1/3] 검증 ==="
python3 validate.py output/content.json

echo ""
echo "=== [2/3] 변환 ==="
python3 scripts/convert.py

echo ""
echo "=== [3/3] 이미지 생성 ==="
python3 scripts/generate_image.py

echo ""
echo "✅ 완료"
