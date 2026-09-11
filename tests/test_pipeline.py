"""Тесты аналитики на синтетических точках — без MediaPipe и реальных фото.

Строим «велосипедиста» из координат с заранее известными углами и проверяем,
что геометрия, правила рекомендаций, разметка и текстовый отчёт согласованы.
"""

import math
import unittest

import numpy as np

from bikefit import geometry as G
from bikefit.analyzer import (
    FitReport, _BDC, _TDC, build_recommendations, collect_metrics,
)
from bikefit.bikes import (
    BIANCHI_IMPULSO_COMP_LG as BIKE_BIANCHI, ROSE_BACKROAD_L, ROSE_BACKROAD_ML, get_bike,
)
from bikefit.pose import Point, PoseFrame
from bikefit.references import get_profile
from bikefit.report import annotate, render_text


def _pt(x, y, vis=0.95):
    return Point(float(x), float(y), vis)


def _rider(knee_deg: float, elbow_deg: float = 155.0, torso_deg: float = 50.0) -> PoseFrame:
    """Скелет сбоку, ось Y вниз. Бедро 400 px, голень 400 px, стопа вправо."""
    hip = (500.0, 500.0)
    knee = (hip[0] + 150.0, hip[1] + 370.0)
    # лодыжка: поворачиваем голень вокруг колена так, чтобы угол таз-колено-лодыжка = knee_deg
    femur = np.array(hip) - np.array(knee)
    ang = math.atan2(femur[1], femur[0]) - math.radians(knee_deg)
    ankle = (knee[0] + 400 * math.cos(ang), knee[1] + 400 * math.sin(ang))
    foot = (ankle[0] + 90.0, ankle[1] + 20.0)
    heel = (ankle[0] - 40.0, ankle[1] + 30.0)
    # корпус под torso_deg к горизонту, вперёд (вправо) и вверх
    shoulder = (hip[0] + 450 * math.cos(math.radians(torso_deg)),
                hip[1] - 450 * math.sin(math.radians(torso_deg)))
    # рука вниз-вперёд от плеча, локоть с заданным углом
    upper = np.array([120.0, 250.0])
    elbow = tuple(np.array(shoulder) + upper)
    a2 = math.atan2(-upper[1], -upper[0]) - math.radians(elbow_deg)
    wrist = (elbow[0] + 250 * math.cos(a2), elbow[1] + 250 * math.sin(a2))
    pts = {
        "shoulder": _pt(*shoulder), "elbow": _pt(*elbow), "wrist": _pt(*wrist),
        "hip": _pt(*hip), "knee": _pt(*knee), "ankle": _pt(*ankle),
        "heel": _pt(*heel), "foot": _pt(*foot),
    }
    return PoseFrame(points=pts, side="right",
                     image=np.zeros((1200, 1400, 3), dtype=np.uint8))


class GeometryTest(unittest.TestCase):
    def test_angle_at_matches_construction(self):
        for deg in (90, 120, 145, 170):
            f = _rider(deg)
            self.assertAlmostEqual(G.knee_angle(f), deg, places=5)

    def test_torso_angle(self):
        self.assertAlmostEqual(G.torso_angle(_rider(145, torso_deg=42)), 42, places=5)

    def test_elbow_angle(self):
        self.assertAlmostEqual(G.elbow_angle(_rider(145, elbow_deg=100)), 100, places=5)

    def test_linear_delta_sign(self):
        # выпрямить колено -> расстояние таз-педаль растёт
        self.assertGreater(G.linear_delta_px(400, 400, 140, 150), 0)
        self.assertLess(G.linear_delta_px(400, 400, 150, 140), 0)

    def test_scale(self):
        s = G.Scale.from_two_points((0, 0), (0, 345), 172.5)
        self.assertAlmostEqual(s.to_mm(690), 345.0)
        with self.assertRaises(ValueError):
            G.Scale.from_two_points((0, 0), (0, 0.5), 172.5)


class AnalyzerTest(unittest.TestCase):
    def _report(self, knee, scale=None, tdc=None, **kw):
        profile = get_profile("road_endurance")
        bdc = _rider(knee, **kw)
        frames = {_BDC: bdc} | ({_TDC: tdc} if tdc else {})
        rep = FitReport(profile=profile, calibrated=scale is not None, frames=frames)
        rep.metrics = collect_metrics(profile, bdc, tdc, scale)
        rep.recommendations = build_recommendations(rep, bdc, scale)
        return rep

    def test_all_ok_yields_leave_as_is(self):
        rep = self._report(146, elbow_deg=155, torso_deg=50)
        by_key = {m.key: m for m in rep.metrics}
        for key in ("knee_extension", "torso", "elbow"):
            self.assertTrue(by_key[key].ok, by_key[key])
        parts = [r.part for r in rep.recommendations]
        self.assertNotIn("Седло", parts)

    def test_knee_too_straight_lowers_saddle_with_mm(self):
        scale = G.Scale(mm_per_px=0.5)
        rep = self._report(160, scale=scale)
        rec = next(r for r in rep.recommendations if r.part == "Седло")
        self.assertEqual(rec.action, "опустить")
        self.assertIsNotNone(rec.amount_mm)
        self.assertLess(rec.amount_mm, 0)         # знак: уменьшить расстояние
        self.assertGreater(abs(rec.amount_mm), 5)  # 160 -> ~144° на 400px сегментах — десятки мм
        self.assertEqual(rep.recommendations[0].priority, 1)

    def test_knee_too_bent_raises_saddle_without_scale(self):
        rep = self._report(130)
        rec = next(r for r in rep.recommendations if r.part == "Седло")
        self.assertEqual(rec.action, "поднять")
        self.assertIsNone(rec.amount_mm)
        self.assertNotIn("на ~", rec.render())  # без калибровки нет «на ~N мм»

    def test_tdc_metrics_present(self):
        rep = self._report(146, tdc=_rider(72))
        keys = {m.key for m in rep.metrics}
        self.assertIn("knee_flexion", keys)
        self.assertIn("hip_closed", keys)

    def test_metric_frame_names_match_report_frames(self):
        """Регрессия: annotate сопоставляет m.frame с ключами report.frames."""
        rep = self._report(146, tdc=_rider(72))
        for m in rep.metrics:
            self.assertIn(m.frame, set(rep.frames) | {"any"}, m.key)

    def test_to_dict_serialisable(self):
        import json
        rep = self._report(160, scale=G.Scale(0.5), tdc=_rider(72))
        json.dumps(rep.to_dict(), ensure_ascii=False)


class ProfilesTest(unittest.TestCase):
    def test_all_profiles_have_same_metric_keys(self):
        from bikefit.references import PROFILES
        keys = {name: set(p.ranges) for name, p in PROFILES.items()}
        ref = keys["road_endurance"]
        for name, k in keys.items():
            self.assertEqual(k, ref, name)
        self.assertIn("gravel", PROFILES)
        for p in PROFILES.values():
            for key, r in p.ranges.items():
                self.assertLess(r.lo, r.hi, f"{p.name}.{key}")


class BikeTest(unittest.TestCase):
    def test_lookup(self):
        self.assertIs(get_bike("rose_backroad_l"), ROSE_BACKROAD_L)
        self.assertIsNone(get_bike(None))
        with self.assertRaises(ValueError):
            get_bike("nope")

    def test_all_bikes_consistent(self):
        from bikefit.bikes import BIKES
        for b in BIKES.values():
            self.assertGreater(b.stack_mm, b.reach_mm, b.key)
            self.assertTrue(60 < b.head_angle_deg < 80 and 68 < b.seat_angle_deg < 82, b.key)
            self.assertAlmostEqual(b.wheelbase_mm, b.chainstay_mm + (b.wheelbase_mm - b.chainstay_mm))
            self.assertGreater(b.wheelbase_mm - b.chainstay_mm, 550, b.key)  # front centre
            self.assertIn("База (ось колеса → ось колеса)", b.calibration_options())

    def test_setback_to_height(self):
        b = ROSE_BACKROAD_L
        dh = b.height_change_for_setback_mm(10)   # 10 мм вперёд
        # cos(73.78°) ≈ 0.279 → седло ближе к каретке на ~2.8 мм
        self.assertAlmostEqual(dh, -2.79, places=1)
        self.assertAlmostEqual(b.height_change_for_setback_mm(-10), -dh)

    def test_calibration_options(self):
        opts = ROSE_BACKROAD_L.calibration_options()
        self.assertAlmostEqual(opts["База (ось колеса → ось колеса)"], 1063.81)
        self.assertIsNone(ROSE_BACKROAD_L.wheel_outer_diameter_mm())
        self.assertEqual(ROSE_BACKROAD_L.wheel_outer_diameter_mm(45), 622 + 90)

    def test_kops_recommendation_uses_bike_geometry(self):
        profile = get_profile("road_endurance")
        bdc, hcr = _rider(146), _rider(150)
        self.assertGreater(hcr["foot"].x, hcr["hip"].x)  # райдер «смотрит» вправо
        # колено на 60 мм впереди оси педали (середина лодыжка↔плюсна): седло назад
        pedal_x = (hcr["ankle"].x + hcr["foot"].x) / 2
        hcr.points["knee"] = _pt(pedal_x + 60, hcr["knee"].y)
        scale = G.Scale(mm_per_px=1.0)
        rep = FitReport(profile=profile, frames={_BDC: bdc}, calibrated=True,
                        bike=ROSE_BACKROAD_L)
        rep.metrics = collect_metrics(profile, bdc, None, scale, hcr)
        rep.recommendations = build_recommendations(rep, bdc, scale)
        back = next(r for r in rep.recommendations if "назад" in r.action)
        fix = next(r for r in rep.recommendations if r.action.startswith("после сдвига"))
        # назад = дальше от каретки = эффективно выше → опустить
        self.assertEqual(fix.action, "после сдвига опустить седло")
        self.assertAlmostEqual(fix.amount_mm, back.amount_mm * math.cos(math.radians(73.78)), places=3)
        self.assertEqual(rep.to_dict()["bike"], "rose_backroad_l")


class RiderTest(unittest.TestCase):
    def test_formulas(self):
        from bikefit.rider import Rider
        r = Rider(186, 87.5, 81, 46)
        self.assertAlmostEqual(r.saddle_height_lemond_mm(), 772.6, places=1)
        self.assertAlmostEqual(r.saddle_height_hamley_mm(), 953.75, places=1)
        self.assertEqual(r.bar_width_mm(), 460)
        self.assertEqual(r.bar_width_mm(gravel=True), 480)
        self.assertTrue(Rider().is_empty())
        self.assertIsNone(Rider().saddle_height_lemond_mm())

    def test_frame_size_warning_and_notes(self):
        from bikefit.rider import Rider
        r = Rider(186, 87.5, 81, 46)
        self.assertIsNone(r.frame_size_warning(BIKE_BIANCHI))
        self.assertIn("больше диапазона", r.frame_size_warning(ROSE_BACKROAD_ML))
        notes = r.notes(BIKE_BIANCHI, gravel=True)
        self.assertEqual(len(notes), 2)
        self.assertIn("773 мм", notes[0])
        self.assertIn("480 мм", notes[1])
        self.assertIn("уже на 60 мм", notes[1])

    def test_rider_in_report(self):
        from bikefit.analyzer import _apply_rider
        from bikefit.rider import Rider
        profile = get_profile("gravel")
        rep = FitReport(profile=profile, frames={_BDC: _rider(146)},
                        bike=ROSE_BACKROAD_ML, rider=Rider(186, 87.5))
        _apply_rider(rep)
        self.assertEqual(len(rep.notes), 1)
        self.assertEqual(len(rep.warnings), 1)  # рост вне диапазона M/L
        self.assertIn("notes", rep.to_dict())
        self.assertIn("ОРИЕНТИРЫ", render_text(rep))


class VideoCyclesTest(unittest.TestCase):
    @staticmethod
    def _series(n_cycles=6, period=20, noise=0.0, outlier_at=None):
        """Синусоида колена 72°..146° как в реальном педалировании + выброс."""
        import random
        rnd = random.Random(1)
        frames = []
        for i in range(n_cycles * period):
            ang = 109 + 37 * math.cos(2 * math.pi * i / period) + rnd.uniform(-noise, noise)
            if outlier_at is not None and i == outlier_at:
                ang = 172  # «рекордный» кадр с ошибкой детекции
            f = _rider(ang)
            f.frame_index = i
            frames.append(f)
        return frames

    def test_median_ignores_outlier(self):
        from bikefit.analyzer import pick_cycle_frames
        frames = self._series(noise=1.0, outlier_at=45)
        bdc, tdc, stats = pick_cycle_frames(frames)
        self.assertIsNotNone(stats)
        self.assertGreaterEqual(stats.cycles, 4)
        self.assertAlmostEqual(stats.bdc_median, 146, delta=2)
        self.assertAlmostEqual(stats.tdc_median, 72, delta=2)
        self.assertLess(stats.bdc_spread, 3)
        self.assertNotEqual(bdc.frame_index, 45)          # выброс не выбран как НМТ
        self.assertAlmostEqual(G.knee_angle(bdc), stats.bdc_median, delta=2)

    def test_short_video_falls_back_to_extremes(self):
        from bikefit.analyzer import pick_cycle_frames
        frames = self._series(n_cycles=1, period=8)
        bdc, tdc, stats = pick_cycle_frames(frames)
        self.assertIsNone(stats)
        self.assertGreater(G.knee_angle(bdc), G.knee_angle(tdc))

    def test_overrides_applied_to_metrics(self):
        profile = get_profile("gravel")
        bdc = _rider(160)
        ms = collect_metrics(profile, bdc, None, None, overrides={"knee_extension": 146.0})
        self.assertEqual(next(m for m in ms if m.key == "knee_extension").value, 146.0)


class PdfTest(unittest.TestCase):
    def test_build_pdf_bytes(self):
        from bikefit.pdf_report import build_pdf
        from bikefit.rider import Rider
        profile = get_profile("gravel")
        bdc, tdc = _rider(160), _rider(70)
        rep = FitReport(profile=profile, frames={_BDC: bdc, _TDC: tdc},
                        bike=ROSE_BACKROAD_ML, rider=Rider(186, 87.5, 81, 46), calibrated=True)
        rep.metrics = collect_metrics(profile, bdc, tdc, G.Scale(0.5))
        rep.recommendations = build_recommendations(rep, bdc, G.Scale(0.5))
        rep.notes = ["заметка"]; rep.warnings = ["предупреждение"]
        data = build_pdf(rep)
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertGreater(len(data), 20_000)  # два JPEG-кадра внутри


class GuidePdfTest(unittest.TestCase):
    def test_guide_pdf(self):
        from bikefit.pdf_report import build_guide_pdf
        data = build_guide_pdf(get_profile("gravel"))
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertGreater(len(data), 30_000)

    def test_svglib_fonts_registered_even_if_reportlab_already_has_them(self):
        """Регрессия: квадраты вместо кириллицы в схемах PDF."""
        import os
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.graphics.shapes import String
        from svglib.svglib import svg2rlg
        from bikefit import guide
        from bikefit.pdf_report import _font_dir, _register_fonts
        # имитация процесса, где reportlab-шрифт уже зарегистрирован старым кодом
        if "DejaVuSans" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("DejaVuSans", os.path.join(_font_dir(), "DejaVuSans.ttf")))
        _register_fonts()
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False, encoding="utf-8") as fh:
            fh.write(guide.svg_crank_positions(guide.LIGHT)); path = fh.name
        d = svg2rlg(path); os.unlink(path)
        fonts = set()
        def walk(n):
            for c in getattr(n, "contents", []):
                if isinstance(c, String): fonts.add(c.fontName)
                walk(c)
        walk(d)
        self.assertTrue(fonts and fonts <= {"DejaVuSans", "DejaVuSans-Bold"}, fonts)

    def test_svgs_are_well_formed(self):
        import xml.etree.ElementTree as ET
        from bikefit import guide
        for fn in (guide.svg_camera_top_view, guide.svg_camera_side_view, guide.svg_crank_positions):
            for pal in (guide.DARK, guide.LIGHT):
                ET.fromstring(fn(pal))
        ET.fromstring(guide.svg_angles(get_profile("tt"), guide.LIGHT))


class ReportTest(unittest.TestCase):
    def test_render_text_and_annotate(self):
        profile = get_profile("road_race")
        bdc, tdc = _rider(160), _rider(70)
        rep = FitReport(profile=profile, frames={_BDC: bdc, _TDC: tdc})
        rep.metrics = collect_metrics(profile, bdc, tdc, None)
        rep.recommendations = build_recommendations(rep, bdc, None)
        text = render_text(rep)
        self.assertIn("Профиль:", text)
        self.assertIn("РЕКОМЕНДАЦИИ", text)

        img = annotate(bdc, rep, _BDC)
        self.assertEqual(img.shape, bdc.image.shape)
        # на кадре НМТ подписан угол колена: рядом с коленом есть закрашенные пиксели
        kx, ky = int(bdc["knee"].x), int(bdc["knee"].y)
        patch = img[ky - 5:ky + 5, kx - 5:kx + 5]
        self.assertGreater(patch.sum(), 0)


if __name__ == "__main__":
    unittest.main()
