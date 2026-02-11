import base64
import gc
import io
import json
import re

import anthropic
from PIL import Image

from prompt import SYSTEM_PROMPT, USER_PROMPT

MAX_TILE_BYTES = 500_000  # 타일당 500KB (메모리 절약)
MAX_DIMENSION = 6000
TILE_HEIGHT = 3000
TILE_OVERLAP = 100
TARGET_WIDTH = 800  # 폭 줄여서 메모리 절약


def _save_jpeg(img: Image.Image, max_bytes: int = MAX_TILE_BYTES) -> bytes:
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    for quality in (75, 60, 45):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        if buf.tell() <= max_bytes:
            return buf.getvalue()

    shrunk = img
    while True:
        shrunk = shrunk.resize(
            (int(shrunk.width * 0.7), int(shrunk.height * 0.7)), Image.LANCZOS
        )
        buf = io.BytesIO()
        shrunk.save(buf, format="JPEG", quality=50)
        if buf.tell() <= max_bytes:
            return buf.getvalue()


def _process_single_image(image_bytes: bytes) -> list[dict]:
    """이미지 1장을 처리하여 API content 블록 리스트 반환. 메모리 즉시 해제."""
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode == "P":
        img = img.convert("RGBA")

    if img.width > TARGET_WIDTH:
        ratio = TARGET_WIDTH / img.width
        img = img.resize((TARGET_WIDTH, int(img.height * ratio)), Image.LANCZOS)

    # 타일 분할
    content_blocks = []
    if img.height <= MAX_DIMENSION:
        data = _save_jpeg(img)
        img.close()
        b64 = base64.standard_b64encode(data).decode("utf-8")
        del data
        content_blocks.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
        })
        del b64
    else:
        y = 0
        while y < img.height:
            bottom = min(y + TILE_HEIGHT, img.height)
            tile = img.crop((0, y, img.width, bottom))
            data = _save_jpeg(tile)
            tile.close()
            del tile
            b64 = base64.standard_b64encode(data).decode("utf-8")
            del data
            content_blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
            })
            del b64
            y = bottom - TILE_OVERLAP
            if bottom == img.height:
                break
        img.close()

    gc.collect()
    return content_blocks


def analyze_page(image_bytes_list: list[tuple[bytes, str]], api_key: str) -> dict:
    """상세페이지 이미지를 1회 호출로 분석."""
    client = anthropic.Anthropic(api_key=api_key)

    content = []
    for i, (image_bytes, _media_type) in enumerate(image_bytes_list):
        blocks = _process_single_image(image_bytes)
        content.extend(blocks)
        del blocks
        # 원본 바이트 참조 제거
        image_bytes_list[i] = (b"", "")
        gc.collect()

    content.append({"type": "text", "text": USER_PROMPT})

    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    raw_text = response.content[0].text
    del content, response
    gc.collect()

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
