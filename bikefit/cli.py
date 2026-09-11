"""CLI: python -m bikefit.cli --photo bdc.jpg --tdc tdc.jpg --profile road_race"""

from __future__ import annotations

import argparse
import json
import logging
import sys

import cv2

from .analyzer import analyze_photos, analyze_video
from .bikes import BIKES
from .geometry import Scale
from .references import PROFILES, DEFAULT_PROFILE
from .rider import Rider
from .report import annotate, render_text


def _parse_calib(raw: str | None) -> Scale | None:
    """--calib x1,y1,x2,y2,мм — две точки на фото с известным расстоянием."""
    if not raw:
        return None
    try:
        x1, y1, x2, y2, mm = (float(v) for v in raw.split(","))
    except ValueError:
        raise SystemExit("Формат --calib: x1,y1,x2,y2,длина_в_мм")
    return Scale.from_two_points((x1, y1), (x2, y2), mm)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Анализ велопосадки по фото или видео")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--photo", help="фото сбоку, шатун в нижней мёртвой точке")
    src.add_argument("--video", help="видео сбоку (предпочтительно)")
    ap.add_argument("--tdc", help="второе фото: шатун в верхней мёртвой точке")
    ap.add_argument("--crank-horizontal", help="фото с горизонтальным шатуном (для KOPS)")
    ap.add_argument("--profile", default=DEFAULT_PROFILE, choices=sorted(PROFILES))
    ap.add_argument("--calib", help="x1,y1,x2,y2,мм — калибровка масштаба")
    ap.add_argument("--bike", choices=sorted(BIKES),
                    help="геометрия велосипеда: точный пересчёт сдвига седла, "
                         "подсказки по калибровке")
    rg = ap.add_argument_group("антропометрия райдера, см")
    rg.add_argument("--height", type=float, help="рост")
    rg.add_argument("--inseam", type=float,
                    help="внутренняя длина ноги: пол → промежность, без обуви")
    rg.add_argument("--arm", type=float, help="длина руки: акромион → кончик среднего пальца")
    rg.add_argument("--shoulders", type=float, help="ширина плеч между акромионами")
    ap.add_argument("--json", dest="json_path", help="куда сохранить отчёт в JSON")
    ap.add_argument("--out", help="куда сохранить размеченное изображение")
    ap.add_argument("--pdf", dest="pdf_path", help="куда сохранить PDF-отчёт")
    ap.add_argument("--step", type=int, default=1, help="брать каждый N-й кадр видео")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    scale = _parse_calib(args.calib)
    rider = Rider(args.height, args.inseam, args.arm, args.shoulders)

    if args.video:
        report = analyze_video(args.video, args.profile, scale, args.step, args.bike, rider)
    else:
        report = analyze_photos(args.photo, args.tdc, args.crank_horizontal,
                                args.profile, scale, args.bike, rider)

    print(render_text(report))

    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as fh:
            json.dump(report.to_dict(), fh, ensure_ascii=False, indent=2)

    if args.pdf_path:
        from .pdf_report import build_pdf  # reportlab тяжёлый — импорт по требованию
        with open(args.pdf_path, "wb") as fh:
            fh.write(build_pdf(report))

    if args.out and report.frames:
        name, frame = next(iter(report.frames.items()))
        cv2.imwrite(args.out, annotate(frame, report, name))

    return 0


if __name__ == "__main__":
    sys.exit(main())
