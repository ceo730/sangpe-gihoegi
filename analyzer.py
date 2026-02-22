import base64
import gc
import io
import json
import logging
import re
import time

import anthropic
from PIL import Image

from prompt import SYSTEM_PROMPT, USER_PROMPT

MAX_TILE_BYTES = 800_000
MAX_DIMENSION = 7900
TILE_HEIGHT = 4000
TILE_OVERLAP = 200
TARGET_WIDTH = 1100

MAX_RETRIES = 2
RETRY_DELAY = 3  # seconds

logger = logging.getLogger(__name__)


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


def _process_single_image(image_bytes: bytes) -> list[dict]:
    """이미지 1장 처리 → API content 블록 리스트. 메모리 즉시 해제."""
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode == "P":
        img = img.convert("RGBA")

    if img.width > TARGET_WIDTH:
        ratio = TARGET_WIDTH / img.width
        img = img.resize((TARGET_WIDTH, int(img.height * ratio)), Image.LANCZOS)

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


def _call_api_with_retry(client, content: list) -> str:
    """API 호출 + 서버 에러 시 최대 MAX_RETRIES회 재시도."""
    last_error = None
    for attempt in range(1 + MAX_RETRIES):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=32000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
            )
            return response.content[0].text
        except anthropic.APIStatusError as e:
            last_error = e
            if e.status_code >= 500 and attempt < MAX_RETRIES:
                logger.warning(
                    f"API 서버 에러 (HTTP {e.status_code}), "
                    f"{RETRY_DELAY}초 후 재시도 ({attempt + 1}/{MAX_RETRIES})"
                )
                time.sleep(RETRY_DELAY)
            else:
                raise
        except anthropic.APIConnectionError as e:
            last_error = e
            if attempt < MAX_RETRIES:
                logger.warning(
                    f"API 연결 에러, {RETRY_DELAY}초 후 재시도 ({attempt + 1}/{MAX_RETRIES})"
                )
                time.sleep(RETRY_DELAY)
            else:
                raise
    raise last_error


def analyze_page(image_bytes_list: list[tuple[bytes, str]], api_key: str) -> dict:
    """상세페이지 이미지를 1회 호출로 분석."""
    client = anthropic.Anthropic(api_key=api_key)

    content = []
    for i, (image_bytes, _media_type) in enumerate(image_bytes_list):
        blocks = _process_single_image(image_bytes)
        content.extend(blocks)
        del blocks
        image_bytes_list[i] = (b"", "")
        gc.collect()

    content.append({"type": "text", "text": USER_PROMPT})

    raw_text = _call_api_with_retry(client, content)
    del content
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
