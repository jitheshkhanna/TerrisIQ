"""Three-page due-diligence PDF.

WeasyPrint (the brief's suggestion) needs cairo/pango system libraries that are not
installable here, so the report is drawn with ReportLab instead. That turns out to be
an advantage for the locality map: we already hold the flood polygons as geometry, so
the map is drawn as true vectors offline rather than fetched as a raster tile image.
"""
import datetime
import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, KeepTogether,
                                PageBreak, PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)

from app.core import cities as city_registry
from app.core.geo import get_store, point_utm
from app.core.scoring import DISCLAIMER

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm

GRADE_COLORS = {
    "A": colors.HexColor("#15803d"),
    "B": colors.HexColor("#65a30d"),
    "C": colors.HexColor("#ca8a04"),
    "D": colors.HexColor("#ea580c"),
    "F": colors.HexColor("#dc2626"),
}
CATEGORY_COLORS = {
    "Very High": colors.HexColor("#dc2626"),
    "High": colors.HexColor("#f97316"),
    "Moderate": colors.HexColor("#eab308"),
    "Low": colors.HexColor("#a3e635"),
    "Very Low": colors.HexColor("#dcfce7"),
}
INK = colors.HexColor("#111827")
MUTED = colors.HexColor("#6b7280")
RULE = colors.HexColor("#e5e7eb")


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontName="Helvetica-Bold",
                                fontSize=20, leading=24, textColor=INK, alignment=TA_LEFT),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="Helvetica-Bold",
                             fontSize=13, leading=16, textColor=INK,
                             spaceBefore=10, spaceAfter=5),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontName="Helvetica-Bold",
                             fontSize=10.5, leading=13, textColor=INK,
                             spaceBefore=7, spaceAfter=3),
        "body": ParagraphStyle("b", parent=base["BodyText"], fontName="Helvetica",
                               fontSize=9.5, leading=13.5, textColor=INK),
        "small": ParagraphStyle("s", parent=base["BodyText"], fontName="Helvetica",
                                fontSize=8, leading=11, textColor=MUTED),
        "warn": ParagraphStyle("w", parent=base["BodyText"], fontName="Helvetica",
                               fontSize=9, leading=12.5, textColor=colors.HexColor("#7f1d1d"),
                               leftIndent=8, spaceAfter=2),
    }


class GradeBlock(Flowable):
    """Large grade letter with the composite score and the three sub-scores."""

    def __init__(self, result, width):
        super().__init__()
        self.result = result
        self.width = width
        self.height = 50 * mm

    def draw(self):
        c = self.canv
        grade = self.result["composite_grade"]
        colour = GRADE_COLORS.get(grade, MUTED)

        box = 38 * mm
        c.setFillColor(colour)
        c.roundRect(0, 4 * mm, box, box, 3 * mm, stroke=0, fill=1)
        # Level 1-5 as filled bars inside the box, instead of a letter nobody decodes.
        level = self.result.get("level") or 1
        bar_w, gap = 4.2 * mm, 1.6 * mm
        total = 5 * bar_w + 4 * gap
        x0 = (box - total) / 2.0
        for i in range(5):
            c.setFillColor(INK if i < level else colors.Color(1, 1, 1, alpha=0.55))
            h = (6 + i * 3.2) * mm
            c.roundRect(x0 + i * (bar_w + gap), 4 * mm + 8 * mm, bar_w, h, 1 * mm,
                        stroke=0, fill=1)

        x = box + 9 * mm
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 24)
        c.drawString(x, 4 * mm + box - 11 * mm, "%d/100" % self.result["composite_score"])
        c.setFont("Helvetica", 11)
        c.setFillColor(colour)
        c.drawString(x, 4 * mm + box - 17 * mm,
                     self.result.get("verdict") or self.result["composite_band"])
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 8)
        c.drawString(x, 4 * mm + box - 22 * mm,
                     "Confidence in underlying data coverage: %s" % self.result["confidence"])

        bar_x = x
        bar_y = 3.5 * mm
        bar_w = self.width - bar_x - 2 * mm
        # A city with no groundwater evidence has no scarcity block at all; show the
        # row as "no data" rather than drawing a zero bar, which would read as "safe".
        weights = self.result.get("weights") or {}
        labels = [("Flood", self.result.get("flood"), weights.get("flood")),
                  ("Contamination", self.result.get("contamination"), weights.get("contamination")),
                  ("Scarcity", self.result.get("scarcity"), weights.get("scarcity"))]
        row_h = 5.0 * mm
        for i, (name, block, weight) in enumerate(labels):
            y = bar_y + (2 - i) * row_h
            c.setFont("Helvetica", 7.5)
            c.setFillColor(MUTED)
            c.drawString(bar_x, y + 1.2 * mm,
                         "%s (x%.2f)" % (name, weight) if weight else name)
            track_x = bar_x + 30 * mm
            track_w = max(bar_w - 42 * mm, 10 * mm)

            if block is None:
                c.setFont("Helvetica-Oblique", 7.5)
                c.setFillColor(MUTED)
                c.drawString(track_x, y + 1.2 * mm, "not scored in this city")
                continue

            c.setFillColor(RULE)
            c.roundRect(track_x, y, track_w, 3 * mm, 1.5 * mm, stroke=0, fill=1)
            frac = max(0.0, min(1.0, block["score"] / 100.0))
            if frac > 0:
                c.setFillColor(GRADE_COLORS.get(block["grade"], MUTED))
                c.roundRect(track_x, y, max(track_w * frac, 1.5 * mm), 3 * mm,
                            1.5 * mm, stroke=0, fill=1)
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 7.5)
            c.drawRightString(self.width, y + 1.2 * mm, "%d" % block["score"])


class LocalityMap(Flowable):
    """Vector mini-map: flood categories, water, drains and the parcel marker."""

    def __init__(self, city, lat, lng, width, height=72 * mm, radius_m=900.0):
        super().__init__()
        self.city = city
        self.lat, self.lng = lat, lng
        self.width, self.height = width, height
        self.radius_m = radius_m

    def _project(self, cx, cy):
        """Build a UTM-metres -> PDF-points transform centred on the parcel."""
        scale = min(self.width, self.height) / (2.0 * self.radius_m)
        ox, oy = self.width / 2.0, self.height / 2.0

        def tx(coords):
            out = []
            for x, y in coords:
                out.append((ox + (x - cx) * scale, oy + (y - cy) * scale))
            return out
        return tx

    def _polys(self, geom):
        if geom.geom_type == "Polygon":
            return [geom]
        if geom.geom_type == "MultiPolygon":
            return list(geom.geoms)
        return []

    def _lines(self, geom):
        if geom.geom_type == "LineString":
            return [geom]
        if geom.geom_type == "MultiLineString":
            return list(geom.geoms)
        return []

    def draw(self):
        c = self.canv
        store = get_store(self.city)
        pt = point_utm(self.city, self.lat, self.lng)
        cx, cy = pt.x, pt.y
        tx = self._project(cx, cy)

        c.saveState()
        c.setFillColor(colors.HexColor("#f8fafc"))
        c.setStrokeColor(RULE)
        c.rect(0, 0, self.width, self.height, stroke=1, fill=1)
        p = c.beginPath()
        p.rect(0, 0, self.width, self.height)
        c.clipPath(p, stroke=0, fill=0)

        # Flood categories underneath.
        fz = store.layer("flood_zones")
        for i in fz.within(pt, self.radius_m * 1.5):
            cat = fz.props[i].get("CATEGORY")
            colour = CATEGORY_COLORS.get(cat)
            if colour is None:
                continue
            for poly in self._polys(fz.geoms_utm[i]):
                pts = tx(list(poly.exterior.coords))
                if len(pts) < 3:
                    continue
                path = c.beginPath()
                path.moveTo(*pts[0])
                for xy in pts[1:]:
                    path.lineTo(*xy)
                path.close()
                c.setFillColor(colour)
                c.setStrokeColor(colour)
                c.setLineWidth(0.2)
                c.drawPath(path, stroke=0, fill=1)

        # Waterbodies.
        wb = store.layer("waterbodies")
        water = colors.HexColor("#0ea5e9")
        for i in wb.within(pt, self.radius_m * 1.5):
            geom = wb.geoms_utm[i]
            for poly in self._polys(geom):
                pts = tx(list(poly.exterior.coords))
                if len(pts) < 3:
                    continue
                path = c.beginPath()
                path.moveTo(*pts[0])
                for xy in pts[1:]:
                    path.lineTo(*xy)
                path.close()
                c.setFillColor(water)
                c.drawPath(path, stroke=0, fill=1)
            for line in self._lines(geom):
                pts = tx(list(line.coords))
                if len(pts) < 2:
                    continue
                c.setStrokeColor(water)
                c.setLineWidth(1.1)
                c.lines([(pts[j][0], pts[j][1], pts[j + 1][0], pts[j + 1][1])
                         for j in range(len(pts) - 1)])

        # Storm water drains.
        swd = store.layer("swd")
        for i in swd.within(pt, self.radius_m * 1.2):
            bad = (swd.props[i].get("STATUS") or "").strip().lower() == "bad"
            c.setStrokeColor(colors.HexColor("#b91c1c") if bad else colors.HexColor("#1d4ed8"))
            c.setLineWidth(0.9 if bad else 0.6)
            for line in self._lines(swd.geoms_utm[i]):
                pts = tx(list(line.coords))
                if len(pts) < 2:
                    continue
                c.lines([(pts[j][0], pts[j][1], pts[j + 1][0], pts[j + 1][1])
                         for j in range(len(pts) - 1)])

        # Parcel marker.
        ox, oy = self.width / 2.0, self.height / 2.0
        c.setStrokeColor(colors.white)
        c.setLineWidth(2.4)
        c.circle(ox, oy, 3.6 * mm, stroke=1, fill=0)
        c.setStrokeColor(colors.black)
        c.setLineWidth(1.4)
        c.circle(ox, oy, 3.6 * mm, stroke=1, fill=0)
        c.setFillColor(colors.black)
        c.circle(ox, oy, 1.2 * mm, stroke=0, fill=1)

        # Scale bar.
        scale = min(self.width, self.height) / (2.0 * self.radius_m)
        bar_m = 200.0
        bar_len = bar_m * scale
        c.setStrokeColor(INK)
        c.setLineWidth(1.1)
        c.line(6 * mm, 5 * mm, 6 * mm + bar_len, 5 * mm)
        c.line(6 * mm, 4 * mm, 6 * mm, 6 * mm)
        c.line(6 * mm + bar_len, 4 * mm, 6 * mm + bar_len, 6 * mm)
        c.setFont("Helvetica", 6.5)
        c.setFillColor(INK)
        c.drawString(6 * mm, 6.6 * mm, "200 m")
        c.restoreState()


class Legend(Flowable):
    def __init__(self, width):
        super().__init__()
        self.width = width
        self.height = 9 * mm

    def draw(self):
        c = self.canv
        items = [("Very High", CATEGORY_COLORS["Very High"]),
                 ("High", CATEGORY_COLORS["High"]),
                 ("Moderate", CATEGORY_COLORS["Moderate"]),
                 ("Low", CATEGORY_COLORS["Low"]),
                 ("Very Low", CATEGORY_COLORS["Very Low"]),
                 ("Water", colors.HexColor("#0ea5e9")),
                 ("Drain", colors.HexColor("#1d4ed8")),
                 ("Drain (bad)", colors.HexColor("#b91c1c"))]
        x = 0
        c.setFont("Helvetica", 7)
        for label, colour in items:
            c.setFillColor(colour)
            c.rect(x, 3 * mm, 3.2 * mm, 3.2 * mm, stroke=0, fill=1)
            c.setFillColor(MUTED)
            c.drawString(x + 4.2 * mm, 3.8 * mm, label)
            x += 4.2 * mm + c.stringWidth(label, "Helvetica", 7) + 5 * mm


def _metric_table(rows, width):
    data = [[Paragraph("<b>%s</b>" % k, _styles()["small"]),
             Paragraph(str(v), _styles()["small"])] for k, v in rows]
    table = Table(data, colWidths=[width * 0.42, width * 0.58])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return table


def _dimension_section(story, st, title, weight, block, width):
    grade = block["grade"]
    header = Table(
        [[Paragraph("<b>%s</b>" % title, st["h3"]),
          Paragraph('<font color="#%s"><b>%s &nbsp;%d/100</b></font>'
                    % (GRADE_COLORS.get(grade, MUTED).hexval()[2:],
                       block.get("verdict") or grade, block["score"]),
                    ParagraphStyle("r", parent=st["h3"], alignment=2))]],
        colWidths=[width * 0.62, width * 0.38])
    header.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    story.append(header)
    story.append(Paragraph("Composite weight %.2f &middot; data confidence: %s"
                           % (weight, block["confidence"]), st["small"]))
    story.append(Spacer(1, 3))

    if block["components"]:
        rows = [(c["label"], "+%.0f pts" % c["points"] if c["points"] >= 0
                 else "%.0f pts" % c["points"]) for c in block["components"]]
        story.append(_metric_table(rows, width))
    if block["warnings"]:
        story.append(Spacer(1, 4))
        for warning in block["warnings"]:
            story.append(Paragraph("&#9888;&nbsp; %s" % warning, st["warn"]))
    story.append(Spacer(1, 8))


def _key_findings(result, limit=6):
    """The warnings a buyer should read first, heaviest-weighted dimension first."""
    out = []
    for label, key in (("Flood", "flood"), ("Contamination", "contamination"),
                       ("Water scarcity", "scarcity")):
        block = result.get(key)
        if not block:
            continue  # this city publishes nothing for that dimension
        for warning in block["warnings"]:
            out.append((label, warning))
    return out[:limit]


_PLAIN_VERDICT = {
    1: "On the hazards we can measure, this plot looks low-risk.",
    2: "This plot looks mostly low-risk, with a few things worth checking.",
    3: "This plot carries moderate risk — read the checklist below before you commit.",
    4: "This plot has serious risk flags. Get them checked before you pay any money.",
    5: "This plot has major risk flags. Treat it as high-risk until an expert clears it.",
}


def _plain_summary(story, st, result, build_scope, title_check, width):
    """A plain-language box anyone can act on — written for a first-time buyer, not an
    engineer. Enterprises still get the cited breakdown on the later pages; this is the
    one-glance 'what it means and what to check' that the whole report hangs off."""
    level = result.get("level") or 1
    story.append(Paragraph("In plain words", st["h2"]))
    story.append(Paragraph(_PLAIN_VERDICT.get(level, _PLAIN_VERDICT[3]), st["body"]))

    checks = []
    # Title — tailored to the uploaded documents when we have them.
    owner = (title_check or {}).get("ownerMatch")
    if owner and owner.get("status") == "mismatch":
        checks.append("The name on the Patta does not clearly match the sale/EC party — "
                      "confirm who actually owns this land before paying.")
    elif owner and owner.get("status") == "match":
        checks.append("Patta owner and the sale/EC party look consistent — still verify the "
                      "original documents at the sub-registrar.")
    else:
        checks.append("Confirm the seller's name on the Patta matches the EC and the sale deed.")
    mort = (title_check or {}).get("mortgages")
    if mort and mort.get("unreleased"):
        checks.append("At least one loan on this land has no release on record — get it "
                      "cleared (CERSAI/EC) before you buy.")
    checks.append("Check the survey number is the same on every document and on the ground.")
    crz = result.get("crz")
    if crz:
        checks.append("This plot is near the coast (CRZ ~%s m) — confirm what you may build "
                      "under the CZMP." % crz.get("distance_m", "?"))
    flood = result.get("flood") or {}
    if (flood.get("level") or 0) >= 3:
        checks.append("This street can flood in the monsoon — ask neighbours how high the "
                      "water came last time, and whether the storm drain works.")
    if build_scope:
        fsi = build_scope["fsi"]["max_with_premium"]
        units = build_scope["yield"].get("approx_dwelling_units")
        tail = " (roughly %d homes-worth of floor area)" % units if units else ""
        checks.append("You can build to about FSI %s here%s — confirm the exact limit with "
                      "CMDA/DTCP before you plan." % (fsi, tail))

    story.append(Spacer(1, 3))
    story.append(Paragraph("<b>Before you pay, check:</b>", st["body"]))
    for item in checks[:6]:
        story.append(Paragraph("&bull;&nbsp; %s" % item, st["body"]))
    story.append(Spacer(1, 6))


_NOC_NONE = "No statutory clearances are triggered by these inputs."


def _build_scope_section(story, st, bs, width):
    """'What you can build here' — the TNCDBR development envelope, for the buyer deciding
    whether the plot fits their plan and for a lender sizing the asset."""
    story.append(PageBreak())
    story.append(Paragraph("What you can build here", st["h2"]))
    story.append(Paragraph(
        "Indicative development potential under TNCDBR-2019-style rules for a "
        "<b>%s m&#178;</b> plot on a <b>%s m</b> road, %s use."
        % (int(bs["inputs"]["plot_area_sqm"]), bs["inputs"]["road_width_m"],
           bs["inputs"]["use"]), st["small"]))
    story.append(Spacer(1, 4))

    h = bs["height"]
    height_val = ("%s m (capped by %s)" % (h["net_permissible_m"], h["constrained_by"])
                  if h.get("net_permissible_m") is not None
                  else "provide AAI PTE + ground elevation for the airport cap")
    rows = [
        ("Max FSI (with premium)", "%s  (normal %s + premium %s)"
         % (bs["fsi"]["max_with_premium"], bs["fsi"]["normal"], bs["fsi"]["premium_added"])),
        ("Max built-up area", "%s m²  (%s m² at normal FSI)"
         % (int(bs["built_up_area_sqm"]["at_premium_fsi"]),
            int(bs["built_up_area_sqm"]["at_normal_fsi"]))),
        ("Ground coverage", "%d%%  (%s m² footprint)"
         % (round(bs["ground_coverage"]["fraction"] * 100),
            int(bs["ground_coverage"]["max_footprint_sqm"]))),
        ("Setbacks (front / side / rear)", "%s / %s / %s m"
         % (bs["setbacks"]["front_m"], bs["setbacks"]["side1_m"], bs["setbacks"]["rear_m"])),
        ("Net permissible height", height_val),
        ("Parking", "%d car-equivalent spaces" % bs["parking"]["car_equivalent_spaces"]),
    ]
    if bs["yield"].get("approx_dwelling_units") is not None:
        rows.append(("Approx. dwelling units", "~%d" % bs["yield"]["approx_dwelling_units"]))
    if bs["osr"].get("required"):
        rows.append(("Reserved open space (OSR)", "%s m²" % bs["osr"]["area_sqm"]))
    story.append(_metric_table(rows, width))

    story.append(Paragraph("Clearances to obtain", st["h3"]))
    active = [n for n in bs["noc_checklist"] if n.get("required")]
    if not active:
        story.append(Paragraph(_NOC_NONE, st["body"]))
    else:
        for n in active:
            story.append(Paragraph("&#9888;&nbsp; <b>%s</b> — %s"
                                   % (n["authority"], n["reason"]), st["warn"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(bs["disclaimer"], st["small"]))


_TITLE_STATUS = {
    "match": ("Consistent", "#15803d"),
    "mismatch": ("Does not match", "#dc2626"),
    "unknown": ("Need more documents", "#6b7280"),
}


def _title_row(story, st, label, status, detail):
    word, hexc = _TITLE_STATUS.get(status, _TITLE_STATUS["unknown"])
    story.append(Paragraph('<b>%s</b> &mdash; <font color="%s">%s</font>'
                           % (label, hexc, word), st["body"]))
    if detail:
        story.append(Paragraph(detail, st["small"]))
    story.append(Spacer(1, 3))


def _title_section(story, st, title_check, width):
    """Title cross-verification from the user's own uploaded documents — the due-diligence
    section an underwriter and a buyer both want. Screening signals, not legal advice."""
    story.append(PageBreak())
    story.append(Paragraph("Title &amp; document verification", st["h2"]))
    have = ", ".join(title_check.get("haveDocs") or []) or "your uploaded documents"
    story.append(Paragraph(
        "Screening checks across %s. These are automated comparisons — verify the originals "
        "against the sub-registrar's records and CERSAI before relying on them." % have,
        st["small"]))
    story.append(Spacer(1, 5))

    owner = title_check.get("ownerMatch")
    if owner:
        detail = owner.get("note") or ""
        if owner.get("owner") and owner.get("buyer"):
            detail = "%s ↔ %s. %s" % (owner["owner"], owner["buyer"], detail)
        _title_row(story, st, "Patta owner vs. sale/EC party", owner.get("status"), detail)
    survey = title_check.get("surveyParity")
    if survey:
        vals = " vs ".join(survey.get("values") or [])
        _title_row(story, st, "Survey-number parity", survey.get("status"),
                   "%s. %s" % (vals, survey.get("note") or ""))
    mort = title_check.get("mortgages")
    if mort:
        status = "mismatch" if mort.get("unreleased") else "match"
        _title_row(story, st, "Encumbrance (mortgage) chain", status, mort.get("note") or "")


def _header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, PAGE_H - 12 * mm, "TerrisIQ")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 12 * mm,
                           "Property risk & buildability — due-diligence screening")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, PAGE_H - 14 * mm, PAGE_W - MARGIN, PAGE_H - 14 * mm)
    canvas.line(MARGIN, 14 * mm, PAGE_W - MARGIN, 14 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(MARGIN, 10 * mm, "Screening tool - not a professional environmental assessment.")
    canvas.drawRightString(PAGE_W - MARGIN, 10 * mm, "Page %d" % doc.page)
    canvas.restoreState()


def build_report(result, build_scope=None, title_check=None):
    city_info = result.get("city") or {}
    city = city_registry.get(city_info.get("slug"))
    # A US (or any out-of-India) result has no local layer store; skip the locality map
    # rather than draw a misleading Chennai one at the wrong coordinates.
    is_local = city is not None
    city_name = city.name if city else (city_info.get("name") or "Location")
    st = _styles()
    buf = io.BytesIO()
    width = PAGE_W - 2 * MARGIN
    doc = BaseDocTemplate(buf, pagesize=A4,
                          leftMargin=MARGIN, rightMargin=MARGIN,
                          topMargin=MARGIN + 4 * mm, bottomMargin=MARGIN,
                          title="TerrisIQ property risk report",
                          author="TerrisIQ")
    frame = Frame(MARGIN, MARGIN, width, PAGE_H - 2 * MARGIN - 4 * mm, id="body")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_header_footer)])

    story = []
    address = result.get("address") or "Unnamed parcel"
    story.append(Paragraph("TerrisIQ Property Risk Report", st["title"]))
    story.append(Paragraph(address, st["body"]))
    if result.get("coverage_note"):
        story.append(Paragraph("<b>%s</b> &middot; %s" % (city_name, result["coverage_note"]),
                               st["small"]))
    admin = result.get("administrative") or {}
    if admin.get("summary"):
        story.append(Paragraph("<b>%s</b>" % admin["summary"], st["body"]))
    story.append(Paragraph("%.5f, %.5f &nbsp;&middot;&nbsp; generated %s"
                           % (result["latitude"], result["longitude"],
                              result["generated_at"].replace("T", " ").replace("+00:00", " UTC")),
                           st["small"]))
    story.append(Spacer(1, 8))
    story.append(GradeBlock(result, width))
    story.append(Paragraph(result["summary"], st["body"]))
    if result.get("grade_floor_reason"):
        story.append(Spacer(1, 3))
        story.append(Paragraph(
            "<b>Reading adjusted.</b> %s" % result["grade_floor_reason"], st["warn"]))
    if result.get("evidence_ceiling_reason"):
        story.append(Spacer(1, 3))
        story.append(Paragraph("<b>Reading capped.</b> %s" % result["evidence_ceiling_reason"],
                               st["small"]))
    story.append(Spacer(1, 4))

    # Plain-language "what it means / what to check" — the part a first-time buyer reads.
    _plain_summary(story, st, result, build_scope, title_check, width)

    findings = _key_findings(result)
    if findings:
        story.append(Paragraph("Key findings", st["h2"]))
        for dimension, message in findings:
            story.append(Paragraph("<b>%s.</b> %s" % (dimension, message), st["warn"]))
        story.append(Spacer(1, 4))

    if is_local:
        story.append(Paragraph("Locality map", st["h2"]))
        story.append(LocalityMap(city, result["latitude"], result["longitude"], width))
        story.append(Spacer(1, 2))
        story.append(Legend(width))

    # Buildability and title — the two things the location score alone can't tell a buyer.
    # Each renders on its own page and is skipped when the app didn't supply the data.
    if build_scope:
        _build_scope_section(story, st, build_scope, width)
    if title_check:
        _title_section(story, st, title_check, width)

    story.append(PageBreak())
    story.append(Paragraph("Risk breakdown", st["h2"]))
    _dimension_section(story, st, "1. Monsoon flood &amp; water stagnation", 0.45,
                       result["flood"], width)
    if result.get("contamination"):
        _dimension_section(story, st, "2. Groundwater contamination", 0.30,
                           result["contamination"], width)
    else:
        story.append(Paragraph("2. Groundwater contamination", st["h3"]))
        story.append(Paragraph(
            "No industrial or waste sites are mapped for %s, so this dimension is not "
            "scored. That is a gap in the mapping, not a clean bill of health."
            % city_name, st["body"]))
        story.append(Spacer(1, 8))
    if result.get("scarcity"):
        _dimension_section(story, st, "3. Summer water scarcity", 0.25,
                           result["scarcity"], width)
    else:
        story.append(Paragraph("3. Summer water scarcity", st["h3"]))
        story.append(Paragraph(
            "No groundwater evidence is published for %s, so this dimension is not "
            "scored and the other two carry the whole grade. Absence of data is not "
            "the same as absence of risk: ask neighbours what depth their borewell "
            "runs at, and whether it holds through May." % city_name, st["body"]))
        story.append(Spacer(1, 8))

    context = result["flood"]["details"].get("locality_context")
    if context:
        story.append(Paragraph("Locality notes", st["h3"]))
        for note in context:
            story.append(Paragraph("<b>%s</b> (%dm): %s"
                                   % (note["locality"], note["distance_m"], note["note"]),
                                   st["small"]))

    story.append(PageBreak())
    story.append(Paragraph("Methodology", st["h2"]))
    story.append(Paragraph(
        "Each dimension is scored 0-100 from independent spatial signals, then combined "
        "as <b>0.45 &times; flood + 0.30 &times; contamination + 0.25 &times; scarcity</b>. "
        "Readings: 0-20 very low, 21-40 low, 41-60 moderate, 61-80 high, "
        "81-100 very high risk.", st["body"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Because a parcel is metres across and the GCC inundation layer tiles the city "
        "with small gaps along roads, the flood category is read from a 40 m window "
        "around the point, falling back to a 150 m window at a 0.6 discount. Elevation "
        "is measured relative to a 250 m ring rather than absolute height, since a plot "
        "sitting below its neighbours collects their runoff regardless of its height "
        "above sea level.", st["body"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "The flood category field was validated against the 53 GCC-recorded 2020 "
        "(Cyclone Nivar) flood hotspots, which are independent of the inundation "
        "polygons. The 'High' and 'Very High' categories cover 10.8% of the city's area "
        "but contain 45% of those recorded hotspots - a 4.2x concentration - and the "
        "lift falls monotonically down the scale.", st["body"]))

    story.append(Paragraph("Single-dimension severity floor", st["h3"]))
    story.append(Paragraph(
        "A plain weighted average can report a reassuring grade over a severe finding: "
        "a parcel inside a critically polluted industrial cluster but with good drainage "
        "and moderate water stress averages out to a 'Low Risk' B. These three risks are "
        "not substitutes for one another, so where any single dimension scores 61 or "
        "above the headline grade is capped at C, and at 81 or above it is capped at D. "
        "The composite score itself is left exactly as the weighted formula produces it, "
        "and the unadjusted grade is always reported alongside.", st["body"]))

    story.append(Paragraph("Confidence", st["h3"]))
    story.append(Paragraph(
        "Each dimension reports its own confidence. It is downgraded where a parcel "
        "falls outside a dataset's surveyed extent, where a groundwater figure comes "
        "from the CGWB regional finding rather than a published local measurement, or "
        "where a proxy indicator stands in for data that is not openly published. "
        "Absence of a mapped hazard is not evidence that no hazard exists.", st["body"]))

    story.append(Paragraph("Data sources", st["h3"]))
    sources = [
        ("GCC flood inundation zones", "OpenCity.in (Greater Chennai Corporation)"),
        ("GCC storm water drain network", "OpenCity.in - 10,255 segments with condition"),
        ("GCC 2020 flood hotspots", "OpenCity.in (Cyclone Nivar record)"),
        ("Elevation (SRTM 30 m)", "NASA SRTM via Open Topo Data"),
        ("Waterbodies, industrial land use, coastline", "OpenStreetMap (ODbL)"),
        ("Industrial pollution (CEPI)", "Central Pollution Control Board"),
        ("Groundwater exploitation status",
         "Hand-curated: 4 localities from published CGWB/CMWSSB figures, "
         "the rest inferred from CGWB's regional finding"),
    ]
    story.append(_metric_table(sources, width))

    story.append(Paragraph("Disclaimer", st["h3"]))
    story.append(Paragraph(DISCLAIMER, st["body"]))

    doc.build(story)
    buf.seek(0)
    return buf.read()
