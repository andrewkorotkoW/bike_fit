"""Геометрия конкретных велосипедов.

Зачем это аналитике:
  * калибровка масштаба — база (wheelbase) и наружный диаметр колеса известны
    из геометрии, их проще отметить на фото, чем ось педали;
  * угол подседельной трубы — точный пересчёт «сдвинул седло по рельсам →
    изменилась эффективная высота» вместо эмпирических 3–4 мм на 10 мм;
  * длина шатуна — если известна комплектация, не надо вводить руками.

Rose маркирует размеры и буквой, и «frame height» в см (XS=50 … M/L=57, L=59),
поэтому в названии указаны оба. Числа берутся с официальной таблицы
производителя и сохраняются как есть,
с указанием источника. Длина шатуна/выноса зависит от комплектации, поэтому
None, пока не уточнена по конкретному велосипеду.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BikeGeometry:
    key: str
    title: str
    size: str
    model_year: int
    # рама, мм и градусы — обозначения как в таблице Rose (A, B, C, ...)
    seat_tube_mm: float          # A  длина подседельной трубы
    top_tube_mm: float           # B  эффективная верхняя труба
    head_tube_mm: float          # C  длина рулевого стакана
    head_angle_deg: float        # D  угол рулевой
    seat_angle_deg: float        # E  угол подседельной трубы
    eff_seat_angle_deg: float    # E2 эффективный угол подседельной трубы
    bb_drop_mm: float            # F  занижение каретки
    chainstay_mm: float          # G  длина перьев
    wheelbase_mm: float          # H  база
    reach_mm: float              # J
    stack_mm: float              # K
    standover_mm: float | None   # M  стендовер (не все производители публикуют)
    fork_offset_mm: float        # P  вынос вилки
    trail_mm: float | None       # P1 трейл
    fork_length_mm: float        # U  длина вилки
    rim_etrto_mm: float          # посадочный диаметр обода (622 = 28"/700c)
    max_tyre_mm: float           # R1 максимальная ширина покрышки
    rider_height_cm: tuple[int, int]
    # комплектация — зависит от сборки, уточняется по своему велосипеду
    crank_mm: float | None = None
    stem_mm: float | None = None
    bar_width_mm: float | None = None  # руль центр–центр
    tyre_mm: float | None = None       # установленная покрышка
    source: str = ""

    # ------------------------------------------------------------ калибровка
    def wheel_outer_diameter_mm(self, tyre_mm: float | None = None) -> float | None:
        """Наружный диаметр колеса ≈ ETRTO + 2 × ширина покрышки (приближение:
        высота покрышки ≈ её ширине). Для калибровки по колесу."""
        t = tyre_mm if tyre_mm is not None else self.tyre_mm
        if t is None:
            return None
        return self.rim_etrto_mm + 2 * t

    def calibration_options(self) -> dict[str, float]:
        """Что можно отметить на фото и какой длине в мм это соответствует."""
        out: dict[str, float] = {"База (ось колеса → ось колеса)": self.wheelbase_mm}
        if self.crank_mm:
            out["Шатун (ось каретки → ось педали)"] = self.crank_mm
        d = self.wheel_outer_diameter_mm()
        if d:
            out["Наружный диаметр колеса"] = d
        return out

    # ------------------------------------------------------------ седло
    def height_change_for_setback_mm(self, setback_mm: float) -> float:
        """На сколько мм изменится расстояние каретка→седло, если сдвинуть
        седло по рельсам горизонтально на setback_mm (+ = вперёд).

        Седло движется по горизонтали, высота считается вдоль подседельной
        трубы под углом θ к горизонту: проекция сдвига на ось трубы = d·cos θ.
        Сдвиг вперёд приближает седло к каретке → знак минус.
        """
        return -setback_mm * math.cos(math.radians(self.eff_seat_angle_deg))


ROSE_BACKROAD_L = BikeGeometry(
    key="rose_backroad_l",
    title="Rose Backroad (карбон, 2025) — размер L (59)",
    size="L",
    model_year=2025,
    seat_tube_mm=531,
    top_tube_mm=590,
    head_tube_mm=167,
    head_angle_deg=71.5,
    seat_angle_deg=73.75,
    eff_seat_angle_deg=73.78,
    bb_drop_mm=78,
    chainstay_mm=430,
    wheelbase_mm=1063.81,
    reach_mm=412.31,
    stack_mm=610.5,
    standover_mm=837,
    fork_offset_mm=48,
    trail_mm=69,
    fork_length_mm=410,
    rim_etrto_mm=622,
    max_tyre_mm=53,
    rider_height_cm=(185, 191),
    crank_mm=None,   # зависит от комплектации — уточнить по своему велосипеду
    stem_mm=None,
    tyre_mm=None,
    source="rosebikes.com, карточка Backroad GRX 820, вкладка Frame geometry, размер L",
)

ROSE_BACKROAD_ML = BikeGeometry(
    key="rose_backroad_ml",
    title="Rose Backroad (карбон, 2025) — размер M/L (57)",
    size="M/L",
    model_year=2025,
    seat_tube_mm=511,
    top_tube_mm=575,
    head_tube_mm=157,
    head_angle_deg=71.25,
    seat_angle_deg=74,
    eff_seat_angle_deg=73.85,
    bb_drop_mm=78,
    chainstay_mm=425,
    wheelbase_mm=1048.74,
    reach_mm=403.22,
    stack_mm=599.58,
    standover_mm=823,
    fork_offset_mm=48,
    trail_mm=71,
    fork_length_mm=410,
    rim_etrto_mm=622,
    max_tyre_mm=53,
    rider_height_cm=(180, 184),
    crank_mm=175.0,   # комплектация владельца
    stem_mm=None,     # не измерен
    tyre_mm=40.0,     # установленная покрышка, мм
    source="rosebikes.com, карточка Backroad GRX 820, вкладка Frame geometry, размер M/L",
)

BIANCHI_IMPULSO_COMP_LG = BikeGeometry(
    key="bianchi_impulso_comp_lg",
    title="Bianchi Impulso Comp (карбон) — размер LG",
    size="LG",
    model_year=2026,
    # таблица Bianchi без легенды; колонки сопоставлены по значениям:
    # A подседельная, B1 верхняя труба, C перья, D BB drop, E рулевой стакан,
    # F front centre, G угол подседельной, G1 угол рулевой, H вынос вилки,
    # I длина вилки, X reach, Y stack, W база
    seat_tube_mm=520,
    top_tube_mm=572,
    head_tube_mm=162,
    head_angle_deg=71.5,
    seat_angle_deg=73.5,
    eff_seat_angle_deg=73.5,   # эффективный не публикуется — берём фактический
    bb_drop_mm=70,
    chainstay_mm=426,
    wheelbase_mm=1045,
    reach_mm=401,
    stack_mm=580,
    standover_mm=None,
    fork_offset_mm=50,
    trail_mm=None,
    fork_length_mm=391,
    rim_etrto_mm=622,
    max_tyre_mm=42,
    rider_height_cm=(180, 188),  # ориентировочно, Bianchi даёт только размер
    # штатная комплектация Impulso Comp GRX 610, размер LG
    crank_mm=172.5,
    stem_mm=100,
    bar_width_mm=420,
    tyre_mm=40,                  # Pirelli Cinturato Gravel H 40-622
    source="bianchi.com, страница Impulso, «Size & Frame geometry» + спецификация Impulso Comp",
)

BIKES: dict[str, BikeGeometry] = {
    b.key: b for b in (ROSE_BACKROAD_ML, ROSE_BACKROAD_L, BIANCHI_IMPULSO_COMP_LG)
}


def get_bike(key: str | None) -> BikeGeometry | None:
    if not key:
        return None
    try:
        return BIKES[key]
    except KeyError:
        raise ValueError(
            f"Неизвестный велосипед {key!r}. Доступны: {', '.join(BIKES)}"
        ) from None
