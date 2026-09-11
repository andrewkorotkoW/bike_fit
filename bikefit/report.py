"""Отрисовка скелета с углами и текстовый отчёт."""

from __future__ import annotations

import cv2
import numpy as np

from .analyzer import _BDC, FitReport
from .pose import PoseFrame

_GREEN = (80, 200, 120)
_RED = (60, 60, 235)
_WHITE = (245, 245, 245)

_CHAIN = [
    ("wrist", "elbow"), ("elbow", "shoulder"), ("shoulder", "hip"),
    ("hip", "knee"), ("knee", "ankle"), ("ankle", "foot"),
]


def annotate(frame: PoseFrame, report: FitReport, which: str = _BDC) -> np.ndarray:
    """Рисует скелет и подписывает углы: зелёный — в норме, красный — вне диапазона."""
    img = frame.image.copy()
    thickness = max(2, img.shape[1] // 500)

    for a, b in _CHAIN:
        p1 = tuple(map(int, (frame[a].x, frame[a].y)))
        p2 = tuple(map(int, (frame[b].x, frame[b].y)))
        cv2.line(img, p1, p2, _WHITE, thickness, cv2.LINE_AA)

    joint_of_metric = {
        "knee_extension": "knee", "knee_flexion": "knee",
        "hip_closed": "hip", "elbow": "elbow", "shoulder": "shoulder",
        "ankle": "ankle",
    }
    for m in report.metrics:
        joint = joint_of_metric.get(m.key)
        if joint is None or m.frame not in (which, "any"):
            continue
        color = _GREEN if m.ok else _RED
        p = (int(frame[joint].x), int(frame[joint].y))
        cv2.circle(img, p, thickness * 3, color, -1, cv2.LINE_AA)
        cv2.putText(img, f"{m.value:.0f}", (p[0] + 12, p[1] - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, thickness * 0.35, color,
                    max(1, thickness // 2), cv2.LINE_AA)

    # линия корпуса к горизонту
    hip, sh = frame["hip"], frame["shoulder"]
    cv2.line(img, (int(hip.x), int(hip.y)), (int(hip.x + 200), int(hip.y)),
             (180, 180, 180), 1, cv2.LINE_AA)
    return img


def render_text(report: FitReport) -> str:
    lines = [f"Профиль: {report.profile.title}"]
    if report.bike:
        b = report.bike
        lines.append(
            f"Велосипед: {b.title} — stack {b.stack_mm:g} / reach {b.reach_mm:g}, "
            f"подседельная {b.eff_seat_angle_deg:g}°, база {b.wheelbase_mm:g} мм"
        )
    lines += ["=" * 60, "ИЗМЕРЕНИЯ"]
    for m in report.metrics:
        mark = "OK " if m.ok else "!! "
        dev = "" if m.ok else f"  (отклонение {m.deviation:+.0f})"
        lines.append(
            f"  {mark}{m.title:<42} {m.value:6.1f}{m.unit}"
            f"   норма {m.ref.lo:g}–{m.ref.hi:g}{dev}"
        )

    lines += ["", "РЕКОМЕНДАЦИИ (в порядке выполнения)"]
    for i, r in enumerate(report.recommendations, 1):
        lines.append(f"  {i}. {r.render()}")

    if report.notes:
        lines += ["", "ОРИЕНТИРЫ ПО АНТРОПОМЕТРИИ"]
        lines += [f"  - {n}" for n in report.notes]

    if report.warnings:
        lines += ["", "ОГРАНИЧЕНИЯ И ПРЕДУПРЕЖДЕНИЯ"]
        lines += [f"  - {w}" for w in report.warnings]

    lines += [
        "",
        "Меняйте по одному параметру за раз, шаг седла — не более 5 мм, "
        "затем 2-3 поездки на адаптацию.",
        "При боли в колене, спине или онемении рук отчёт не заменяет очного "
        "фиттинга и консультации врача.",
    ]
    return "\n".join(lines)
