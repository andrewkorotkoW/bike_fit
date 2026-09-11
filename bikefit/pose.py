"""Извлечение ключевых точек тела из фото/видео (MediaPipe Pose / BlazePose).

Зачем именно MediaPipe: работает на CPU в реальном времени, даёт 33 точки,
устойчив к велосипедной посадке (сильное сгибание бедра). Альтернативы —
YOLOv8-pose (точнее на плохом свете, тяжелее) и MoveNet Thunder.
Абстракция ниже позволяет подменить бэкенд, не трогая аналитику.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterator, Literal

import cv2
import numpy as np

log = logging.getLogger(__name__)

# Индексы landmark'ов MediaPipe Pose
_IDX = {
    "left": {
        "shoulder": 11, "elbow": 13, "wrist": 15,
        "hip": 23, "knee": 25, "ankle": 27, "heel": 29, "foot": 31,
    },
    "right": {
        "shoulder": 12, "elbow": 14, "wrist": 16,
        "hip": 24, "knee": 26, "ankle": 28, "heel": 30, "foot": 32,
    },
}

Side = Literal["left", "right"]
JOINTS = ("shoulder", "elbow", "wrist", "hip", "knee", "ankle", "heel", "foot")


@dataclass(frozen=True, slots=True)
class Point:
    x: float          # пиксели
    y: float          # пиксели, ось вниз
    visibility: float

    def as_array(self) -> np.ndarray:
        return np.array([self.x, self.y], dtype=float)


@dataclass(slots=True)
class PoseFrame:
    """Один кадр: точки ближней к камере стороны тела, приведённые к общим именам."""
    points: dict[str, Point]
    side: Side
    frame_index: int = 0
    image: np.ndarray | None = None

    def __getitem__(self, joint: str) -> Point:
        return self.points[joint]

    def min_visibility(self, joints: tuple[str, ...] = JOINTS) -> float:
        return min(self.points[j].visibility for j in joints)


def _ensure_ca_bundle() -> None:
    """Python с python.org на macOS часто без системных CA-сертификатов —
    докачка heavy-модели падает с CERTIFICATE_VERIFY_FAILED. Подставляем
    бандл certifi, если пользователь сам не задал SSL_CERT_FILE."""
    import os

    if os.environ.get("SSL_CERT_FILE"):
        return
    try:
        import certifi
    except ImportError:
        return
    os.environ["SSL_CERT_FILE"] = certifi.where()


class PoseEstimator:
    """Обёртка над MediaPipe. Используется как контекстный менеджер."""

    def __init__(self, static: bool = True, model_complexity: int = 2) -> None:
        import urllib.error

        _ensure_ca_bundle()
        import mediapipe as mp  # ленивый импорт: тяжёлый пакет

        self._mp = mp

        def _make(complexity: int):
            return mp.solutions.pose.Pose(
                static_image_mode=static,
                model_complexity=complexity,
                enable_segmentation=False,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )

        try:
            self._pose = _make(model_complexity)
        except urllib.error.URLError as exc:
            # heavy-модель (complexity=2) не входит в wheel и докачивается
            # с серверов Google при первом использовании. Нет сети или
            # сертификатов — работаем на full: она в пакете, офлайн.
            if model_complexity < 2:
                raise
            log.warning(
                "Не скачать heavy-модель (%s); откат на model_complexity=1 "
                "(full, встроена в пакет). Точность чуть ниже.", exc,
            )
            self._pose = _make(1)

    def __enter__(self) -> "PoseEstimator":
        return self

    def __exit__(self, *exc) -> None:
        self._pose.close()

    # ------------------------------------------------------------------
    def estimate(self, bgr: np.ndarray, frame_index: int = 0,
                 side: Side | None = None) -> PoseFrame | None:
        h, w = bgr.shape[:2]
        res = self._pose.process(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        if not res.pose_landmarks:
            log.warning("Кадр %s: человек не найден", frame_index)
            return None

        lms = res.pose_landmarks.landmark
        chosen = side or self._pick_side(lms)
        pts = {
            name: Point(lms[i].x * w, lms[i].y * h, lms[i].visibility)
            for name, i in _IDX[chosen].items()
        }
        return PoseFrame(points=pts, side=chosen, frame_index=frame_index, image=bgr)

    @staticmethod
    def _pick_side(lms) -> Side:
        """Ближняя к камере сторона = та, у которой выше суммарная visibility."""
        score = {
            s: sum(lms[i].visibility for i in idx.values())
            for s, idx in _IDX.items()
        }
        return max(score, key=score.get)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    def iter_video(self, path: str, step: int = 1) -> Iterator[PoseFrame]:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise FileNotFoundError(f"Не открыть видео: {path}")
        i, side = 0, None
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                if i % step == 0:
                    pf = self.estimate(frame, i, side)
                    if pf is not None:
                        side = side or pf.side  # фиксируем сторону на всё видео
                        yield pf
                i += 1
        finally:
            cap.release()


def load_image(path: str) -> np.ndarray:
    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(f"Не открыть изображение: {path}")
    return img