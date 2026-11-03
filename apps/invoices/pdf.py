"""
Invoice PDF, drawn with ReportLab (pure Python, installs the same way on
Windows, macOS and Linux).
"""

from io import BytesIO
from html import escape as _html_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import re
from pathlib import Path

import arabic_reshaper
from reportlab.lib.fonts import addMapping
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from apps.core.currencies import format_money
from apps.core.models import AgencySettings

# Noto Sans covers Latin (incl. Turkish, Polish, Vietnamese…), Greek and
# Cyrillic; Noto Naskh Arabic covers Urdu and Arabic. The PDF's built-in
# Helvetica only knows Western European letters and prints boxes otherwise.
FONT_DIR = Path(__file__).resolve().parent / "fonts"
for _name, _file in [("Sans", "NotoSans-Regular.ttf"), ("Sans-Bold", "NotoSans-Bold.ttf"),
                     ("Naskh", "NotoNaskhArabic-Regular.ttf"), ("Naskh-Bold", "NotoNaskhArabic-Bold.ttf")]:
    if _name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(_name, str(FONT_DIR / _file)))
addMapping("Sans", 0, 0, "Sans")
addMapping("Sans", 1, 0, "Sans-Bold")
addMapping("Naskh", 0, 0, "Naskh")
addMapping("Naskh", 1, 0, "Naskh-Bold")

# A run of Arabic-script words (letters, joined by spaces), e.g. an Urdu name.
_ARABIC_RUN = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]+"
                         r"(?:\s+[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]+)*")

INK = colors.HexColor("#111111")
MUTED = colors.HexColor("#676560")
LINE = colors.HexColor("#E2E0D9")
SOFT = colors.HexColor("#F6F5F1")
BRAND = colors.HexColor("#111111")


def _style(name, **kw):
    base = {"fontName": "Sans", "fontSize": 9.5, "leading": 13, "textColor": INK}
    base.update(kw)
    return ParagraphStyle(name, **base)


S = {
    "agency": _style("agency", fontName="Sans-Bold", fontSize=16, leading=20),
    "small": _style("small", fontSize=8.5, leading=12, textColor=MUTED),
    "label": _style("label", fontName="Sans-Bold", fontSize=7.5, leading=10, textColor=MUTED),
    "title": _style("title", fontName="Sans-Bold", fontSize=22, leading=26, alignment=TA_RIGHT, textColor=BRAND),
    "right": _style("right", alignment=TA_RIGHT),
    "right_small": _style("right_small", fontSize=8.5, leading=12, alignment=TA_RIGHT, textColor=MUTED),
    "body": _style("body"),
    "bold": _style("bold", fontName="Sans-Bold"),
    "th": _style("th", fontName="Sans-Bold", fontSize=8, textColor=MUTED),
    "th_r": _style("th_r", fontName="Sans-Bold", fontSize=8, textColor=MUTED, alignment=TA_RIGHT),
    "total": _style("total", fontName="Sans-Bold", fontSize=12, leading=16, alignment=TA_RIGHT),
}


def escape(text):
    """
    Make user text safe inside ReportLab's mini-markup (<, >, &), and set
    Urdu/Arabic words in the Naskh font with their letters joined and in
    right-to-left order.
    """
    def arabic(match):
        shaped = arabic_reshaper.reshape(match.group(0))[::-1]
        return f'<font name="Naskh">{_html_escape(shaped, quote=False)}</font>'

    parts, last = [], 0
    for match in _ARABIC_RUN.finditer(text):
        parts.append(_html_escape(text[last:match.start()], quote=False))
        parts.append(arabic(match))
        last = match.end()
    parts.append(_html_escape(text[last:], quote=False))
    return "".join(parts)


def _p(text, style="body"):
    """Paragraph with user text escaped and line breaks kept."""
    return Paragraph(escape(str(text or "")).replace("\n", "<br/>"), S[style])


def _qty(value):
    return f"{int(value)}" if value == value.to_integral_value() else f"{value:.2f}"


def logo_flowable(agency, max_w=48 * mm, max_h=16 * mm):
    """The agency logo scaled to fit, or nothing if there's no (readable) logo."""
    if not agency.logo:
        return []
    try:
        from reportlab.lib.utils import ImageReader
        from reportlab.platypus import Image
        path = agency.logo.path
        w, h = ImageReader(path).getSize()
        scale = min(max_w / w, max_h / h, 1)
        img = Image(path, width=w * scale, height=h * scale)
        img.hAlign = "LEFT"
        return [img, Spacer(1, 4)]
    except Exception:  # a missing or broken logo file must never stop an invoice
        return []


def render_invoice(invoice) -> bytes:
    agency = AgencySettings.load()
    client = invoice.client
    contact = client.primary_contact
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"Invoice {invoice.number}", author=agency.name,
    )
    width = doc.width
    story = []

    # Header: agency on the left, invoice title and dates on the right.
    agency_lines = [line for line in [agency.address, agency.phone, agency.email, agency.website] if line]
    left = [*logo_flowable(agency), _p(agency.name, "agency"), Spacer(1, 3)] + [_p(line, "small") for line in agency_lines]
    status = invoice.status_label.upper()
    status_hex = "#0B7A53" if invoice.is_paid else "#D7263D" if invoice.is_overdue else "#676560"
    right = [
        _p("INVOICE", "title"),
        Spacer(1, 4),
        Paragraph(f"<b>{escape(invoice.number)}</b>", S["right"]),
        _p(f"Issued {invoice.issue_date:%d %b %Y}", "right_small"),
        _p(f"Due {invoice.due_date:%d %b %Y}", "right_small"),
        Spacer(1, 4),
        Paragraph(f'<font color="{status_hex}"><b>{status}</b></font>', S["right"]),
    ]
    header = Table([[left, right]], colWidths=[width * 0.58, width * 0.42])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [header, Spacer(1, 14 * mm)]

    # Bill to
    bill = [_p("BILL TO", "label"), Spacer(1, 3), _p(client.company, "bold")]
    if contact:
        bill.append(_p(contact.name))
        bill += [_p(x, "small") for x in (contact.email, contact.phone) if x]
    if client.address:
        bill.append(_p(client.address, "small"))
    story += [*bill, Spacer(1, 9 * mm)]

    # Lines
    rows = [[_p("DESCRIPTION", "th"), _p("QTY", "th_r"), _p("PRICE", "th_r"), _p("AMOUNT", "th_r")]]
    for line in invoice.lines.all():
        rows.append([
            _p(line.description),
            Paragraph(_qty(line.quantity), S["right"]),
            Paragraph(escape(format_money(line.unit_price, invoice.currency)), S["right"]),
            Paragraph(escape(format_money(line.amount, invoice.currency)), S["right"]),
        ])
    table = Table(rows, colWidths=[width * 0.50, width * 0.10, width * 0.20, width * 0.20], repeatRows=1)
    table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (1, 0), (-1, -1), 6),
    ]))
    story += [table, Spacer(1, 5 * mm)]

    total = Table(
        [[_p("Total", "right_small"), Paragraph(escape(format_money(invoice.total, invoice.currency)), S["total"])]],
        colWidths=[width * 0.6, width * 0.4],
    )
    total.setStyle(TableStyle([
        ("BACKGROUND", (1, 0), (1, 0), SOFT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story += [total]
    if invoice.is_paid and invoice.paid_at:
        story += [Spacer(1, 2 * mm), _p(f"Paid on {invoice.paid_at:%d %b %Y}. Thank you!", "right_small")]

    # Payment details and notes
    extra = []
    if agency.payment_details and not invoice.is_paid:
        extra += [_p("HOW TO PAY", "label"), Spacer(1, 3), _p(agency.payment_details), Spacer(1, 6 * mm)]
    if invoice.notes:
        extra += [_p("NOTES", "label"), Spacer(1, 3), _p(invoice.notes)]
    if extra:
        story += [Spacer(1, 12 * mm), KeepTogether(extra)]

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def _footer(canvas, doc):
    """Small credit line at the bottom of every page (demo edition)."""
    canvas.saveState()
    canvas.setFont("Sans", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawCentredString(A4[0] / 2, 10 * mm, "Made with Kairos")
    canvas.restoreState()
