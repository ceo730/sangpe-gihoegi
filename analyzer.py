import base64
import io
import json
import re

import anthropic
from PIL import Image

from prompt import SYSTEM_PROMPT, USER_PROMPT

MAX_TILE_BYTES = 800_000  # 타일당 800KB → 총 10타일이어도 ~10MB
MAX_DIMENSION = 7900
TILE_HEIGHT = 4000
TILE_OVERLAP = 200
TARGET_WIDTH = 1100  # 텍스트 가독 충분, 용량 대폭 절약


def _save_jpeg(img: Image.Image, max_bytes: int = MAX_TILE_BYTES) -> bytes:
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    for quality in (90, 80, 70, 55):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        if buf.tell() <= max_bytes:
            return buf.getvalue()

    shrunk = img
    while True:
        shrunk = shrunk.resize(
            (int(shrunk.width * 0.75), int(shrunk.height * 0.75)), Image.LANCZOS
        )
        buf = io.BytesIO()
        shrunk.save(buf, format="JPEG", quality=60)
        if buf.tell() <= max_bytes:
            return buf.getvalue()


def _split_tall_image(img: Image.Image) -> list[Image.Image]:
    if img.height <= MAX_DIMENSION:
        return [img]

    tiles = []
    y = 0
    while y < img.height:
        bottom = min(y + TILE_HEIGHT, img.height)
        tile = img.crop((0, y, img.width, bottom))
        tiles.append(tile)
        y = bottom - TILE_OVERLAP
        if bottom == img.height:
            break
    return tiles


def _process_image(image_bytes: bytes) -> list[tuple[bytes, str]]:
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode == "P":
        img = img.convert("RGBA")

    if img.width > TARGET_WIDTH:
        ratio = TARGET_WIDTH / img.width
        img = img.resize((TARGET_WIDTH, int(img.height * ratio)), Image.LANCZOS)

    tiles = _split_tall_image(img)

    results = []
    for tile in tiles:
        data = _save_jpeg(tile)
        results.append((data, "image/jpeg"))
    return results


def analyze_page(image_bytes_list: list[tuple[bytes, str]], api_key: str) -> dict:
    """상세페이지 이미지를 1회 호출로 분석."""
    client = anthropic.Anthropic(api_key=api_key)

    content = []
    for image_bytes, _media_type in image_bytes_list:
        processed = _process_image(image_bytes)
        for data, media_type in processed:
            image_b64 = base64.standard_b64encode(data).decode("utf-8")
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_b64,
                    },
                }
            )

    content.append({"type": "text", "text": USER_PROMPT})

    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    raw_text = response.content[0].text
    return _extract_json(raw_text)


def _extract_json(raw_text: str) -> dict:
    match = re.search(r"```json\s*(.*?)\s*```", raw_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    match = re.search(r"```\s*(.*?)\s*```", raw_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"JSON 파싱 실패. AI 원본 응답 앞부분:\n{raw_text[:500]}"
    )
