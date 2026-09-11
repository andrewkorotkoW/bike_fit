"""Аналитика посадки: метрики -> отклонения -> рекомендации по регулировкам.

Порядок правок повторяет протокол живого фиттинга:
  1) стопа/шипы, 2) высота седла, 3) вынос седла вперёд-назад, 4) кокпит.
Менять кокпит раньше седла бессмысленно: сдвинули седло — поехал и вылет.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
import statistics
from typing import Iterable, Sequence

from . import geometry as G
from .bikes import BikeGeometry, get_bike
from .rider import Rider
from .pose import PoseEstimator, PoseFrame, load_image
from .references import Profile, Range, get_profile

log = logging.getLogger(__name__)

# какой кадр нужен для каждой метрики
# Значения совпадают с ключами FitReport.frames: по ним report.annotate
# понимает, какие метрики подписывать на каком кадре.
_BDC = "НМТ"   # нижняя мёртвая точка (шатун вниз по оси подседельной трубы)
_TDC = "ВМТ"   # верхняя мёртвая точка
_ANY = "any"


@dataclass(slots=True)
class Metric:
    key: str
    title: str
    value: float
    unit: str
    ref: Range
    frame: str

    @property
    def deviation(self) -> float:
        return self.ref.deviation(self.value)

    @property
    def ok(self) -> bool:
        return abs(self.deviation) < 1e-6

    @property
    def target(self) -> float:
        return self.ref.target(self.value)


@dataclass(slots=True)
class Recommendation:
    priority: int
    part: str            # что крутим
    action: str          # что делаем
    amount_mm: float | None
    reason: str
    metrics: tuple[str, ...] = ()

    def render(self) -> str:
        amount = f" на ~{abs(self.amount_mm):.0f} мм" if self.amount_mm else ""
        return f"[{self.part}] {self.action}{amount} — {self.reason}"


@dataclass(slots=True)
class FitReport:
    profile: Profile
    metrics: list[Metric] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    calibrated: bool = False
    frames: dict[str, PoseFrame] = field(default_factory=dict)
    bike: BikeGeometry | None = None
    rider: Rider | None = None
    notes: list[str] = field(default_factory=list)

    def metric(self, key: str) -> Metric | None:
        return next((m for m in self.metrics if m.key == key), None)

    def to_dict(self) -> dict:
        return {
            "profile": self.profile.name,
            "bike": self.bike.key if self.bike else None,
            "calibrated": self.calibrated,
            "metrics": [
                {
                    "key": m.key, "title": m.title, "value": round(m.value, 1),
                    "unit": m.unit, "ok": m.ok,
                    "range": [m.ref.lo, m.ref.hi],
                    "deviation": round(m.deviation, 1),
                }
                for m in self.metrics
            ],
            "recommendations": [
                {
                    "priority": r.priority, "part": r.part, "action": r.action,
                    "amount_mm": None if r.amount_mm is None else round(r.amount_mm, 1),
                    "reason": r.reason,
                }
                for r in self.recommendations
            ],
            "warnings": self.warnings,
            "notes": self.notes,
        }


# --------------------------------------------------------------- сбор метрик
def _quality_checks(frames: dict[str, PoseFrame]) -> list[str]:
    warns: list[str] = []
    for name, f in frames.items():
        vis = f.min_visibility()
        if vis < 0.6:
            warns.append(
                f"Кадр «{name}»: низкая уверенность детекции ({vis:.2f}). "
                "Снимайте строго сбоку, в облегающей одежде, без затенения ног."
            )
    return warns


def collect_metrics(profile: Profile, bdc: PoseFrame, tdc: PoseFrame | None,
                    scale: G.Scale | None,
                    horizontal_crank: PoseFrame | None = None,
                    overrides: dict[str, float] | None = None) -> list[Metric]:
    """overrides — значения метрик, усреднённые по видео; кадр bdc/tdc тогда
    нужен только для длин сегментов и разметки."""
    r = profile.ranges
    out = [
        Metric("knee_extension", "Колено, нижняя мёртвая точка",
               G.knee_angle(bdc), "°", r["knee_extension"], _BDC),
        Metric("torso", "Наклон корпуса к горизонту",
               G.torso_angle(bdc), "°", r["torso"], _ANY),
        Metric("shoulder", "Плечо (таз—плечо—кисть)",
               G.shoulder_angle(bdc), "°", r["shoulder"], _ANY),
        Metric("elbow", "Локоть",
               G.elbow_angle(bdc), "°", r["elbow"], _ANY),
        Metric("ankle", "Голеностоп в нижней точке",
               G.ankle_angle(bdc), "°", r["ankle"], _BDC),
    ]
    if tdc is not None:
        out += [
            Metric("knee_flexion", "Колено, верхняя мёртвая точка",
                   G.knee_angle(tdc), "°", r["knee_flexion"], _TDC),
            Metric("hip_closed", "Открытие таза, верхняя мёртвая точка",
                   G.hip_angle(tdc), "°", r["hip_closed"], _TDC),
        ]
    if horizontal_crank is not None and scale is not None:
        out.append(
            Metric("kops_mm", "KOPS: колено над осью педали",
                   G.kops_offset_mm(horizontal_crank, scale), "мм", r["kops_mm"], _ANY)
        )
    for m in out:
        if overrides and m.key in overrides:
            m.value = overrides[m.key]
    return out


# ------------------------------------------------------------ правила вывода
def build_recommendations(report: FitReport, bdc: PoseFrame,
                          scale: G.Scale | None) -> list[Recommendation]:
    recs: list[Recommendation] = []
    m = report.metric
    bike = report.bike

    # 1. Высота седла — самая влиятельная регулировка
    ke = m("knee_extension")
    if ke and not ke.ok:
        delta = (
            G.saddle_height_delta_mm(bdc, ke.value, ke.target, scale)
            if scale else None
        )
        if ke.deviation > 0:      # нога слишком прямая
            recs.append(Recommendation(
                1, "Седло", "опустить", delta,
                f"колено разгибается до {ke.value:.0f}° при норме "
                f"{ke.ref.lo:.0f}–{ke.ref.hi:.0f}°: таз будет раскачиваться, "
                "риск боли под коленом сзади и в подколенном сухожилии",
                ("knee_extension",),
            ))
        else:                     # нога слишком согнута
            recs.append(Recommendation(
                1, "Седло", "поднять", delta,
                f"колено разгибается лишь до {ke.value:.0f}° при норме "
                f"{ke.ref.lo:.0f}–{ke.ref.hi:.0f}°: перегруз передней части "
                "колена и потеря мощности",
                ("knee_extension",),
            ))

    # Голеностоп подтверждает или опровергает диагноз по седлу
    ank = m("ankle")
    if ank and ke and ank.deviation > 0 and ke.deviation > 0:
        recs.append(Recommendation(
            1, "Седло", "проверить высоту повторно после правки", None,
            "сильное подошвенное сгибание стопы в нижней точке — типичный признак "
            "«тянущегося» к педали райдера, косвенно подтверждает завышенное седло",
            ("ankle", "knee_extension"),
        ))

    # 2. Положение седла вперёд-назад
    kops = m("kops_mm")
    if kops and not kops.ok:
        amount = abs(kops.deviation)
        if kops.deviation > 0:
            recs.append(Recommendation(
                2, "Седло", "сдвинуть назад по рельсам", amount,
                f"колено на {kops.value:.0f} мм впереди оси педали — перегружается "
                "передняя поверхность колена и кисти",
                ("kops_mm",),
            ))
        else:
            recs.append(Recommendation(
                2, "Седло", "сдвинуть вперёд по рельсам", amount,
                f"колено на {abs(kops.value):.0f} мм позади оси педали — таз уезжает "
                "назад, теряется опора и мощность на подъёме",
                ("kops_mm",),
            ))
        if bike is not None:
            # знак: сдвиг назад (deviation > 0) удаляет седло от каретки
            setback = -amount if kops.deviation > 0 else amount
            dh = bike.height_change_for_setback_mm(setback)
            fix = "опустить" if dh > 0 else "поднять"
            reason = (
                f"при угле подседельной трубы {bike.eff_seat_angle_deg:g}° сдвиг на "
                f"{amount:.0f} мм меняет расстояние каретка→седло на {abs(dh):.1f} мм"
            )
            recs.append(Recommendation(
                2, "Седло", f"после сдвига {fix} седло", abs(dh), reason, ("kops_mm",),
            ))
        else:
            recs.append(Recommendation(
                2, "Седло", "после сдвига вернуть высоту вдоль оси подседельной трубы", None,
                "сдвиг седла по рельсам меняет эффективную высоту: 10 мм вперёд ≈ "
                "3–4 мм ниже относительно каретки",
            ))

    # 3. Кокпит: вылет и высота руля
    elbow, sh, torso = m("elbow"), m("shoulder"), m("torso")
    hip = m("hip_closed")

    if elbow and not elbow.ok:
        delta = (
            G.reach_delta_mm(bdc, elbow.value, elbow.target, scale) if scale else None
        )
        if elbow.deviation > 0:   # локоть переразогнут
            recs.append(Recommendation(
                3, "Вынос руля", "укоротить (или сдвинуть руль назад)", delta,
                f"локоть выпрямлен до {elbow.value:.0f}° — руки работают как "
                "жёсткая распорка, вся вибрация уходит в кисти и шею",
                ("elbow",),
            ))
        else:
            recs.append(Recommendation(
                3, "Вынос руля", "удлинить", delta,
                f"локоть согнут до {elbow.value:.0f}° — корпус сложен, "
                "не хватает раскрытия и управляемости",
                ("elbow",),
            ))

    if torso and not torso.ok:
        delta = (
            G.bar_height_delta_mm(bdc, torso.value, torso.target, scale)
            if scale else None
        )
        if torso.deviation < 0:   # корпус слишком низко
            recs.append(Recommendation(
                3, "Руль", "поднять (добавить проставки / развернуть вынос вверх)",
                delta,
                f"корпус наклонён до {torso.value:.0f}° при норме "
                f"{torso.ref.lo:.0f}–{torso.ref.hi:.0f}° — характерная причина "
                "боли в пояснице и шее на длинных выездах",
                ("torso",),
            ))
        else:
            recs.append(Recommendation(
                3, "Руль", "опустить (убрать проставки)", delta,
                f"корпус слишком вертикален ({torso.value:.0f}°) — велика парусность, "
                "недогружена передняя часть велосипеда",
                ("torso",),
            ))

    if hip and hip.deviation < 0:
        recs.append(Recommendation(
            2, "Седло / руль", "наклонить нос седла вниз на 1–2° и/или поднять руль",
            None,
            f"таз закрывается до {hip.value:.0f}° в верхней мёртвой точке — "
            "ограничивается ход бедра и дыхание; часто решается доворотом таза, "
            "а не переносом руля",
            ("hip_closed",),
        ))

    if sh and not sh.ok and elbow and elbow.ok:
        direction = "укоротить" if sh.deviation > 0 else "удлинить"
        recs.append(Recommendation(
            3, "Вынос руля", direction, None,
            f"угол плеча {sh.value:.0f}° при норме {sh.ref.lo:.0f}–{sh.ref.hi:.0f}° "
            "при нормальном локте — вопрос длины кокпита, а не посадки рук",
            ("shoulder",),
        ))

    if not recs:
        recs.append(Recommendation(
            3, "Посадка", "оставить как есть", None,
            "все измеренные углы в референсных диапазонах выбранного профиля",
        ))

    recs.sort(key=lambda r: r.priority)
    return recs


def _apply_rider(report: FitReport) -> None:
    """Справочные ориентиры по антропометрии и проверка размера рамы."""
    r = report.rider
    if r is None or r.is_empty():
        return
    gravel = report.profile.name in ("gravel", "mtb_xc")
    report.notes += r.notes(report.bike, gravel)
    if report.bike is not None:
        w = r.frame_size_warning(report.bike)
        if w:
            report.warnings.append(w)


# ------------------------------------------------------------------- фасады
@dataclass(slots=True)
class CycleStats:
    """Сводка по циклам педалирования из видео."""
    cycles: int
    bdc_angles: list[float]
    tdc_angles: list[float]

    @property
    def bdc_median(self) -> float:
        return statistics.median(self.bdc_angles)

    @property
    def tdc_median(self) -> float:
        return statistics.median(self.tdc_angles)

    @staticmethod
    def _robust_spread(values: list[float]) -> float:
        """σ через MAD: один кадр-выброс не раздувает оценку разброса."""
        if len(values) < 2:
            return 0.0
        med = statistics.median(values)
        return 1.4826 * statistics.median(abs(v - med) for v in values)

    @property
    def bdc_spread(self) -> float:
        return self._robust_spread(self.bdc_angles)

    @property
    def tdc_spread(self) -> float:
        return self._robust_spread(self.tdc_angles)


def _estimate_period(series: list[float], min_lag: int = 4) -> int | None:
    """Период колебаний (в отсчётах) по максимуму автокорреляции."""
    n = len(series)
    if n < 3 * min_lag:
        return None
    mean = sum(series) / n
    x = [v - mean for v in series]
    var = sum(v * v for v in x)
    if var < 1e-9:
        return None
    best_lag, best = None, 0.0
    for lag in range(min_lag, n // 2):
        r = sum(x[i] * x[i + lag] for i in range(n - lag)) / var
        if r > best:
            best_lag, best = lag, r
    return best_lag if best > 0.2 else None


def _extrema(series: list[float], window: int, maxima: bool) -> list[int]:
    """Индексы локальных экстремумов, не ближе window/2 друг к другу."""
    half = max(1, window // 2)
    idx = []
    for i, v in enumerate(series):
        lo, hi = max(0, i - half), min(len(series), i + half + 1)
        neigh = series[lo:hi]
        best = max(neigh) if maxima else min(neigh)
        if v == best and (not idx or i - idx[-1] >= half):
            idx.append(i)
    return idx


def pick_cycle_frames(frames: Sequence[PoseFrame]
                      ) -> tuple[PoseFrame, PoseFrame, CycleStats | None]:
    """НМТ/ВМТ по видео: медиана по всем оборотам, а не один экстремальный кадр.

    Один кадр с ошибкой детекции даёт «рекордный» угол и портит отчёт; медиана
    по 5–10 оборотам от этого защищена, а разброс между оборотами — сам по себе
    диагностика (раскачка таза, нестабильная детекция).
    Возвращает кадры, ближайшие к медианным углам, — для разметки и длин сегментов.
    """
    scored = [(G.knee_angle(f), f) for f in frames]
    scored = [(a, f) for a, f in scored if a == a]  # отбрасываем NaN
    if not scored:
        raise RuntimeError("Не удалось измерить угол колена ни на одном кадре")
    angles = [a for a, _ in scored]

    period = _estimate_period(angles)
    if period:
        peaks = _extrema(angles, period, maxima=True)
        troughs = _extrema(angles, period, maxima=False)
    else:
        peaks, troughs = [], []

    if len(peaks) < 2 or len(troughs) < 2:
        # слишком коротко для статистики — старое поведение: max/min
        bdc = max(scored, key=lambda p: p[0])[1]
        tdc = min(scored, key=lambda p: p[0])[1]
        return bdc, tdc, None

    stats = CycleStats(min(len(peaks), len(troughs)),
                       [angles[i] for i in peaks], [angles[i] for i in troughs])
    bdc = min((scored[i] for i in peaks), key=lambda p: abs(p[0] - stats.bdc_median))[1]
    tdc = min((scored[i] for i in troughs), key=lambda p: abs(p[0] - stats.tdc_median))[1]
    return bdc, tdc, stats


def analyze_photos(bdc_path: str, tdc_path: str | None = None,
                   crank_horizontal_path: str | None = None,
                   profile_name: str = "road_endurance",
                   scale: G.Scale | None = None,
                   bike: BikeGeometry | str | None = None,
                   rider: Rider | None = None) -> FitReport:
    """Анализ по фото. bdc_path — снимок с шатуном в нижней мёртвой точке."""
    profile = get_profile(profile_name)
    bike = get_bike(bike) if isinstance(bike, str) else bike
    with PoseEstimator(static=True) as est:
        bdc = est.estimate(load_image(bdc_path))
        if bdc is None:
            raise RuntimeError("На основном фото не найден человек")
        tdc = est.estimate(load_image(tdc_path), side=bdc.side) if tdc_path else None
        hcr = (est.estimate(load_image(crank_horizontal_path), side=bdc.side)
               if crank_horizontal_path else None)

    frames = {_BDC: bdc} | ({_TDC: tdc} if tdc else {})
    report = FitReport(profile=profile, calibrated=scale is not None, frames=frames,
                       bike=bike, rider=rider)
    report.warnings = _quality_checks(frames)
    if tdc is None:
        report.warnings.append(
            "Нет фото с верхней мёртвой точкой: не оценены закрытие таза и "
            "максимальное сгибание колена."
        )
    if scale is None:
        report.warnings.append(
            "Нет калибровки масштаба: рекомендации только по направлению, без миллиметров. "
            "Передайте --calib с известной длиной (например, шатуна)."
        )
    report.metrics = collect_metrics(profile, bdc, tdc, scale, hcr)
    report.recommendations = build_recommendations(report, bdc, scale)
    _apply_rider(report)
    return report


def analyze_video(path: str, profile_name: str = "road_endurance",
                  scale: G.Scale | None = None, step: int = 1,
                  bike: BikeGeometry | str | None = None,
                  rider: Rider | None = None) -> FitReport:
    """Анализ по видео: сам находит НМТ и ВМТ, поэтому надёжнее фото."""
    profile = get_profile(profile_name)
    bike = get_bike(bike) if isinstance(bike, str) else bike
    with PoseEstimator(static=False) as est:
        frames = list(est.iter_video(path, step=step))
    if not frames:
        raise RuntimeError("В видео не найдено ни одного кадра с человеком")

    bdc, tdc, stats = pick_cycle_frames(frames)
    named = {_BDC: bdc, _TDC: tdc}
    report = FitReport(profile=profile, calibrated=scale is not None, frames=named,
                       bike=bike, rider=rider)
    report.warnings = _quality_checks(named)
    overrides = None
    if stats is not None:
        overrides = {"knee_extension": stats.bdc_median, "knee_flexion": stats.tdc_median}
        # корпус, локоть, плечо почти не меняются за оборот — медиана по всем кадрам
        for key, fn in (("torso", G.torso_angle), ("elbow", G.elbow_angle),
                        ("shoulder", G.shoulder_angle)):
            vals = [v for v in (fn(f) for f in frames) if v == v]
            if vals:
                overrides[key] = statistics.median(vals)
        report.notes.append(
            f"Видео: {stats.cycles} оборотов, {len(frames)} кадров. Колено в НМТ "
            f"{stats.bdc_median:.0f}° ± {stats.bdc_spread:.1f}°, в ВМТ "
            f"{stats.tdc_median:.0f}° ± {stats.tdc_spread:.1f}° (медиана и разброс по оборотам)."
        )
        if stats.bdc_spread > 3:
            report.warnings.append(
                f"Разброс угла колена в НМТ между оборотами {stats.bdc_spread:.1f}° — "
                "либо раскачка таза (седло высоко / нестабильная посадка), либо шумная "
                "детекция. Проверьте ракурс и освещение."
            )
    else:
        report.warnings.append(
            "Видео слишком короткое для статистики по оборотам — взяты единичные "
            "кадры max/min угла колена. Снимайте 10–15 с ровного педалирования."
        )
    report.metrics = collect_metrics(profile, bdc, tdc, scale, overrides=overrides)
    report.recommendations = build_recommendations(report, bdc, scale)
    _apply_rider(report)
    return report
