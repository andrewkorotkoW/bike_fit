"""Streamlit UI: streamlit run app.py

MVP-интерфейс: загрузка фото/видео, выбор дисциплины, калибровка по шатуну,
размеченный кадр и список рекомендаций.
"""

from __future__ import annotations

import cv2
import numpy as np
import streamlit as st

from bikefit.analyzer import analyze_photos, analyze_video
from bikefit.bikes import BIKES
from bikefit.geometry import Scale
from bikefit.guide import render_metrics_guide, render_shooting_guide
from bikefit.pdf_report import build_guide_pdf, build_pdf
from bikefit.references import PROFILES
from bikefit.report import annotate
from bikefit.rider import Rider
from bikefit.ui_calib import click_calibration, first_image, save_tmp

st.set_page_config(page_title="Bike Fit", layout="wide")
st.title("Анализ велопосадки по фото")


with st.sidebar:
    st.header("Параметры")
    profile = st.selectbox(
        "Дисциплина", sorted(PROFILES),
        format_func=lambda k: PROFILES[k].title,
    )
    mode = st.radio("Источник", ["Фото", "Видео (точнее)"])
    bike_key = st.selectbox(
        "Велосипед", ["", *sorted(BIKES)],
        format_func=lambda k: BIKES[k].title if k else "— не выбран —",
    )
    bike = BIKES[bike_key] if bike_key else None
    if bike:
        with st.expander("Геометрия рамы"):
            st.table({
                "Stack / Reach": f"{bike.stack_mm:g} / {bike.reach_mm:g} мм",
                "Подседельная (эфф.)": f"{bike.seat_angle_deg:g}° ({bike.eff_seat_angle_deg:g}°)",
                "Рулевая": f"{bike.head_angle_deg:g}°",
                "Верхняя труба": f"{bike.top_tube_mm:g} мм",
                "Рулевой стакан": f"{bike.head_tube_mm:g} мм",
                "База / перья": f"{bike.wheelbase_mm:g} / {bike.chainstay_mm:g} мм",
                "Занижение каретки": f"{bike.bb_drop_mm:g} мм",
                "Вилка: вынос / трейл": f"{bike.fork_offset_mm:g} / "
                                        + (f"{bike.trail_mm:g} мм" if bike.trail_mm else "—"),
                "Покрышка макс.": f"{bike.max_tyre_mm:g} мм",
                "Комплектация": ", ".join(filter(None, [
                    f"шатун {bike.crank_mm:g}" if bike.crank_mm else None,
                    f"вынос {bike.stem_mm:g}" if bike.stem_mm else None,
                    f"покрышка {bike.tyre_mm:g}" if bike.tyre_mm else None,
                ])) or "—",
                "Рост райдера": f"{bike.rider_height_cm[0]}–{bike.rider_height_cm[1]} см",
            })
            st.caption(f"Источник: {bike.source}")
    st.caption(
        "Съёмка: камера строго сбоку на высоте каретки, 2–3 м от велосипеда, "
        "велосипед на станке, райдер в облегающей одежде, руки на хватах."
    )
    st.divider()
    st.subheader("Райдер")
    st.caption("Все размеры в см. Пустое поле — не учитывать.")
    r_height = st.number_input("Рост", 120.0, 220.0, value=None, step=0.5)
    r_inseam = st.number_input(
        "Внутренняя длина ноги (inseam)", 55.0, 110.0, value=None, step=0.5,
        help="От пола до промежности, стоя босиком, книга плотно в промежность.",
    )
    r_arm = st.number_input(
        "Длина руки", 50.0, 100.0, value=None, step=0.5,
        help="От акромиона (косточка на плече) до кончика среднего пальца.",
    )
    r_shoulders = st.number_input(
        "Ширина плеч", 30.0, 60.0, value=None, step=0.5,
        help="Между акромионами — костными выступами плеч, не по одежде.",
    )
    rider = Rider(r_height, r_inseam, r_arm, r_shoulders)
    st.divider()
    st.subheader("Калибровка масштаба")
    st.caption("Без неё будут только направления регулировок, без миллиметров.")
    calib_by = st.radio("Эталон на фото", ["Шатун", "База велосипеда"],
                        horizontal=True, disabled=bike is None)
    if calib_by == "База велосипеда" and bike is not None:
        ref_mm = bike.wheelbase_mm
        calib_hint = (f"Кликните ось заднего и ось переднего колеса — база "
                      f"{bike.title.split(' — ')[0]} = {ref_mm:g} мм.")
        st.caption(f"База: {ref_mm:g} мм.")
        px_manual = st.number_input("…или база на фото, пикселей (вручную)",
                                    0.0, 10000.0, 0.0, 1.0)
    else:
        default_crank = float(bike.crank_mm) if bike and bike.crank_mm else 172.5
        ref_mm = st.number_input("Длина шатуна, мм", 150.0, 185.0, default_crank, 2.5)
        calib_hint = f"Кликните ось каретки и ось педали — шатун {ref_mm:g} мм."
        px_manual = st.number_input("…или шатун на фото, пикселей (вручную)",
                                    0.0, 5000.0, 0.0, 1.0)


# Ключ кэша st.cache_data строится по исходнику этой функции, а не её зависимостей:
# при правках в guide.py / pdf_report.py поднимайте версию, иначе отдастся старый PDF.
GUIDE_PDF_VERSION = 2


@st.cache_data(show_spinner=False)
def _guide_pdf(profile_key: str, version: int = GUIDE_PDF_VERSION) -> bytes:
    return build_guide_pdf(PROFILES[profile_key])


tab_run, tab_shoot, tab_metrics = st.tabs(["Анализ", "Как снимать", "Что измеряется"])

with tab_shoot:
    st.download_button(
        "Скачать инструкцию PDF", data=_guide_pdf(profile),
        file_name="bikefit_instruction.pdf", mime="application/pdf",
    )
    render_shooting_guide()

with tab_metrics:
    render_metrics_guide(PROFILES[profile])

with tab_run:
    col_in, col_out = st.columns([1, 1])

    with col_in:
        if mode == "Фото":
            bdc = st.file_uploader("Шатун внизу (нижняя мёртвая точка)",
                                   type=["jpg", "jpeg", "png"], key="up_bdc")
            tdc = st.file_uploader("Шатун вверху (опционально)",
                                   type=["jpg", "jpeg", "png"])
            hcr = st.file_uploader("Шатун горизонтально — для KOPS (опционально)",
                                   type=["jpg", "jpeg", "png"])
            run = st.button("Проанализировать", type="primary", disabled=bdc is None)
            uploads = ("photos", bdc, tdc, hcr)
        else:
            vid = st.file_uploader("Видео сбоку, 10–15 секунд педалирования",
                                   type=["mp4", "mov", "avi"], key="up_vid")
            run = st.button("Проанализировать", type="primary", disabled=vid is None)
            uploads = ("video", vid, None, None)

    # калибровка — на всю ширину страницы: в половинной колонке картинка слишком
    # мелкая, чтобы точно попасть в ось колеса или педали
    px_click = None
    calib_img = first_image(uploads[1], uploads[0] == "video")
    if calib_img is not None:
        px_click = click_calibration(calib_img, f"{uploads[0]}_{uploads[1].name}", calib_hint)
    px = px_click or px_manual
    scale = Scale(mm_per_px=ref_mm / px) if px > 0 else None

    if run:
        source = (uploads[0], *map(save_tmp, uploads[1:]))
        with st.spinner("Считаю углы…"):
            if source[0] == "photos":
                report = analyze_photos(source[1], source[2], source[3], profile, scale,
                                        bike, rider)
            else:
                report = analyze_video(source[1], profile, scale, step=2, bike=bike,
                                       rider=rider)
        # результат живёт в сессии: нажатие «Скачать PDF» перезапускает скрипт,
        # и без этого отчёт исчез бы с экрана
        st.session_state["report"] = report
        st.session_state["pdf"] = build_pdf(report)

    report = st.session_state.get("report")
    if report is not None:
        with col_out:
            for name, frame in report.frames.items():
                img = annotate(frame, report, name)
                st.image(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), caption=name,
                         use_column_width=True)

        st.subheader("Измерения")
        st.dataframe(
            [
                {
                    "Метрика": m.title,
                    "Значение": f"{m.value:.1f}{m.unit}",
                    "Норма": f"{m.ref.lo:g}–{m.ref.hi:g}",
                    "Статус": "в норме" if m.ok else f"{m.deviation:+.0f}",
                }
                for m in report.metrics
            ],
            use_container_width=True, hide_index=True,
        )

        st.subheader("Рекомендации")
        for i, r in enumerate(report.recommendations, 1):
            amount = f" ~{abs(r.amount_mm):.0f} мм" if r.amount_mm else ""
            with st.expander(f"{i}. {r.part}: {r.action}{amount}", expanded=i <= 2):
                st.write(r.reason)

        for n in report.notes:
            st.info(n)

        for w in report.warnings:
            st.warning(w)

        st.info(
            "Меняйте по одному параметру за раз, седло — шагом не более 5 мм. "
            "Отчёт не заменяет очный фиттинг; при боли обратитесь к специалисту."
        )
        st.download_button(
            "Скачать отчёт PDF", data=st.session_state["pdf"],
            file_name=f"bikefit_{report.profile.name}.pdf", mime="application/pdf",
            type="primary",
        )
