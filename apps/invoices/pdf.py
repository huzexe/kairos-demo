"""
Invoice PDF, drawn with ReportLab (pure Python, installs the same way on
Windows, macOS and Linux).
"""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.core.currencies import format_money
from apps.core.models import AgencySettings

INK = colors.HexColor("#121826")
MUTED = colors.HexColor("#6b7486")
LINE = colors.HexColor("#e3e6eb")
SOFT = colors.HexColor("#f4f5f7")
BRAND = colors.HexColor("#0a7d69")


def _style(name, **kw):
    base = {"fontName": "Helvetica", "fontSize": 9.5, "leading": 13, "textColor": INK}
    base.update(kw)
    return ParagraphStyle(name, **base)


S = {
    "agency": _style("agency", fontName="Helvetica-Bold", fontSize=16, leading=20),
    "small": _style("small", fontSize=8.5, leading=12, textColor=MUTED),
    "label": _style("label", fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=MUTED),
    "title": _style("title", fontName="Helvetica-Bold", fontSize=22, leading=26, alignment=TA_RIGHT, textColor=BRAND),
    "right": _style("right", alignment=TA_RIGHT),
    "right_small": _style("right_small", fontSize=8.5, leading=12, alignment=TA_RIGHT, textColor=MUTED),
    "body": _style("body"),
    "bold": _style("bold", fontName="Helvetica-Bold"),
    "th": _style("th", fontName="Helvetica-Bold", fontSize=8, textColor=MUTED),
    "th_r": _style("th_r", fontName="Helvetica-Bold", fontSize=8, textColor=MUTED, alignment=TA_RIGHT),
    "total": _style("total", fontName="Helvetica-Bold", fontSize=12, leading=16, alignment=TA_RIGHT),
}


def _p(text, style="body"):
    """Paragraph with user text escaped and line breaks kept."""
    return Paragraph(escape(str(text or "")).replace("\n", "<br/>"), S[style])


def _qty(value):
    return f"{int(value)}" if value == value.to_integral_value() else f"{value:.2f}"


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
    left = [_p(agency.name, "agency"), Spacer(1, 3)] + [_p(line, "small") for line in agency_lines]
    status = invoice.status_label.upper()
    status_hex = "#0f7b4a" if invoice.is_paid else "#c62828" if invoice.is_overdue else "#6b7486"
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

    doc.build(story)
    return buf.getvalue()
