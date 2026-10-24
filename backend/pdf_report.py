"""Three metric cards per authorized Facebook Page, with embedded Khmer fonts."""
import io
import math
import unicodedata
from pathlib import Path
from threading import Lock

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont, shapeStr
from reportlab.pdfgen.canvas import Canvas

FONT_LOCK = Lock()
GREEN = "#20846d"
DARK = "#29483b"
MUTED = "#738477"
LABELS = {"views": "Total views", "interactions": "Content interactions", "followers": "Total followers"}


def register_fonts():
    with FONT_LOCK:
        folder = Path(__file__).parent / "fonts"
        for name, filename in [("Pagepulse", "NotoSans-Regular.ttf"), ("PagepulseBold", "NotoSans-Bold.ttf"),
                               ("PagepulseKhmer", "NotoSansKhmer-Regular.ttf")]:
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, str(folder / filename), shapable=True))


def text(canvas, value, x, y, size=10, color=DARK, bold=False, max_width=None):
    value = str(value).replace("\n", " ").replace("\r", " ")
    khmer = any("\u1780" <= char <= "\u17ff" for char in value)
    latin = "PagepulseBold" if bold else "Pagepulse"
    coverage = pdfmetrics.getFont("PagepulseKhmer").face.charToGlyph
    runs = []
    for char in value:
        if unicodedata.category(char) == "Cf":
            continue
        font = "PagepulseKhmer" if khmer and ord(char) in coverage else latin
        if runs and runs[-1][0] == font:
            runs[-1] = (font, runs[-1][1]+char)
        else:
            runs.append((font, char))
    def prepare(font_size):
        prepared = []
        for font, chars in runs:
            shaped = shapeStr(chars, font, font_size, force=True) if font == "PagepulseKhmer" else chars
            width = sum(item.x_advance for item in shaped.__shapeData__) * font_size / 1000 if font == "PagepulseKhmer" else pdfmetrics.stringWidth(chars, font, font_size)
            prepared.append((font, shaped, width))
        return prepared
    prepared = prepare(size)
    width = sum(run[2] for run in prepared)
    if max_width and width > max_width:
        size = max(7, size * max_width / width)
        prepared = prepare(size)
    canvas.setFillColor(HexColor(color))
    # ActualText retains the original name for accessible PDF readers after shaping.
    if khmer:
        encoded = (b"\xfe\xff" + value.encode("utf-16-be")).hex()
        canvas._code.append(f"/Span << /ActualText <{encoded}> >> BDC")
    for font, shaped, width in prepared:
        canvas.setFont(font, size)
        canvas.drawString(x, y, shaped)
        x += width
    if khmer:
        canvas._code.append("EMC")


def sparkline(canvas, values, x, y, width, height):
    available = [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
    if len(available) < 2:
        return
    low, high = min(available), max(available)
    path = canvas.beginPath()
    connected = False
    for index, value in enumerate(values):
        if value is None:
            connected = False
            continue
        px = x + index / max(1, len(values)-1) * width
        py = y + (value-low) / (high-low or 1) * height
        if connected:
            path.lineTo(px, py)
        else:
            path.moveTo(px, py)
        connected = True
    canvas.setStrokeColor(HexColor(GREEN))
    canvas.setLineWidth(.8)
    canvas.drawPath(path)


def metric_icon(canvas, key, x, y):
    canvas.setStrokeColor(HexColor("#84a28d"))
    canvas.setLineWidth(.8)
    if key == "views":
        canvas.ellipse(x-5, y-2.7, x+5, y+2.7, fill=0)
        canvas.circle(x, y, 1.4, fill=0)
    elif key == "interactions":
        canvas.roundRect(x-4, y-3, 8, 6, 2, fill=0)
        canvas.line(x-2, y-3, x-3, y-5)
    else:
        canvas.circle(x-1, y+1.8, 2, fill=0)
        canvas.arc(x-5, y-6, x+3, y, 0, 180)
        canvas.arc(x+1, y-4, x+7, y+1, -10, 110)


def metric_card(canvas, key, report, x, y, width, height):
    metric = report["metrics"][key] if report else {}
    canvas.setFillColor(HexColor("#fbfdfb" if key == "views" else "#ffffff"))
    canvas.setStrokeColor(HexColor("#d5e3d9"))
    canvas.setLineWidth(.7)
    canvas.roundRect(x, y, width, height, 5, fill=1, stroke=1)
    text(canvas, LABELS[key], x+13, y+height-19, 8.5, MUTED)
    metric_icon(canvas, key, x+width-18, y+height-16)
    value = metric.get("value")
    text(canvas, f"{value:,.0f}" if value is not None else "N/A", x+13, y+height-50, 23, DARK)
    growth = metric.get("growth")
    if growth is None:
        text(canvas, "Not available" if value is None else "No comparable period", x+13, y+19, 7.5, MUTED)
    else:
        direction = "+" if growth >= 0 else ""
        text(canvas, f"{direction}{growth:g}%", x+13, y+22, 8, GREEN if growth >= 0 else "#b15b50", bold=True)
        text(canvas, "vs. previous period", x+13, y+10, 6.5, MUTED)
    if metric.get("status") == "partial":
        text(canvas, "Partial data", x+width-69, y+height-34, 6.5, MUTED)
    if report and value is not None:
        sparkline(canvas, [row.get(key) for row in report["series"]], x+width-94, y+12, 79, 20)


def render_pages_pdf(entries, since, until, demo=False):
    register_fonts()
    output = io.BytesIO()
    width, height = landscape(A4)
    canvas = Canvas(output, pagesize=(width, height), pageCompression=1)
    canvas.setTitle(f"Facebook Page Analytics - {since} to {until}")
    canvas.setAuthor("Pagepulse")
    total_sheets = max(1, math.ceil(len(entries)/3))
    unavailable = sum(bool(entry.get("error")) or not entry.get("report") or
                      any(entry["report"]["metrics"][key]["status"] != "available" for key in LABELS) for entry in entries)
    for sheet in range(total_sheets):
        canvas.setFillColor(HexColor("#f5f8f5"))
        canvas.rect(0, 0, width, height, fill=1, stroke=0)
        text(canvas, "pagepulse.", 34, height-37, 19, GREEN, bold=True)
        text(canvas, "Facebook Page Analytics", 34, height-63, 17, DARK, bold=True)
        text(canvas, f"{since} to {until}  |  {len(entries)} {'sample' if demo else 'authorized'} Pages", 34, height-81, 8.5, MUTED)
        if demo:
            text(canvas, "SAMPLE DATA", width-140, height-37, 10, GREEN, bold=True)
        elif unavailable:
            text(canvas, f"{unavailable} Pages have limited or missing data", width-280, height-37, 8, MUTED)
        for row, entry in enumerate(entries[sheet*3:sheet*3+3]):
            top = height-109-row*143
            page = entry["page"]
            text(canvas, page.get("name", "Facebook Page"), 34, top, 13, DARK, bold=True, max_width=580)
            text(canvas, f"Page ID: {page['id']}", width-211, top, 7.5, MUTED)
            gap = 12
            card_width = (width-68-2*gap)/3
            for index, key in enumerate(LABELS):
                metric_card(canvas, key, entry.get("report"), 34+index*(card_width+gap), top-102, card_width, 88)
            if entry.get("error"):
                text(canvas, entry["error"], 34, top-116, 6.7, "#9e5247", max_width=width-68)
        canvas.setStrokeColor(HexColor("#dfe7df"))
        canvas.line(34, 39, width-34, 39)
        text(canvas, "Followers use the final reporting-day snapshot. Growth compares the previous period. Missing values remain unavailable.", 34, 26, 6.5, MUTED)
        text(canvas, f"{'SAMPLE DATA' if demo else 'Meta Graph API'}  |  {sheet+1} / {total_sheets}", width-169, 13, 6.5, MUTED)
        canvas.showPage()
    canvas.save()
    return output.getvalue()
