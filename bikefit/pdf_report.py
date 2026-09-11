"""PDF-отчёт: размеченные кадры, измерения, рекомендации, ориентиры.

Шрифт: DejaVu Sans из состава matplotlib (он всегда рядом, т.к. matplotlib —
зависимость mediapipe), иначе встроенные шрифты reportlab не умеют кириллицу.
"""

from __future__ import annotations

import datetime as dt
import os
from io import BytesIO

import cv2
import numpy as np
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
    TableStyle,
)

from . import guide
from .analyzer import FitReport
from .references import Profile
from .report import annotate

_FONT, _FONT_BOLD = "DejaVuSans", "DejaVuSans-Bold"


def _font_dir() -> str:
    import matplotlib
    return os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf")


def _register_fonts() -> None:
    """Регистрирует DejaVu в двух независимых реестрах.

    reportlab и svglib ведут реестры порознь, поэтому проверки тоже порознь:
    если шрифт уже есть в reportlab (например, раньше собирали отчёт), svglib
    всё равно нужно зарегистрировать — иначе текст схем уйдёт в Helvetica,
    у которой нет кириллицы, и в PDF будут квадраты.
    """
    d = _font_dir()
    if _FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(_FONT, os.path.join(d, "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont(_FONT_BOLD, os.path.join(d, "DejaVuSans-Bold.ttf")))
        pdfmetrics.registerFontFamily(_FONT, normal=_FONT, bold=_FONT_BOLD,
                                      italic=_FONT, boldItalic=_FONT_BOLD)

    from svglib.fonts import find_font, register_font
    name, exact = find_font(_FONT)
    if not exact or name != _FONT:
        register_font(_FONT, os.path.join(d, "DejaVuSans.ttf"))
    name_b, exact_b = find_font(_FONT, weight="bold")
    if not exact_b or name_b != _FONT_BOLD:
        register_font(_FONT, os.path.join(d, "DejaVuSans-Bold.ttf"), weight="bold")


def _styles() -> dict[str, ParagraphStyle]:
    base = dict(fontName=_FONT, leading=14, alignment=TA_LEFT)
    return {
        "h1": ParagraphStyle("h1", fontName=_FONT_BOLD, fontSize=18, leading=22, spaceAfter=4),
        "h2": ParagraphStyle("h2", fontName=_FONT_BOLD, fontSize=13, leading=17,
                             spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("body", fontSize=10, **base),
        "small": ParagraphStyle("small", fontSize=8.5, leading=11, textColor=colors.grey,
                                fontName=_FONT),
        "cell": ParagraphStyle("cell", fontSize=9, leading=11, fontName=_FONT),
        "warn": ParagraphStyle("warn", fontSize=10, leading=14, fontName=_FONT,
                               textColor=colors.HexColor("#8a4b00")),
    }


def _img_flowable(bgr: np.ndarray, max_w: float, max_h: float) -> Image:
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise RuntimeError("Не удалось закодировать кадр")
    h, w = bgr.shape[:2]
    k = min(max_w / w, max_h / h)
    return Image(BytesIO(buf.tobytes()), width=w * k, height=h * k)


def build_pdf(report: FitReport, title: str = "Отчёт по велопосадке") -> bytes:
    """Собирает PDF в память и возвращает байты."""
    _register_fonts()
    st = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=14 * mm, bottomMargin=14 * mm, title=title,
    )
    W = A4[0] - doc.leftMargin - doc.rightMargin
    el: list = []

    # -------------------------------------------------------------- шапка
    el.append(Paragraph(title, st["h1"]))
    meta = [f"Дата: {dt.date.today():%d.%m.%Y}", f"Профиль: {report.profile.title}"]
    if report.bike:
        b = report.bike
        meta.append(
            f"Велосипед: {b.title} — stack {b.stack_mm:g} / reach {b.reach_mm:g} мм, "
            f"подседельная {b.eff_seat_angle_deg:g}°, база {b.wheelbase_mm:g} мм"
        )
    if report.rider and not report.rider.is_empty():
        r = report.rider
        parts = [f"рост {r.height_cm:g}" if r.height_cm else None,
                 f"inseam {r.inseam_cm:g}" if r.inseam_cm else None,
                 f"рука {r.arm_cm:g}" if r.arm_cm else None,
                 f"плечи {r.shoulder_cm:g}" if r.shoulder_cm else None]
        meta.append("Райдер, см: " + ", ".join(p for p in parts if p))
    meta.append("Калибровка: " + ("есть — величины в мм" if report.calibrated
                                  else "нет — только направления регулировок"))
    for m in meta:
        el.append(Paragraph(m, st["body"]))

    # -------------------------------------------------------------- кадры
    if report.frames:
        el.append(Paragraph("Кадры с разметкой", st["h2"]))
        imgs = [(name, annotate(f, report, name)) for name, f in report.frames.items()]
        if len(imgs) == 1:
            el.append(_img_flowable(imgs[0][1], W, 110 * mm))
            el.append(Paragraph(imgs[0][0], st["small"]))
        else:
            cw = (W - 4 * mm) / 2
            row = [_img_flowable(img, cw, 95 * mm) for _, img in imgs[:2]]
            cap = [Paragraph(n, st["small"]) for n, _ in imgs[:2]]
            t = Table([row, cap], colWidths=[cw, cw])
            t.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            el.append(t)

    # -------------------------------------------------------------- метрики
    el.append(Paragraph("Измерения", st["h2"]))
    rows = [["", "Метрика", "Значение", "Норма", "Отклонение"]]
    for m in report.metrics:
        rows.append([
            "✓" if m.ok else "!", Paragraph(m.title, st["cell"]),
            f"{m.value:.1f}{m.unit}", f"{m.ref.lo:g}–{m.ref.hi:g}{m.unit}",
            "" if m.ok else f"{m.deviation:+.1f}",
        ])
    t = Table(rows, colWidths=[8 * mm, W - 8 * mm - 26 * 3 * mm, 26 * mm, 26 * mm, 26 * mm])
    style = [
        ("FONTNAME", (0, 0), (-1, -1), _FONT),
        ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
    ]
    for i, m in enumerate(report.metrics, 1):
        style.append(("TEXTCOLOR", (0, i), (0, i),
                      colors.HexColor("#2e8b57") if m.ok else colors.HexColor("#c0392b")))
    t.setStyle(TableStyle(style))
    el.append(t)

    # -------------------------------------------------------------- рекомендации
    el.append(Paragraph("Рекомендации (в порядке выполнения)", st["h2"]))
    for i, r in enumerate(report.recommendations, 1):
        amount = f" на ~{abs(r.amount_mm):.0f} мм" if r.amount_mm else ""
        el.append(Paragraph(
            f"<b>{i}. {r.part}: {r.action}{amount}</b><br/>{r.reason}", st["body"]))
        el.append(Spacer(1, 3))

    if report.notes:
        el.append(Paragraph("Ориентиры по антропометрии и видео", st["h2"]))
        for n in report.notes:
            el.append(Paragraph("• " + n, st["body"]))

    if report.warnings:
        el.append(Paragraph("Ограничения и предупреждения", st["h2"]))
        for w in report.warnings:
            el.append(Paragraph("• " + w, st["warn"]))

    el.append(Spacer(1, 8))
    el.append(Paragraph(
        "Меняйте по одному параметру за раз, шаг седла — не более 5 мм, затем 2–3 поездки "
        "на адаптацию. Углы измерены по 2D-проекции с ошибкой до нескольких градусов при "
        "неидеальном ракурсе. Отчёт — инструмент самонастройки, не замена очному фиттингу; "
        "при боли в колене, спине или онемении рук обратитесь к специалисту.", st["small"]))

    doc.build(el)
    return buf.getvalue()


# ====================================================================== инструкция
def _md_inline(text: str) -> str:
    """**жирный** из markdown → <b> для Paragraph."""
    out, bold = [], False
    for chunk in text.split("**"):
        out.append(chunk)
        bold = not bold
        out.append("<b>" if bold else "</b>")
    return "".join(out[:-1])


def _svg_flowable(svg: str, max_w: float):
    """SVG-строка → векторный Drawing reportlab, вписанный по ширине."""
    import tempfile

    from svglib.svglib import svg2rlg

    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False, encoding="utf-8") as fh:
        fh.write(svg)
        path = fh.name
    try:
        d = svg2rlg(path)
    finally:
        os.unlink(path)
    k = min(1.0, max_w / d.width)
    d.width, d.height = d.width * k, d.height * k
    d.scale(k, k)
    return d


def build_guide_pdf(profile: Profile | None = None) -> bytes:
    """PDF-инструкция по съёмке + пояснение метрик (диапазоны профиля)."""
    _register_fonts()
    st = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=14 * mm, bottomMargin=14 * mm, title="Инструкция по съёмке для анализа велопосадки",
    )
    W = A4[0] - doc.leftMargin - doc.rightMargin
    el: list = [Paragraph(guide.GUIDE_TITLE, st["h1"]), Paragraph(guide.GUIDE_LEAD, st["body"])]

    for sec in guide.SECTIONS:
        head: list = [Paragraph(sec.title, st["h2"])]
        if sec.diagrams:
            # схемы одна под другой на всю ширину — так подписи читаемы;
            # заголовок скреплён с первой схемой, чтобы не осиротел внизу страницы
            head.append(_svg_flowable(sec.diagrams[0](guide.LIGHT), W * 0.85))
            el.append(KeepTogether(head))
            for d in sec.diagrams[1:]:
                el.append(_svg_flowable(d(guide.LIGHT), W * 0.85))
            el.append(Spacer(1, 4))
        else:
            el.extend(head)
        for b in sec.bullets:
            el.append(Paragraph("• " + _md_inline(b), st["body"]))
        if sec.after:
            el.append(Paragraph(sec.after, st["body"]))

    el.append(Paragraph(guide.ERRORS_TITLE, st["h2"]))
    rows = [["Ошибка", "Что ломает"]] + [[Paragraph(a, st["cell"]), Paragraph(b, st["cell"])]
                                         for a, b in guide.ERRORS]
    t = Table(rows, colWidths=[W * 0.5, W * 0.5])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD), ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    el.append(t)

    el.append(PageBreak())
    el.append(Paragraph(guide.METRICS_TITLE, st["h1"]))
    if profile is not None:
        el.append(Paragraph(f"Диапазоны для профиля «{profile.title}».", st["small"]))
    el.append(_svg_flowable(guide.svg_angles(profile, guide.LIGHT), W))
    el.append(Spacer(1, 6))
    el.append(Paragraph(_md_inline(guide.METRICS_TEXT), st["body"]))
    el.append(Spacer(1, 4))
    for b in guide.METRICS_BULLETS:
        el.append(Paragraph("• " + _md_inline(b), st["body"]))
    el.append(Spacer(1, 8))
    el.append(Paragraph(guide.METRICS_DISCLAIMER, st["small"]))

    doc.build(el)
    return buf.getvalue()
