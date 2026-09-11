"""Streamlit-хелперы калибровки масштаба по кликам. Вынесены из app.py,
чтобы их можно было запускать в отдельном тестовом приложении."""

from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import numpy as np
import streamlit as st
from streamlit_image_coordinates import streamlit_image_coordinates


def save_tmp(upload) -> str | None:
    if upload is None:
        return None
    suffix = Path(upload.name).suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(upload.getbuffer())
    tmp.close()
    return tmp.name


def first_image(upload, is_video: bool) -> np.ndarray | None:
    """BGR-кадр для калибровки: само фото или первый кадр видео."""
    if upload is None:
        return None
    if not is_video:
        return cv2.imdecode(np.frombuffer(upload.getbuffer(), np.uint8), cv2.IMREAD_COLOR)
    path = save_tmp(upload)
    cap = cv2.VideoCapture(path)
    ok, frame = cap.read()
    cap.release()
    return frame if ok else None


def click_calibration(img: np.ndarray, key: str, hint: str) -> float | None:
    """Два клика по фото -> расстояние между ними в пикселях исходного кадра.

    Компонент отдаёт координаты в пикселях отображённой (сжатой) картинки,
    поэтому пересчитываем через отношение исходной ширины к показанной.
    """
    pts: list[tuple[float, float]] = st.session_state.setdefault(f"calib_{key}", [])
    h, w = img.shape[:2]
    st.markdown(f"**Калибровка кликами.** {hint}")
    if st.button("Сбросить точки", key=f"reset_{key}"):
        pts.clear()
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).copy()
    r = max(4, w // 150)
    for x, y in pts:
        cv2.circle(rgb, (int(x), int(y)), r, (255, 60, 60), -1, cv2.LINE_AA)
    if len(pts) == 2:
        (x1, y1), (x2, y2) = pts
        cv2.line(rgb, (int(x1), int(y1)), (int(x2), int(y2)), (255, 60, 60),
                 max(2, r // 2), cv2.LINE_AA)
    click = streamlit_image_coordinates(rgb, key=f"img_{key}", width="stretch",
                                        cursor="crosshair", image_format="JPEG")
    if click and len(pts) < 2 and click.get("width"):
        # один клик = один момент времени: дедупликация по unix_time, а не по
        # координатам — повторный клик в ту же точку тоже считается
        stamp = click.get("unix_time") or (click["x"], click["y"])
        if st.session_state.get(f"last_{key}") != stamp:
            st.session_state[f"last_{key}"] = stamp
            k = w / click["width"]
            pts.append((click["x"] * k, click["y"] * k))
            st.rerun()
    shown = ", ".join(f"({x:.0f}, {y:.0f})" for x, y in pts)
    if len(pts) < 2:
        st.caption(f"Отмечено точек: {len(pts)} из 2" + (f" — {shown}" if pts else ""))
        return None
    (x1, y1), (x2, y2) = pts
    dist = float(np.hypot(x2 - x1, y2 - y1))
    st.caption(f"Точки {shown}; расстояние между ними: {dist:.0f} px")
    return dist
