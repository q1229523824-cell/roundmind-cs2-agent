"""Build the shareable RoundMind Chinese user manual PDF."""

from __future__ import annotations

import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "user-manual.md"
OUTPUT = ROOT / "output" / "pdf" / "RoundMind-CS2-Agent-用户使用手册-v0.1.0.pdf"

PAGE_W, PAGE_H = A4
INK = colors.HexColor("#161A13")
MUTED = colors.HexColor("#66705F")
LINE = colors.HexColor("#DDE4D8")
PANEL = colors.HexColor("#F4F7F1")
ACCENT = colors.HexColor("#B9F227")
ACCENT_DARK = colors.HexColor("#547500")
WARNING = colors.HexColor("#FFF5DB")


def register_fonts() -> None:
    font_dir = Path("C:/Windows/Fonts")
    pdfmetrics.registerFont(TTFont("RoundMindCN", str(font_dir / "msyh.ttc"), subfontIndex=0))
    pdfmetrics.registerFont(TTFont("RoundMindCN-Bold", str(font_dir / "msyhbd.ttc"), subfontIndex=0))


def inline_markup(text: str) -> str:
    value = html.escape(text.strip())
    value = re.sub(
        r"&lt;(https?://[^&]+)&gt;",
        r'<link href="\1" color="#547500"><u>\1</u></link>',
        value,
    )
    value = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)
    value = re.sub(r"`([^`]+)`", r'<font color="#3F5B00">\1</font>', value)
    return value


def make_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "body": ParagraphStyle(
            "BodyCN",
            parent=base["BodyText"],
            fontName="RoundMindCN",
            fontSize=9.3,
            leading=15.5,
            textColor=INK,
            spaceAfter=5,
        ),
        "h2": ParagraphStyle(
            "H2CN",
            parent=base["Heading1"],
            fontName="RoundMindCN-Bold",
            fontSize=17,
            leading=23,
            textColor=INK,
            spaceBefore=12,
            spaceAfter=8,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "H3CN",
            parent=base["Heading2"],
            fontName="RoundMindCN-Bold",
            fontSize=11.5,
            leading=17,
            textColor=ACCENT_DARK,
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "bullet": ParagraphStyle(
            "BulletCN",
            parent=base["BodyText"],
            fontName="RoundMindCN",
            fontSize=9.1,
            leading=14.5,
            leftIndent=12,
            firstLineIndent=-7,
            spaceAfter=3,
            textColor=INK,
        ),
        "code": ParagraphStyle(
            "CodeCN",
            parent=base["Code"],
            fontName="RoundMindCN",
            fontSize=8.2,
            leading=13,
            leftIndent=8,
            rightIndent=8,
            borderColor=LINE,
            borderWidth=0.6,
            borderPadding=7,
            backColor=colors.HexColor("#F7F9F5"),
            textColor=colors.HexColor("#263121"),
            spaceBefore=3,
            spaceAfter=7,
        ),
        "quote": ParagraphStyle(
            "QuoteCN",
            parent=base["BodyText"],
            fontName="RoundMindCN",
            fontSize=9.2,
            leading=15,
            leftIndent=10,
            rightIndent=8,
            borderColor=ACCENT,
            borderWidth=0,
            borderPadding=8,
            backColor=PANEL,
            textColor=MUTED,
            spaceAfter=9,
        ),
        "cover_title": ParagraphStyle(
            "CoverTitle",
            parent=base["Title"],
            fontName="RoundMindCN-Bold",
            fontSize=30,
            leading=39,
            alignment=TA_LEFT,
            textColor=colors.white,
        ),
        "cover_subtitle": ParagraphStyle(
            "CoverSubtitle",
            parent=base["BodyText"],
            fontName="RoundMindCN",
            fontSize=12,
            leading=20,
            textColor=colors.HexColor("#D8DFD2"),
        ),
        "cover_meta": ParagraphStyle(
            "CoverMeta",
            parent=base["BodyText"],
            fontName="RoundMindCN",
            fontSize=9,
            leading=15,
            textColor=colors.HexColor("#AEB8A7"),
        ),
        "toc": ParagraphStyle(
            "TocCN",
            parent=base["BodyText"],
            fontName="RoundMindCN-Bold",
            fontSize=10,
            leading=17,
            textColor=INK,
        ),
        "small": ParagraphStyle(
            "SmallCN",
            parent=base["BodyText"],
            fontName="RoundMindCN",
            fontSize=7.8,
            leading=12,
            textColor=MUTED,
        ),
    }


class ManualDocTemplate(BaseDocTemplate):
    def __init__(self, filename: str):
        super().__init__(
            filename,
            pagesize=A4,
            leftMargin=19 * mm,
            rightMargin=19 * mm,
            topMargin=24 * mm,
            bottomMargin=17 * mm,
            title="RoundMind CS2 Agent 用户使用手册",
            author="RoundMind",
            subject="Windows 本地解析器安装、复盘流程与故障排查",
        )
        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="content",
        )
        self.addPageTemplates(PageTemplate(id="manual", frames=[frame], onPage=self.draw_page))

    @staticmethod
    def draw_page(canvas, doc) -> None:
        canvas.saveState()
        if doc.page == 1:
            canvas.setFillColor(INK)
            canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
            canvas.setFillColor(ACCENT)
            canvas.rect(0, PAGE_H - 16 * mm, PAGE_W, 16 * mm, fill=1, stroke=0)
            canvas.setFillColor(colors.HexColor("#22281F"))
            canvas.circle(PAGE_W - 23 * mm, 28 * mm, 54 * mm, fill=1, stroke=0)
        else:
            canvas.setFont("RoundMindCN", 7.5)
            canvas.setFillColor(MUTED)
            canvas.drawString(19 * mm, 9 * mm, "ROUNDMIND / CS2 AGENT")
            canvas.drawRightString(PAGE_W - 19 * mm, 9 * mm, f"{doc.page - 1}")
        canvas.restoreState()


def cover(styles: dict[str, ParagraphStyle]) -> list:
    items = [Spacer(1, 44 * mm)]
    badge = Table(
        [[Paragraph("WINDOWS LOCAL REVIEW", styles["small"])]],
        colWidths=[55 * mm],
    )
    badge.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), ACCENT),
                ("TEXTCOLOR", (0, 0), (-1, -1), INK),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    items.extend(
        [
            badge,
            Spacer(1, 10 * mm),
            Paragraph("RoundMind<br/>CS2 Agent", styles["cover_title"]),
            Spacer(1, 7 * mm),
            Paragraph("用户使用手册", styles["cover_title"]),
            Spacer(1, 12 * mm),
            Paragraph(
                "从下载安装到 Demo 复盘、结果解读与故障排查。<br/>"
                "写给第一次使用 RoundMind 的玩家。",
                styles["cover_subtitle"],
            ),
            Spacer(1, 34 * mm),
            Paragraph(
                "适用版本 v0.1.0<br/>Windows 10/11 x64<br/>2026-08-26",
                styles["cover_meta"],
            ),
            PageBreak(),
        ]
    )
    return items


def overview(styles: dict[str, ParagraphStyle]) -> list:
    entries = [
        ("01", "快速开始", "下载、解压、启动、上传 Demo"),
        ("02", "完整复盘", "选择玩家、等待解析、阅读结果"),
        ("03", "理解报告", "风险评分、置信度与训练建议"),
        ("04", "解决问题", "连接失败、端口冲突、Demo 异常"),
    ]
    rows = []
    for number, title, desc in entries:
        rows.append(
            [
                Paragraph(f'<font color="#547500"><b>{number}</b></font>', styles["toc"]),
                Paragraph(f"<b>{title}</b><br/><font color='#66705F'>{desc}</font>", styles["toc"]),
            ]
        )
    table = Table(rows, colWidths=[16 * mm, 142 * mm], rowHeights=[18 * mm] * 4)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PANEL),
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return [Paragraph("阅读指南", styles["h2"]), table, Spacer(1, 8 * mm)]


def markdown_story(text: str, styles: dict[str, ParagraphStyle]) -> list:
    lines = text.splitlines()
    items: list = []
    paragraph: list[str] = []
    code: list[str] = []
    in_code = False
    index = 0

    def flush_paragraph() -> None:
        if paragraph:
            items.append(Paragraph(inline_markup(" ".join(paragraph)), styles["body"]))
            paragraph.clear()

    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_paragraph()
            if in_code:
                code_text = "<br/>".join(html.escape(value) for value in code)
                items.append(KeepTogether([Paragraph(code_text, styles["code"])]))
                code.clear()
            in_code = not in_code
            index += 1
            continue
        if in_code:
            code.append(line)
            index += 1
            continue
        if not stripped:
            flush_paragraph()
            index += 1
            continue
        if stripped.startswith("# "):
            index += 1
            continue
        if stripped.startswith("## "):
            flush_paragraph()
            items.append(Paragraph(inline_markup(stripped[3:]), styles["h2"]))
            index += 1
            continue
        if stripped.startswith("### "):
            flush_paragraph()
            items.append(Paragraph(inline_markup(stripped[4:]), styles["h3"]))
            index += 1
            continue
        if stripped.startswith("> "):
            flush_paragraph()
            items.append(Paragraph(inline_markup(stripped[2:]), styles["quote"]))
            index += 1
            continue
        if stripped.startswith("|") and index + 1 < len(lines) and "---" in lines[index + 1]:
            flush_paragraph()
            table_lines = [stripped]
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            rows = []
            for row_index, table_line in enumerate(table_lines):
                cells = [cell.strip() for cell in table_line.strip("|").split("|")]
                style = styles["toc"] if row_index == 0 else styles["small"]
                rows.append([Paragraph(inline_markup(cell), style) for cell in cells])
            table = Table(rows, colWidths=[47 * mm, 111 * mm], repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            items.append(table)
            items.append(Spacer(1, 5 * mm))
            continue
        bullet_match = re.match(r"^[-*]\s+(.+)$", stripped)
        number_match = re.match(r"^(\d+)\.\s+(.+)$", stripped)
        if bullet_match or number_match:
            flush_paragraph()
            if bullet_match:
                prefix, value = "•", bullet_match.group(1)
            else:
                prefix, value = f"{number_match.group(1)}.", number_match.group(2)
            items.append(Paragraph(f"{prefix} {inline_markup(value)}", styles["bullet"]))
            index += 1
            continue
        if stripped == "---":
            flush_paragraph()
            items.append(Spacer(1, 3 * mm))
            index += 1
            continue
        paragraph.append(stripped)
        index += 1

    flush_paragraph()
    return items


def build() -> Path:
    register_fonts()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    styles = make_styles()
    story = cover(styles)
    story.extend(overview(styles))
    story.extend(markdown_story(SOURCE.read_text(encoding="utf-8"), styles))
    story.append(
        KeepTogether(
            [
                Spacer(1, 5 * mm),
                Table(
                    [[Paragraph("GLHF · 让每一场 Demo 都变成下一场能执行的改进。", styles["toc"])]],
                    colWidths=[158 * mm],
                    style=TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), ACCENT),
                            ("BOX", (0, 0), (-1, -1), 0, ACCENT),
                            ("LEFTPADDING", (0, 0), (-1, -1), 10),
                            ("TOPPADDING", (0, 0), (-1, -1), 9),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                        ]
                    ),
                ),
            ]
        )
    )
    ManualDocTemplate(str(OUTPUT)).build(story)
    return OUTPUT


if __name__ == "__main__":
    print(build())
