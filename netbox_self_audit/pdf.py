"""PDF rendering of the NetBoxSelf Audit (reportlab)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from .common import SEVERITY_COLOR, format_time as _format_time, seconds
from .i18n import language_of, tr


FONT_DIR = Path(__file__).resolve().parent / "fonts"
FONT = "SelfAuditSans"
FONT_BOLD = "SelfAuditSans-Bold"


def _register_fonts() -> None:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if FONT in pdfmetrics.getRegisteredFontNames():
        return
    # DejaVu Sans covers Slovak diacritics (the reportlab built-in fonts do not).
    pdfmetrics.registerFont(TTFont(FONT, str(FONT_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(FONT_DIR / "DejaVuSans-Bold.ttf")))


def _encryption(password: str):
    from reportlab.lib.pdfencrypt import StandardEncryption

    return StandardEncryption(password, canPrint=1, canModify=0, canCopy=1, canAnnotate=0, strength=128)


def build_pdf(settings, report: dict, subject: str, password: str | None = None, view: str | None = None) -> bytes:
    """Render the NetBoxSelf Audit as PDF (grouped by object or listed by time); a password encrypts it (128-bit, printing allowed)."""
    from .rules import group_tree, view_of

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape
    from django.utils import timezone

    _register_fonts()
    lang = language_of(settings)
    base = ParagraphStyle("base", fontName=FONT, fontSize=8.5, leading=11)
    small = ParagraphStyle("small", parent=base, fontSize=8, textColor=colors.HexColor("#495057"))
    header = ParagraphStyle("header", parent=base, fontName=FONT_BOLD, textColor=colors.HexColor("#212529"))
    title = ParagraphStyle("title", parent=base, fontName=FONT_BOLD, fontSize=15, leading=19, spaceAfter=2)
    badge = ParagraphStyle("badge", parent=base, fontName=FONT_BOLD, textColor=colors.white, alignment=TA_CENTER)

    generated = timezone.localtime().strftime(getattr(settings, "datetime_format", "%d.%m.%Y %H:%M:%S"))
    report_header = (getattr(settings, "report_header", "") or "").strip()
    story = [Paragraph(escape(report_header), header)] if report_header else []
    story += [
        Paragraph(escape(tr("self.title", lang)), title),
        Paragraph(escape(tr("report.period", lang, period=report["period_label"]) + "    ·    " + tr("report.generated", lang, time=generated)
                  + (f" ({tr('self.took', lang, time=seconds(report['duration'], lang))})" if report.get("duration") is not None else "")), small),
        Spacer(1, 3 * mm),
        Paragraph(escape(subject), header),
        Spacer(1, 2 * mm),
    ]
    group_title = ParagraphStyle("group", parent=base, fontName=FONT_BOLD, fontSize=12, leading=15, spaceBefore=8, spaceAfter=2)
    object_title = ParagraphStyle("object", parent=base, fontName=FONT_BOLD, fontSize=10.5, leading=13)
    page_width = landscape(A4)[0] - 24 * mm

    def change_cell(entry):
        change = escape(entry["text"])
        change += "".join(f'<br/><font color="#495057">{escape(label)}: <b>{escape(value)}</b></font>' for label, value in entry.get("fields", []))
        if entry["kind"] in ("list", "lines"):
            change += "".join(f'<br/><font color="#198754">+ {escape(item)}</font>' for item in entry["added"])
            change += "".join(f'<br/><font color="#dc3545">− {escape(item)}</font>' for item in entry["removed"])
        return Paragraph(change, base)

    def table(entries, with_object, title=None):
        """Changes as a table; with a title the table is an object frame whose name row repeats after a page break."""
        labels = [tr("field.time", lang), tr("field.severity", lang), tr("self.col_user", lang)]
        widths = [32 * mm, 26 * mm, 30 * mm]
        if with_object:
            labels.append(tr("self.col_object", lang))
            widths.append(56 * mm)
        labels.append(tr("field.change", lang))
        widths.append(page_width - sum(widths))
        rows = []
        first = 0
        if title:
            rows.append([Paragraph(escape(title), object_title)] + [""] * (len(labels) - 1))
            first = 1
        rows.append([Paragraph(escape(label), header) for label in labels])
        styles = [
            ("BACKGROUND", (0, first), (-1, first), colors.HexColor("#e9ecef")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, first), (-1, -1), 0.4, colors.HexColor("#dee2e6")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if title:
            styles += [
                ("SPAN", (0, 0), (-1, 0)),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f3f5")),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#adb5bd")),
                ("TOPPADDING", (0, 0), (-1, 0), 2 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 2 * mm),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#adb5bd")),
            ]
        for index, entry in enumerate(entries, start=first + 1):
            row = [
                Paragraph(escape(_format_time(entry["when"], settings)), base),
                Paragraph(escape(entry["severity_label"]), badge),
                Paragraph(escape(entry["user"] or "-"), base),
            ]
            if with_object:
                row.append(Paragraph(escape(f"{entry['object_type']}: {entry['object']}"), base))
            row.append(change_cell(entry))
            rows.append(row)
            styles.append(("BACKGROUND", (1, index), (1, index), colors.HexColor(SEVERITY_COLOR[entry["severity"]])))
        result = Table(rows, colWidths=widths, repeatRows=first + 1)
        result.setStyle(TableStyle(styles))
        return result

    if not report["entries"]:
        story.append(Paragraph(escape(tr("self.no_changes", lang)), base))
    elif view_of(settings, view) == "object":
        for group in group_tree(report["entries"]):
            heading = Paragraph(escape(f"{group['label']} ({tr('self.tree_changes', lang, count=group['count'])})"), group_title)
            for position, obj in enumerate(group["objects"]):
                name = str(obj["name"]) + (f" ({tr('self.deleted_mark', lang)})" if obj["deleted"] else "")
                # An object stays on one page (moved to the next page when it does not fit); only an object
                # longer than a whole page is split, and its name row is repeated on the next page.
                block = [heading] if position == 0 else []
                block.append(table(obj["entries"], with_object=False, title=name))
                story.append(KeepTogether(block))
                story.append(Spacer(1, 3 * mm))
    else:
        story.append(table(report["entries"], with_object=True))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(FONT, 7.5)
        canvas.setFillColor(colors.HexColor("#6c757d"))
        canvas.drawString(12 * mm, 8 * mm, subject[:150])
        canvas.drawRightString(landscape(A4)[0] - 12 * mm, 8 * mm, tr("report.page", lang, page=doc.page))
        canvas.restoreState()

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=14 * mm,
        title=subject, author="NetBoxSelf Audit", **({"encrypt": _encryption(password)} if password else {}),
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
