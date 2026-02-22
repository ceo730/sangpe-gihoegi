"""SVG 와이어프레임 생성기 - recommended_structure를 기반으로 피그마용 초안 생성."""

import html

# 모바일 기준 폭
WIDTH = 375
PADDING = 20
CONTENT_WIDTH = WIDTH - PADDING * 2

# 역할별 색상
ROLE_COLORS = {
    "감정공감": "#ff6b6b",
    "문제제기": "#ffa94d",
    "해결제시": "#51cf66",
    "차별화": "#339af0",
    "증거": "#845ef7",
    "신뢰": "#20c997",
    "CTA": "#f06595",
}

ROLE_BG_COLORS = {
    "감정공감": "#fff5f5",
    "문제제기": "#fff9db",
    "해결제시": "#ebfbee",
    "차별화": "#e7f5ff",
    "증거": "#f3f0ff",
    "신뢰": "#e6fcf5",
    "CTA": "#fff0f6",
}


def _escape(text: str) -> str:
    return html.escape(str(text)) if text else ""


def _wrap_text(text: str, max_chars: int = 28) -> list[str]:
    """텍스트를 max_chars 기준으로 줄바꿈."""
    if not text:
        return [""]
    words = text.replace("\n", " ").split()
    lines = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= max_chars:
            current = f"{current} {word}" if current else word
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def generate_draft_svg(recommended_structure: list[dict], product_name: str = "") -> str:
    """recommended_structure 리스트를 받아 SVG 와이어프레임 문자열을 반환."""
    sections = []
    y_cursor = 0

    # 헤더 영역
    header_height = 80
    header_svg = f"""
    <rect x="0" y="0" width="{WIDTH}" height="{header_height}" fill="#1a1d27"/>
    <text x="{WIDTH // 2}" y="35" text-anchor="middle" fill="#e4e6ef"
          font-size="16" font-weight="bold" font-family="sans-serif">
      {_escape(product_name or "상세페이지 초안")}
    </text>
    <text x="{WIDTH // 2}" y="58" text-anchor="middle" fill="#8b8fa3"
          font-size="11" font-family="sans-serif">
      모바일 와이어프레임 ({WIDTH}px)
    </text>
    """
    sections.append(header_svg)
    y_cursor += header_height + 8

    for item in recommended_structure:
        role = item.get("role", "")
        section_name = item.get("section_name", "섹션")
        order = item.get("order", "")
        height_ratio = item.get("height_ratio", 1.0)
        key_elements = item.get("key_elements", [])
        suggested_copy = item.get("suggested_copy", "")
        design_direction = item.get("design_direction", "")
        color_mood = item.get("color_mood", "")
        aidma_stage = item.get("aidma_stage", "")

        color = ROLE_COLORS.get(role, "#868e96")
        bg_color = ROLE_BG_COLORS.get(role, "#f8f9fa")

        # 섹션 높이 계산 (base 120px * height_ratio)
        base_height = 120
        # 요소 개수에 따라 높이 증가
        element_lines = len(key_elements)
        copy_lines = len(_wrap_text(suggested_copy, 32))
        direction_lines = len(_wrap_text(design_direction, 32))
        extra_lines = element_lines + copy_lines + direction_lines
        section_height = max(
            int(base_height * height_ratio),
            80 + extra_lines * 18
        )

        # 섹션 배경
        section_svg = f"""
    <rect x="4" y="{y_cursor}" width="{WIDTH - 8}" height="{section_height}"
          rx="8" fill="{bg_color}" stroke="{color}" stroke-width="1.5"/>
    """

        # 좌측 역할 바
        section_svg += f"""
    <rect x="4" y="{y_cursor}" width="5" height="{section_height}" rx="2.5" fill="{color}"/>
    """

        # 섹션 번호 + 이름
        section_svg += f"""
    <circle cx="28" cy="{y_cursor + 22}" r="12" fill="{color}"/>
    <text x="28" y="{y_cursor + 26}" text-anchor="middle" fill="white"
          font-size="10" font-weight="bold" font-family="sans-serif">{_escape(str(order))}</text>
    <text x="48" y="{y_cursor + 26}" fill="#333" font-size="13" font-weight="bold"
          font-family="sans-serif">{_escape(section_name)}</text>
    """

        # 역할 태그 + AIDMA 태그
        tag_x = 48
        tag_y = y_cursor + 42
        section_svg += f"""
    <rect x="{tag_x}" y="{tag_y}" width="{len(role) * 13 + 12}" height="18"
          rx="9" fill="{color}" opacity="0.15"/>
    <text x="{tag_x + 6}" y="{tag_y + 13}" fill="{color}" font-size="10"
          font-weight="600" font-family="sans-serif">{_escape(role)}</text>
    """
        if aidma_stage:
            aidma_x = tag_x + len(role) * 13 + 20
            section_svg += f"""
    <rect x="{aidma_x}" y="{tag_y}" width="{len(aidma_stage) * 7 + 12}" height="18"
          rx="9" fill="#6c63ff" opacity="0.15"/>
    <text x="{aidma_x + 6}" y="{tag_y + 13}" fill="#6c63ff" font-size="10"
          font-weight="600" font-family="sans-serif">{_escape(aidma_stage)}</text>
    """

        # 컨텐츠 시작 Y
        content_y = y_cursor + 68

        # 추천 카피
        if suggested_copy:
            section_svg += f"""
    <rect x="{PADDING}" y="{content_y - 4}" width="{CONTENT_WIDTH}" height="{copy_lines * 18 + 8}"
          rx="4" fill="white" stroke="#ddd" stroke-width="0.5"/>
    """
            for ci, line in enumerate(_wrap_text(suggested_copy, 32)):
                section_svg += f"""
    <text x="{PADDING + 8}" y="{content_y + 12 + ci * 18}" fill="#333"
          font-size="11" font-style="italic" font-family="sans-serif">"{_escape(line)}"</text>
    """
            content_y += copy_lines * 18 + 16

        # 핵심 요소
        if key_elements:
            for ei, elem in enumerate(key_elements):
                section_svg += f"""
    <circle cx="{PADDING + 8}" cy="{content_y + 8 + ei * 18}" r="2.5" fill="{color}"/>
    <text x="{PADDING + 18}" y="{content_y + 12 + ei * 18}" fill="#555"
          font-size="10" font-family="sans-serif">{_escape(elem)}</text>
    """
            content_y += element_lines * 18 + 8

        # 디자인 방향
        if design_direction:
            for di, line in enumerate(_wrap_text(design_direction, 36)):
                section_svg += f"""
    <text x="{PADDING + 8}" y="{content_y + 12 + di * 16}" fill="#999"
          font-size="9" font-family="sans-serif">{_escape(line)}</text>
    """

        # 컬러 무드 표시
        if color_mood:
            mood_y = y_cursor + section_height - 20
            section_svg += f"""
    <text x="{WIDTH - PADDING}" y="{mood_y}" text-anchor="end" fill="#aaa"
          font-size="8" font-family="sans-serif">{_escape(color_mood)}</text>
    """

        sections.append(section_svg)
        y_cursor += section_height + 6

    # 푸터
    footer_y = y_cursor + 10
    footer_svg = f"""
    <rect x="0" y="{footer_y}" width="{WIDTH}" height="40" fill="#f8f9fa"/>
    <text x="{WIDTH // 2}" y="{footer_y + 24}" text-anchor="middle" fill="#adb5bd"
          font-size="10" font-family="sans-serif">
      상페기획기 v2.0 — 피그마 초안 와이어프레임
    </text>
    """
    sections.append(footer_svg)
    total_height = footer_y + 50

    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {total_height}"
     width="{WIDTH}" height="{total_height}">
  <defs>
    <style>
      text {{ font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
    </style>
  </defs>
  <rect width="{WIDTH}" height="{total_height}" fill="#ffffff"/>
  {"".join(sections)}
</svg>"""

    return svg
