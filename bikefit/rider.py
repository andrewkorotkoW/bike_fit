"""Антропометрия райдера и что из неё можно вывести до анализа фото.

Формулы — классические стартовые точки фиттинга, а не истина: они не знают
длину стопы, гибкость и стиль педалирования. Их задача — дать разумную
отправную высоту седла и ширину руля, а дальше уточняет анализ углов.
"""

from __future__ import annotations

from dataclasses import dataclass

from .bikes import BikeGeometry


@dataclass(frozen=True, slots=True)
class Rider:
    height_cm: float | None = None
    inseam_cm: float | None = None      # внутренняя длина ноги: пол → промежность, без обуви
    arm_cm: float | None = None         # акромион → кончик среднего пальца;
                                        # пока справочно: войдёт в модель вылета кокпита
    shoulder_cm: float | None = None    # между акромионами (костные выступы плеч)

    def is_empty(self) -> bool:
        return all(v is None for v in (self.height_cm, self.inseam_cm,
                                       self.arm_cm, self.shoulder_cm))

    # ------------------------------------------------------------ седло
    def saddle_height_lemond_mm(self) -> float | None:
        """LeMond: центр каретки → верх седла вдоль подседельной = 0.883 × inseam."""
        return None if self.inseam_cm is None else self.inseam_cm * 10 * 0.883

    def saddle_height_hamley_mm(self) -> float | None:
        """Hamley & Thomas (1967): ось педали в НМТ → верх седла = 1.09 × inseam."""
        return None if self.inseam_cm is None else self.inseam_cm * 10 * 1.09

    # ------------------------------------------------------------ кокпит
    def bar_width_mm(self, gravel: bool = False) -> float | None:
        """Ширина руля (центр–центр) ≈ ширина плеч; на гравии часто +20 мм
        ради контроля. Округление до шага 20 мм, как выпускают рули."""
        if self.shoulder_cm is None:
            return None
        base = self.shoulder_cm * 10 + (20 if gravel else 0)
        return round(base / 20) * 20

    # ------------------------------------------------------------ рама
    def frame_size_warning(self, bike: BikeGeometry) -> str | None:
        if self.height_cm is None:
            return None
        lo, hi = bike.rider_height_cm
        if lo <= self.height_cm <= hi:
            return None
        side = "меньше" if self.height_cm < lo else "больше"
        return (
            f"Рост {self.height_cm:g} см {side} диапазона производителя для "
            f"{bike.title} ({lo}–{hi} см). Рама может быть не того размера — "
            "компенсация выносом/подседельным штырём ограничена."
        )

    def notes(self, bike: BikeGeometry | None = None,
              gravel: bool = False) -> list[str]:
        """Справочные ориентиры для отчёта."""
        out: list[str] = []
        lemond, hamley = self.saddle_height_lemond_mm(), self.saddle_height_hamley_mm()
        if lemond is not None:
            out.append(
                f"Стартовая высота седла по inseam {self.inseam_cm:g} см: "
                f"{lemond:.0f} мм от центра каретки до верха седла вдоль подседельной "
                f"(LeMond, 0.883×), либо {hamley:.0f} мм от оси педали в НМТ (Hamley, 1.09×). "
                "Это точка отсчёта, финальную высоту задаёт угол колена."
            )
        bw = self.bar_width_mm(gravel)
        if bw is not None:
            line = f"Ширина руля по плечам {self.shoulder_cm:g} см: ~{bw:.0f} мм центр–центр"
            if bike is not None and bike.bar_width_mm:
                diff = bw - bike.bar_width_mm
                if abs(diff) >= 20:
                    line += (f"; штатный руль {bike.bar_width_mm:g} мм — "
                             f"{'уже' if diff > 0 else 'шире'} на {abs(diff):.0f} мм")
                else:
                    line += f"; штатный руль {bike.bar_width_mm:g} мм подходит"
            out.append(line + ".")
        return out
