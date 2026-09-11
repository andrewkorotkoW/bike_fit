"""Геометрия сагиттальной плоскости: углы суставов и пересчёт градусов в мм.

Ключевая идея модуля: рекомендация «опустить седло» бесполезна без величины.
Поэтому угол в колене переводится в изменение расстояния таз—педаль через
теорему косинусов по реальным длинам сегментов конкретного человека
(они измеряются прямо на фото), а пиксели переводятся в мм по калибровке.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .pose import Point, PoseFrame


def _v(p: Point) -> np.ndarray:
    return p.as_array()


def angle_at(a: Point, b: Point, c: Point) -> float:
    """Внутренний угол ABC в градусах (b — вершина). 180° = сустав выпрямлен."""
    ba, bc = _v(a) - _v(b), _v(c) - _v(b)
    denom = np.linalg.norm(ba) * np.linalg.norm(bc)
    if denom < 1e-9:
        return float("nan")
    cos = float(np.clip(np.dot(ba, bc) / denom, -1.0, 1.0))
    return math.degrees(math.acos(cos))


def segment_len(a: Point, b: Point) -> float:
    """Длина сегмента в пикселях."""
    return float(np.linalg.norm(_v(a) - _v(b)))


def angle_to_horizontal(a: Point, b: Point) -> float:
    """Угол отрезка a→b к горизонту, 0..90°. Ось Y в кадре направлена вниз."""
    dx = abs(b.x - a.x)
    dy = abs(b.y - a.y)
    return math.degrees(math.atan2(dy, max(dx, 1e-9)))


# ---------------------------------------------------------------- калибровка
@dataclass(frozen=True, slots=True)
class Scale:
    """Перевод пикселей в миллиметры."""
    mm_per_px: float

    @classmethod
    def from_two_points(cls, p1: tuple[float, float], p2: tuple[float, float],
                        real_mm: float) -> "Scale":
        """По двум точкам с известным расстоянием.

        Практичные варианты на фото сбоку:
          * ось каретки — ось педали = длина шатуна (170/172.5/175 мм);
          * ось колеса — ось колеса = база велосипеда (из геометрии рамы);
          * наружный диаметр колеса 700x28 ≈ 678 мм.
        """
        px = math.dist(p1, p2)
        if px < 1:
            raise ValueError("Точки калибровки слишком близко")
        return cls(mm_per_px=real_mm / px)

    def to_mm(self, px: float) -> float:
        return px * self.mm_per_px


# --------------------------------------------- углы -> линейные перемещения
def chord(a_px: float, b_px: float, angle_deg: float) -> float:
    """Расстояние между концами двухзвенника (теорема косинусов)."""
    return math.sqrt(
        a_px ** 2 + b_px ** 2 - 2 * a_px * b_px * math.cos(math.radians(angle_deg))
    )


def linear_delta_px(seg_a: float, seg_b: float,
                    angle_now: float, angle_target: float) -> float:
    """На сколько пикселей изменится «размах» двухзвенника при смене угла.

    Для ноги: seg_a = бедро, seg_b = голень, угол в колене в нижней мёртвой
    точке -> получаем требуемое изменение высоты седла.
    Для руки: плечо/предплечье, угол в локте -> изменение вылета кокпита.
    Положительное значение = нужно увеличить расстояние (поднять седло / удлинить вынос).
    """
    return chord(seg_a, seg_b, angle_target) - chord(seg_a, seg_b, angle_now)


def saddle_height_delta_mm(frame: PoseFrame, knee_angle_now: float,
                           knee_angle_target: float, scale: Scale) -> float:
    femur = segment_len(frame["hip"], frame["knee"])
    tibia = segment_len(frame["knee"], frame["ankle"])
    return scale.to_mm(linear_delta_px(femur, tibia, knee_angle_now, knee_angle_target))


def reach_delta_mm(frame: PoseFrame, elbow_angle_now: float,
                   elbow_angle_target: float, scale: Scale) -> float:
    upper = segment_len(frame["shoulder"], frame["elbow"])
    fore = segment_len(frame["elbow"], frame["wrist"])
    return scale.to_mm(linear_delta_px(upper, fore, elbow_angle_now, elbow_angle_target))


def bar_height_delta_mm(frame: PoseFrame, torso_now: float,
                        torso_target: float, scale: Scale) -> float:
    """Грубая оценка подъёма руля через изменение вертикали корпуса.

    Считаем таз неподвижным, длину корпуса постоянной; тогда вертикаль плеча
    меняется на L*(sin(target) - sin(now)). Реально руль надо поднять меньше,
    т.к. корпус довернётся и в тазобедренном суставе — отсюда коэффициент 0.8.
    """
    torso = segment_len(frame["hip"], frame["shoulder"])
    dy = torso * (math.sin(math.radians(torso_target)) - math.sin(math.radians(torso_now)))
    return scale.to_mm(dy) * 0.8


# ------------------------------------------------------------------- метрики
def knee_angle(f: PoseFrame) -> float:
    """Таз—колено—лодыжка. 180° — нога прямая."""
    return angle_at(f["hip"], f["knee"], f["ankle"])


def hip_angle(f: PoseFrame) -> float:
    """Плечо—таз—колено. Закрытие таза в верхней мёртвой точке."""
    return angle_at(f["shoulder"], f["hip"], f["knee"])


def elbow_angle(f: PoseFrame) -> float:
    return angle_at(f["shoulder"], f["elbow"], f["wrist"])


def shoulder_angle(f: PoseFrame) -> float:
    """Таз—плечо—запястье: насколько руки вынесены вперёд относительно корпуса."""
    return angle_at(f["hip"], f["shoulder"], f["wrist"])


def torso_angle(f: PoseFrame) -> float:
    """Наклон корпуса к горизонту: 0° — лежит на руле, 90° — сидит вертикально."""
    return angle_to_horizontal(f["hip"], f["shoulder"])


def ankle_angle(f: PoseFrame) -> float:
    """Колено—лодыжка—плюсна: работа стопы."""
    return angle_at(f["knee"], f["ankle"], f["foot"])


def kops_offset_mm(f: PoseFrame, scale: Scale) -> float:
    """KOPS: смещение переднего края колена относительно оси педали, мм.

    Считать ТОЛЬКО на кадре с горизонтальным шатуном (3 часа).
    Ось педали приближаем серединой лодыжка↔плюсна.
    Знак «+» = колено впереди оси педали.
    """
    pedal_x = (f["ankle"].x + f["foot"].x) / 2
    direction = 1.0 if f["foot"].x > f["hip"].x else -1.0  # куда «смотрит» велосипедист
    return scale.to_mm((f["knee"].x - pedal_x) * direction)
