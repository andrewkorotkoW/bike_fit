"""Эталонные диапазоны углов посадки.

Источники диапазонов (сводно, значения усреднены между школами):
  * Holmes J.C. et al. (1994) — угол сгибания колена в НМТ 25–35° (т.е. 145–155°
    по нашему измерению) как зона минимального риска пателлофеморальной боли;
  * Retul / Specialized Body Geometry fit — динамические диапазоны колена,
    бедра, плеча и локтя для шоссе и ТТ;
  * Steve Hogg / bikefit.com — качественные критерии открытия таза и работы стопы;
  * Silberman M.R. et al. (2005), "Road bicycle fit" — обзор клинических рекомендаций.

Важно: это популяционные ориентиры, а не норма для конкретного человека.
Подвижность в тазобедренном суставе, длина сегментов, травмы и задачи гонщика
двигают «правильный» диапазон. Диапазоны редактируются под школу фиттинга,
для этого они вынесены в отдельный модуль и не зашиты в аналитику.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Range:
    lo: float
    hi: float
    priority: int = 2          # 1 — правим первым, 3 — косметика
    note: str = ""

    @property
    def mid(self) -> float:
        return (self.lo + self.hi) / 2

    def deviation(self, value: float) -> float:
        """0 — внутри диапазона; <0 — ниже; >0 — выше."""
        if value < self.lo:
            return value - self.lo
        if value > self.hi:
            return value - self.hi
        return 0.0

    def target(self, value: float) -> float:
        """Ближайшая точка диапазона; целимся не в край, а немного внутрь."""
        if value < self.lo:
            return self.lo + 0.25 * (self.hi - self.lo)
        if value > self.hi:
            return self.hi - 0.25 * (self.hi - self.lo)
        return value


@dataclass(frozen=True, slots=True)
class Profile:
    name: str
    title: str
    ranges: dict[str, Range] = field(default_factory=dict)


_ROAD_ENDURANCE = Profile(
    "road_endurance", "Шоссе / гран-фондо (комфортная посадка)",
    {
        "knee_extension": Range(142, 150, 1, "угол в колене в нижней мёртвой точке"),
        "knee_flexion":   Range(68, 80, 2, "минимальный угол в колене (верх хода)"),
        "hip_closed":     Range(48, 65, 1, "открытие таза в верхней мёртвой точке"),
        "torso":          Range(45, 55, 2, "наклон корпуса к горизонту"),
        "shoulder":       Range(82, 95, 2, "вынос рук относительно корпуса"),
        "elbow":          Range(148, 165, 2, "лёгкий сгиб в локте — амортизация"),
        "ankle":          Range(95, 120, 3, "работа стопы в нижней точке"),
        "kops_mm":        Range(-20, 20, 2, "колено относительно оси педали, мм"),
    },
)

_ROAD_RACE = Profile(
    "road_race", "Шоссе / гонка (агрессивная посадка)",
    {
        "knee_extension": Range(140, 148, 1),
        "knee_flexion":   Range(65, 78, 2),
        "hip_closed":     Range(42, 58, 1),
        "torso":          Range(38, 46, 2),
        "shoulder":       Range(80, 92, 2),
        "elbow":          Range(145, 162, 2),
        "ankle":          Range(95, 120, 3),
        "kops_mm":        Range(-25, 15, 2),
    },
)

_TT = Profile(
    "tt", "Разделка / триатлон (лежак)",
    {
        "knee_extension": Range(138, 146, 1),
        "knee_flexion":   Range(62, 75, 2),
        "hip_closed":     Range(38, 52, 1, "критично: закрытый таз душит дыхание и мощность"),
        "torso":          Range(8, 22, 2, "корпус почти параллелен земле"),
        "shoulder":       Range(88, 100, 2),
        "elbow":          Range(88, 105, 2, "на лежаке локоть согнут ~90°"),
        "ankle":          Range(95, 120, 3),
        "kops_mm":        Range(-5, 40, 2, "на ТТ таз уезжает вперёд — это норма"),
    },
)

_GRAVEL = Profile(
    "gravel", "Гравел / бэкпэкинг",
    # Между шоссейным эндьюрансом и XC: седло как на шоссе, корпус чуть
    # выше и локоть заметно согнут — вибрация на гравии гасится руками,
    # а не жёсткой распоркой. Колено чуть позади оси педали — устойчивость
    # на спусках и длинных подъёмах в седле.
    {
        "knee_extension": Range(140, 150, 1, "угол в колене в нижней мёртвой точке"),
        "knee_flexion":   Range(66, 80, 2, "минимальный угол в колене (верх хода)"),
        "hip_closed":     Range(50, 68, 1, "открытие таза в верхней мёртвой точке"),
        "torso":          Range(46, 58, 2, "чуть выше шоссе: обзор и контроль на спусках"),
        "shoulder":       Range(80, 95, 2, "вынос рук относительно корпуса"),
        "elbow":          Range(140, 160, 2, "согнутый локоть — амортизация на гравии"),
        "ankle":          Range(95, 120, 3, "работа стопы в нижней точке"),
        "kops_mm":        Range(-25, 15, 2, "колено чуть позади оси педали — норма"),
    },
)

_MTB = Profile(
    "mtb_xc", "МТБ / кросс-кантри",
    {
        "knee_extension": Range(140, 150, 1),
        "knee_flexion":   Range(66, 80, 2),
        "hip_closed":     Range(48, 65, 1),
        "torso":          Range(42, 52, 2),
        "shoulder":       Range(78, 92, 2),
        "elbow":          Range(145, 162, 2),
        "ankle":          Range(95, 120, 3),
        "kops_mm":        Range(-30, 10, 2),
    },
)

_CITY = Profile(
    "city", "Город / прогулочный",
    {
        "knee_extension": Range(138, 152, 1, "часто занижают ради постановки ноги на землю"),
        "knee_flexion":   Range(66, 84, 2),
        "hip_closed":     Range(60, 90, 2),
        "torso":          Range(58, 80, 2),
        "shoulder":       Range(70, 95, 3),
        "elbow":          Range(140, 165, 3),
        "ankle":          Range(90, 125, 3),
        "kops_mm":        Range(-40, 20, 3),
    },
)

PROFILES: dict[str, Profile] = {
    p.name: p for p in (_ROAD_ENDURANCE, _ROAD_RACE, _GRAVEL, _TT, _MTB, _CITY)
}

DEFAULT_PROFILE = "road_endurance"


def get_profile(name: str) -> Profile:
    try:
        return PROFILES[name]
    except KeyError:
        raise ValueError(
            f"Неизвестный профиль {name!r}. Доступны: {', '.join(PROFILES)}"
        ) from None
