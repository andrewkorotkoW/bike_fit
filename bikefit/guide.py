"""Инструкция по съёмке и пояснение метрик: единый источник для UI и PDF.

Текст хранится структурой (SECTIONS/ERRORS), схемы — функциями, рисующими
inline-SVG в заданной палитре: тёмной для Streamlit, светлой для PDF.
SVG масштабируются без потери чёткости и не требуют файлов рядом с кодом.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

from .references import Profile

# ------------------------------------------------------------------ палитры
@dataclass(frozen=True, slots=True)
class Palette:
    line: str
    text: str
    accent: str
    ok: str
    font: str


DARK = Palette(line="#a4a9b0", text="#c9ccd1", accent="#f08a8a", ok="#7fcf9f",
               font="system-ui,-apple-system,Segoe UI,Roboto,sans-serif")
LIGHT = Palette(line="#6b7075", text="#2b2f33", accent="#c94f4f", ok="#2f8f5b",
                font="DejaVuSans")   # зарегистрирован в svglib при сборке PDF

_DOT = "0.1 7"   # точечный пунктир: с round-cap даёт мягкие точки


# ------------------------------------------------------------------ SVG-утилиты
def _svg(w: int, h: int, body: str, c: Palette) -> str:
    # явные width/height: без них <img> в Streamlit не знает высоту и схлопывается
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'width="{w}" height="{h}">'
            f'<g stroke-linecap="round" stroke-linejoin="round" font-family="{c.font}">'
            f'{body}</g></svg>')


def _t(x: float, y: float, s: str, size: int = 13, color: str = "", anchor: str = "middle",
       weight: str = "normal") -> str:
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" '
            f'text-anchor="{anchor}" font-weight="{weight}">{s}</text>')


def _bike_side(ox: float, oy: float, s: float, color: str) -> str:
    """Схематичный велосипед сбоку. (ox, oy) — ось каретки, s — масштаб."""
    r = 34 * s
    rear, front = (ox - 42 * s, oy), (ox + 60 * s, oy)
    seat = (ox - 14 * s, oy - 56 * s)
    head_top, head_bot = (ox + 40 * s, oy - 52 * s), (ox + 48 * s, oy - 30 * s)
    bars = (ox + 46 * s, oy - 58 * s)
    def p(a, b):
        return (f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" stroke="{color}" '
                f'stroke-width="{2.4*s}" opacity="0.9"/>')
    return "".join([
        f'<circle cx="{rear[0]}" cy="{rear[1]}" r="{r}" fill="none" stroke="{color}" stroke-width="{2.4*s}" opacity="0.9"/>',
        f'<circle cx="{front[0]}" cy="{front[1]}" r="{r}" fill="none" stroke="{color}" stroke-width="{2.4*s}" opacity="0.9"/>',
        p(rear, (ox, oy)), p(rear, seat), p(seat, (ox, oy)), p(seat, head_top),
        p(head_top, head_bot), p(head_bot, (ox, oy)), p(head_bot, front), p(head_top, bars),
        p(seat, (seat[0] - 10 * s, seat[1] - 4 * s)), p(seat, (seat[0] + 10 * s, seat[1] - 4 * s)),
        f'<circle cx="{ox}" cy="{oy}" r="{4*s}" fill="{color}"/>',
    ])


# ------------------------------------------------------------------ схемы
def svg_camera_top_view(c: Palette = DARK) -> str:
    """Вид сверху: камера строго перпендикулярно плоскости велосипеда."""
    body = [
        f'<rect x="200" y="86" width="240" height="14" rx="7" fill="{c.line}" fill-opacity="0.15" stroke="{c.line}" stroke-width="2"/>',
        _t(320, 76, "велосипед на станке (вид сверху)", 13, c.text),
        f'<line x1="320" y1="100" x2="320" y2="250" stroke="{c.ok}" stroke-width="3" stroke-dasharray="{_DOT}"/>',
        f'<path d="M320 118 L338 118 L338 100" fill="none" stroke="{c.ok}" stroke-width="2"/>',
        _t(352, 116, "90°", 13, c.ok, "start"),
        f'<rect x="300" y="250" width="40" height="26" rx="8" fill="{c.accent}" fill-opacity="0.15" stroke="{c.accent}" stroke-width="2"/>',
        f'<circle cx="320" cy="263" r="7" fill="none" stroke="{c.accent}" stroke-width="2"/>',
        _t(320, 300, "камера на штативе", 13, c.accent),
        f'<line x1="470" y1="100" x2="470" y2="250" stroke="{c.line}" stroke-width="1"/>',
        f'<line x1="464" y1="100" x2="476" y2="100" stroke="{c.line}" stroke-width="1"/>',
        f'<line x1="464" y1="250" x2="476" y2="250" stroke="{c.line}" stroke-width="1"/>',
        _t(482, 180, "2.5–3 м", 13, c.text, "start"),
        f'<line x1="440" y1="93" x2="560" y2="200" stroke="{c.accent}" stroke-width="2.5" stroke-dasharray="{_DOT}" opacity="0.8"/>',
        _t(560, 222, "не так: под углом — ошибка 5–8° в колене", 12, c.accent),
        _t(308, 190, "напротив каретки, не колеса", 12, c.text, "end"),
    ]
    return _svg(760, 320, "".join(body), c)


def svg_camera_side_view(c: Palette = DARK) -> str:
    """Вид сбоку: высота объектива = ось каретки, колёса целиком в кадре, дистанция."""
    ox, oy = 250, 190
    front_edge = ox + 94 * 1.6
    body = [
        _bike_side(ox, oy, 1.6, c.line),
        f'<line x1="640" y1="{oy}" x2="640" y2="{oy + 90}" stroke="{c.accent}" stroke-width="2.4"/>',
        f'<line x1="620" y1="{oy + 90}" x2="660" y2="{oy + 90}" stroke="{c.accent}" stroke-width="2.4"/>',
        f'<rect x="618" y="{oy - 14}" width="44" height="28" rx="9" fill="{c.accent}" fill-opacity="0.15" stroke="{c.accent}" stroke-width="2"/>',
        f'<circle cx="640" cy="{oy}" r="7" fill="none" stroke="{c.accent}" stroke-width="2"/>',
        f'<line x1="{ox}" y1="{oy}" x2="612" y2="{oy}" stroke="{c.ok}" stroke-width="3" stroke-dasharray="{_DOT}"/>',
        _t(508, oy - 10, "объектив на высоте оси каретки", 13, c.ok),
        f'<rect x="120" y="40" width="330" height="230" rx="14" fill="none" stroke="{c.line}" stroke-width="2.5" stroke-dasharray="{_DOT}" opacity="0.8"/>',
        _t(285, 32, "в кадре — велосипед целиком, оба колеса (для калибровки по базе)", 12, c.text),
        f'<line x1="60" y1="{oy + 92}" x2="700" y2="{oy + 92}" stroke="{c.line}" stroke-width="1.5" opacity="0.6"/>',
        _t(600, oy + 108, "штатив, зум вместо приближения", 12, c.accent),
        f'<line x1="{front_edge}" y1="{oy + 75}" x2="640" y2="{oy + 75}" stroke="{c.text}" stroke-width="1.5"/>',
        f'<line x1="{front_edge}" y1="{oy + 68}" x2="{front_edge}" y2="{oy + 82}" stroke="{c.text}" stroke-width="1.5"/>',
        f'<line x1="640" y1="{oy + 68}" x2="640" y2="{oy + 82}" stroke="{c.text}" stroke-width="1.5"/>',
        _t((front_edge + 640) / 2, oy + 70, "2.5–3 м", 13, c.text, "middle", "bold"),
    ]
    return _svg(760, 310, "".join(body), c)


def svg_crank_positions(c: Palette = DARK) -> str:
    """Три положения шатуна для фото-режима."""
    def crank(cx, cy, angle_deg, label, sub, color):
        a = math.radians(angle_deg)
        px, py = cx + 34 * math.cos(a), cy + 34 * math.sin(a)
        st_a = math.radians(-107)
        sx, sy = cx + 70 * math.cos(st_a), cy + 70 * math.sin(st_a)
        return "".join([
            f'<line x1="{cx}" y1="{cy}" x2="{sx}" y2="{sy}" stroke="{c.line}" stroke-width="2"/>',
            f'<circle cx="{cx}" cy="{cy}" r="38" fill="none" stroke="{c.line}" stroke-width="2.5" stroke-dasharray="{_DOT}" opacity="0.6"/>',
            f'<line x1="{cx}" y1="{cy}" x2="{px}" y2="{py}" stroke="{color}" stroke-width="6"/>',
            f'<circle cx="{px}" cy="{py}" r="7" fill="{color}" fill-opacity="0.35" stroke="{color}" stroke-width="2"/>',
            f'<circle cx="{cx}" cy="{cy}" r="4" fill="{c.line}"/>',
            _t(cx, cy + 68, label, 14, c.text, "middle", "bold"),
            _t(cx, cy + 86, sub, 12, c.text),
        ])
    body = [
        crank(120, 95, 73, "1. НМТ — обязательное", "шатун вниз ВДОЛЬ подседельной трубы", c.accent),
        crank(380, 95, -107, "2. ВМТ", "шатун вверх вдоль трубы", c.ok),
        crank(640, 95, 0, "3. Горизонтально (3 часа)", "для KOPS: колено над педалью", c.ok),
        _t(120, 26, "не строго вертикально вниз (6 часов)!", 11, c.accent),
    ]
    return _svg(760, 200, "".join(body), c)


def svg_angles(profile: Profile | None = None, c: Palette = DARK) -> str:
    """Фигура райдера с подписанными углами и диапазонами профиля."""
    raw = {"hip": (300, 120), "knee": (390, 260), "ankle": (330, 380), "foot": (392, 396),
           "shoulder": (520, 20), "elbow": (585, 130), "wrist": (640, 210)}
    # смещение вправо: слева нужно место под подписи таза
    p = {k: (120 + x * 0.62, 30 + y * 0.62) for k, (x, y) in raw.items()}
    def chain(*names):
        pts = " ".join(f"{p[n][0]},{p[n][1]}" for n in names)
        return f'<polyline points="{pts}" fill="none" stroke="{c.line}" stroke-width="5" opacity="0.85"/>'
    def dot(a):
        return (f'<circle cx="{p[a][0]}" cy="{p[a][1]}" r="9" fill="{c.accent}" fill-opacity="0.3"/>'
                f'<circle cx="{p[a][0]}" cy="{p[a][1]}" r="5" fill="{c.accent}"/>')
    def rng(key):
        if profile is None or key not in profile.ranges:
            return ""
        r = profile.ranges[key]
        return f" · норма {r.lo:g}–{r.hi:g}°"
    body = [
        chain("foot", "ankle", "knee", "hip", "shoulder", "elbow", "wrist"),
        f'<line x1="{p["hip"][0]}" y1="{p["hip"][1]}" x2="{p["hip"][0] + 120}" y2="{p["hip"][1]}" stroke="{c.ok}" stroke-width="3" stroke-dasharray="{_DOT}"/>',
        *[dot(k) for k in ("hip", "knee", "ankle", "shoulder", "elbow")],
        f'<circle cx="{p["shoulder"][0] + 14}" cy="{p["shoulder"][1] - 22}" r="16" fill="{c.line}" fill-opacity="0.15" stroke="{c.line}" stroke-width="3" opacity="0.85"/>',
        _t(p["knee"][0] + 16, p["knee"][1] + 6, "Колено в НМТ" + rng("knee_extension"), 13, c.text, "start", "bold"),
        _t(p["knee"][0] + 16, p["knee"][1] + 24, "таз—колено—лодыжка; 180° = прямая нога", 11, c.line, "start"),
        _t(p["hip"][0] - 16, p["hip"][1] + 24, "Открытие таза (ВМТ)" + rng("hip_closed"), 13, c.text, "end", "bold"),
        _t(p["hip"][0] - 16, p["hip"][1] + 42, "плечо—таз—колено", 11, c.line, "end"),
        _t(p["hip"][0] + 60, p["hip"][1] - 10, "Корпус к горизонту" + rng("torso"), 13, c.ok, "start", "bold"),
        _t(p["shoulder"][0] + 40, p["shoulder"][1] + 6, "Плечо" + rng("shoulder"), 13, c.text, "start", "bold"),
        _t(p["shoulder"][0] + 40, p["shoulder"][1] + 24, "таз—плечо—кисть", 11, c.line, "start"),
        _t(p["elbow"][0] + 16, p["elbow"][1] + 6, "Локоть" + rng("elbow"), 13, c.text, "start", "bold"),
        _t(p["ankle"][0] - 16, p["ankle"][1] + 10, "Голеностоп" + rng("ankle"), 13, c.text, "end", "bold"),
        _t(p["ankle"][0] - 16, p["ankle"][1] + 28, "колено—лодыжка—плюсна", 11, c.line, "end"),
    ]
    return _svg(760, 320, "".join(body), c)


# ------------------------------------------------------------------ контент
@dataclass(frozen=True, slots=True)
class Section:
    title: str
    bullets: tuple[str, ...]                     # markdown: **жирный** допустим
    diagrams: tuple[Callable[[Palette], str], ...] = ()
    after: str = ""                              # абзац после списка


GUIDE_TITLE = "Как снять фото или видео, чтобы отчёту можно было верить"
GUIDE_LEAD = ("От съёмки зависит 80 % точности: наклон камеры на 10° даёт ошибку в колене "
              "до 5–8° — больше, чем весь допустимый диапазон.")

SECTIONS: tuple[Section, ...] = (
    Section("1. Велосипед", (
        "На **станке**, на ровном полу; рама строго вертикально — проверить уровнем по подседельному штырю.",
        "Давление в покрышках рабочее, седло и руль — как ездишь сейчас (это и проверяем).",
        "Ничего не менять между кадрами одной сессии.",
    )),
    Section("2. Камера", (
        "**Строго перпендикулярно** плоскости велосипеда, напротив каретки.",
        "Объектив **на высоте оси каретки**, штатив, горизонт по уровню.",
        "Расстояние **2.5–3 м**, кадрировать зумом. Никакого широкоугольника (0.5×): он искажает углы по краям кадра.",
        "Телефон горизонтально, 1080p и выше. Для видео — **60 fps**.",
        "В кадре велосипед целиком с обоими колёсами: по осям колёс калибруется масштаб.",
        "Свет спереди-сбоку, без контрового; ноги не должны сливаться с фоном.",
    ), (svg_camera_top_view, svg_camera_side_view)),
    Section("3. Райдер", (
        "**Облегающая** одежда, контрастная фону; велотуфли с шипами, если ездишь в них.",
        "Разогрев **5–10 минут** — холодная посадка отличается от рабочей.",
        "Руки на **привычном хвате** (верх / пистолеты / низ — как ездишь чаще), взгляд вперёд по дороге, не в камеру.",
        "Ближняя к камере сторона тела должна быть открыта: ничего не свисает с руля.",
    )),
    Section("4. Видео (предпочтительно)", (
        "**10–15 секунд** ровного педалирования на рабочем каденсе 80–90, среднее усилие.",
        "Не «позировать»: педалировать как на дороге. Первые секунды разгона — в отбрасываемые.",
        "Программа сама находит НМТ/ВМТ в каждом обороте и берёт **медиану по оборотам**; разброс между оборотами покажет раскачку таза.",
        "Для сравнения сторон — снять отдельно левую и правую.",
    )),
    Section("5. Фото (если видео нет)", (), (svg_crank_positions,),
            "Кадр 1 обязателен. Частая ошибка — шатун строго вниз (6 часов): колено там уже "
            "не в максимальном разгибании, отчёт занизит угол и посоветует поднять седло."),
    Section("6. Калибровка", (
        "После загрузки кликни две точки прямо на фото: **оси заднего и переднего колеса** "
        "(база из геометрии велосипеда) или **ось каретки и ось педали** (длина шатуна).",
        "Без калибровки отчёт даст только направление регулировок, без миллиметров.",
    )),
)

ERRORS_TITLE = "Типичные ошибки, из-за которых отчёт врёт"
ERRORS: tuple[tuple[str, str], ...] = (
    ("Камера под углом к велосипеду", "углы колена и таза ±5–8°"),
    ("Камера выше/ниже каретки", "наклон корпуса, угол таза"),
    ("Широкоугольный объектив, съёмка с 1 м", "искажение по краям, колено и локоть"),
    ("Свободная одежда, тёмные ноги на тёмном фоне", "MediaPipe теряет суставы, низкая уверенность"),
    ("Шатун «на 6 часов» вместо вдоль трубы", "занижен угол колена → ложный совет поднять седло"),
    ("Руки не на рабочем хвате", "локоть, плечо, корпус"),
    ("Холодный райдер, 30 секунд на станке", "посадка «сидит» выше и короче рабочей"),
    ("Велосипед не вертикально", "все углы систематически"),
)

METRICS_TITLE = "Что измеряется и что считается нормой"
METRICS_TEXT = (
    "**Порядок правок** повторяет живой фиттинг: стопа → высота седла → продольное "
    "положение седла → кокпит. Менять вынос раньше седла бессмысленно: сдвинул седло — "
    "поехал и вылет."
)
METRICS_BULLETS = (
    "**Колено в НМТ** — главная метрика, задаёт высоту седла. Слишком прямая нога → "
    "раскачка таза, боль под коленом сзади; слишком согнутая → перегруз передней части колена.",
    "**Открытие таза в ВМТ** — закрытый таз душит дыхание и ограничивает ход бедра; "
    "часто решается доворотом седла носом вниз, а не переносом руля.",
    "**Корпус, плечо, локоть** — кокпит. Выпрямленный локоть = вибрация в кисти и шею.",
    "**KOPS** (только кадр с горизонтальным шатуном) — продольное положение седла.",
    "**Голеностоп** — стиль педалирования; сильное подошвенное сгибание в НМТ "
    "косвенно подтверждает завышенное седло.",
)
METRICS_DISCLAIMER = (
    "Диапазоны — популяционные ориентиры (Holmes 1994, Retül, Silberman 2005), "
    "не норма для конкретного человека. Отчёт — инструмент самонастройки и скрининга; "
    "при боли в колене, пояснице или онемении рук нужен очный фиттинг."
)


# ------------------------------------------------------------------ Streamlit
def render_shooting_guide() -> None:
    import streamlit as st

    st.markdown(f"### {GUIDE_TITLE}")
    st.caption(GUIDE_LEAD)
    for sec in SECTIONS:
        st.markdown(f"#### {sec.title}")
        if sec.diagrams:
            cols = st.columns(len(sec.diagrams)) if len(sec.diagrams) > 1 else [st]
            for col, draw in zip(cols, sec.diagrams):
                col.image(draw(DARK), use_column_width=True)
        if sec.bullets:
            st.markdown("\n".join(f"- {b}" for b in sec.bullets))
        if sec.after:
            st.markdown(sec.after)
    # не st.expander: сама инструкция живёт внутри экспандера, а вложенные запрещены
    st.markdown(f"#### {ERRORS_TITLE}")
    st.markdown("| Ошибка | Что ломает |\n|---|---|\n"
                + "\n".join(f"| {a} | {b} |" for a, b in ERRORS))


def render_metrics_guide(profile: Profile | None = None) -> None:
    import streamlit as st

    st.markdown(f"### {METRICS_TITLE}")
    if profile is not None:
        st.caption(f"Диапазоны для профиля «{profile.title}». Другой профиль — в сайдбаре.")
    st.image(svg_angles(profile, DARK), use_column_width=True)
    st.markdown(METRICS_TEXT + "\n\n" + "\n".join(f"- {b}" for b in METRICS_BULLETS))
    st.info(METRICS_DISCLAIMER)
