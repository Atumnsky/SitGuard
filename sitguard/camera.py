"""摄像头采集 + 人脸检测 + 姿态检测线程。

- 人脸：YuNet（models/face_detection_yunet_2023mar.onnx），约 5–8ms/帧
- 姿态：MediaPipe PoseLandmarker（models/pose_landmarker_lite.task），约 25–45ms/帧
人脸每 ~0.2s 一次，姿态每 ~0.35s 一次；画面采集 ~15fps。
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .posture import (Landmark, Posture, PostureAnalyzer, PostureProfile,
                      extract_profile)

log = logging.getLogger("sitguard.camera")

FACE_MODEL = "face_detection_yunet_2023mar.onnx"
POSE_MODELS = ("pose_landmarker_lite.task", "pose_landmarker_full.task")


def model_path(name: str) -> Path:
    here = Path(__file__).resolve().parent.parent
    for candidate in (here / "models" / name, Path.cwd() / "models" / name):
        if candidate.exists():
            return candidate
    return here / "models" / name


@dataclass
class CameraStatus:
    state: str = "init"      # init / ok / error / off
    message: str = ""
    fps: float = 0.0
    detections: int = 0
    posture: str = "unknown"
    posture_reason: str = ""
    pose_ok: bool = False

    def copy(self) -> "CameraStatus":
        return CameraStatus(self.state, self.message, self.fps, self.detections,
                            self.posture, self.posture_reason, self.pose_ok)


@dataclass
class CameraSnapshot:
    frame: np.ndarray | None = None
    faces: list = field(default_factory=list)
    seen: bool = False
    posture: Posture = "unknown"
    posture_reason: str = ""
    standing_seconds: float = 0.0
    profile: PostureProfile = field(default_factory=PostureProfile)
    pose: list[Landmark] | None = None
    stamp: float = 0.0
    status: CameraStatus = field(default_factory=CameraStatus)


class FaceDetector:
    """YuNet 封装：输入 BGR 帧，输出 [(x, y, w, h, score)]（原图坐标）。"""

    def __init__(self, score_threshold: float = 0.6, input_width: int = 480):
        self.score_threshold = score_threshold
        self.input_width = input_width
        self._lock = threading.Lock()
        self._size = None
        self._model = None
        path = model_path(FACE_MODEL)
        if not path.exists():
            raise FileNotFoundError(f"缺少人脸模型文件：{path}")
        self._path = str(path)

    def _ensure(self, w: int, h: int):
        if self._model is not None and self._size == (w, h):
            return self._model
        model = cv2.FaceDetectorYN.create(
            self._path, "", (w, h), self.score_threshold, 0.3, 5000
        )
        model.setInputSize((w, h))
        self._model = model
        self._size = (w, h)
        try:
            model.detect(np.zeros((h, w, 3), dtype=np.uint8))
        except cv2.error:
            pass
        return model

    def detect(self, frame: np.ndarray) -> list[tuple[float, float, float, float, float]]:
        if frame is None or frame.size == 0:
            return []
        h, w = frame.shape[:2]
        scale = min(1.0, self.input_width / float(w))
        small = (cv2.resize(frame, (max(64, int(w * scale)), max(36, int(h * scale))),
                            interpolation=cv2.INTER_AREA) if scale < 0.999 else frame)
        sh, sw = small.shape[:2]
        with self._lock:
            model = self._ensure(sw, sh)
            try:
                _n, faces = model.detect(small)
            except cv2.error:
                return []
        if faces is None:
            return []
        inv = 1.0 / scale
        return [(float(f[0]) * inv, float(f[1]) * inv, float(f[2]) * inv,
                 float(f[3]) * inv, float(f[14]) if len(f) > 14 else 1.0)
                for f in faces]


class PoseDetector:
    """MediaPipe PoseLandmarker 封装（VIDEO 模式，33 个关键点）。"""

    def __init__(self, model_name: str = POSE_MODELS[0], input_width: int = 480):
        self.input_width = input_width
        self._ts = -1
        self._lock = threading.Lock()
        path = model_path(model_name)
        if not path.exists():
            raise FileNotFoundError(f"缺少姿态模型：{path}")
        import mediapipe as mp  # 延迟导入，缺失时不影响人脸检测
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python import vision

        self._mp = mp
        options = vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(path)),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.35,
            min_pose_presence_confidence=0.35,
            min_tracking_confidence=0.35,
        )
        self._landmarker = vision.PoseLandmarker.create_from_options(options)

    def detect(self, frame: np.ndarray, now: float) -> list[Landmark] | None:
        if frame is None or frame.size == 0:
            return None
        h, w = frame.shape[:2]
        scale = min(1.0, self.input_width / float(w))
        small = (cv2.resize(frame, (max(64, int(w * scale)), max(36, int(h * scale))),
                            interpolation=cv2.INTER_AREA) if scale < 0.999 else frame)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        mp_img = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        ts = int(max(now * 1000, self._ts + 1))
        self._ts = ts
        with self._lock:
            try:
                res = self._landmarker.detect_for_video(mp_img, ts)
            except Exception:  # noqa: BLE001
                log.debug("姿态检测失败", exc_info=True)
                return None
        if not res.pose_landmarks:
            return None
        lms = res.pose_landmarks[0]
        return [Landmark(float(p.x), float(p.y), float(getattr(p, "visibility", 0.0) or 0.0))
                for p in lms]


class CameraWorker:
    """后台线程：采集画面、人脸 + 姿态检测、维护最新快照。"""

    def __init__(self, config, on_presence=None, on_posture=None,
                 face_interval: float = 0.22, pose_interval: float = 0.36):
        self.config = config
        self.on_presence = on_presence
        self.on_posture = on_posture
        self.face_interval = face_interval
        self.pose_interval = pose_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._snapshot = CameraSnapshot()
        self._detector: FaceDetector | None = None
        self._pose: PoseDetector | None = None
        self._cap = None
        self.posture = PostureAnalyzer()
        self._last_posture: Posture = "unknown"
        self._pose_error = ""
        self._apply_calibration()

    def _apply_calibration(self) -> None:
        raw = getattr(self.config, "calibration", None) or {}
        sitting = PostureProfile.from_dict(raw.get("sitting")) if isinstance(raw, dict) else None
        standing = PostureProfile.from_dict(raw.get("standing")) if isinstance(raw, dict) else None
        if sitting or standing:
            self.posture.set_calibration(sitting, standing)

    # ---------- 生命周期 ----------
    def start(self) -> None:
        self._stop.clear()
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="camera", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)
            if self._thread.is_alive():
                # 读帧卡死时释放设备，强制唤醒采集线程
                try:
                    if self._cap is not None:
                        self._cap.release()
                except Exception:  # noqa: BLE001
                    pass
                self._thread.join(timeout=1.5)
            self._thread = None
        self._cap = None
        self._set_status("off", "摄像头已关闭")

    def restart(self) -> None:
        self.stop()
        self._set_status("init", "正在启动摄像头…")
        self.start()

    # ---------- 查询 ----------
    def snapshot(self) -> CameraSnapshot:
        with self._lock:
            snap = self._snapshot
            return CameraSnapshot(snap.frame, list(snap.faces), snap.seen,
                                  snap.posture, snap.posture_reason,
                                  snap.standing_seconds, snap.profile, snap.pose,
                                  snap.stamp, snap.status.copy())

    @property
    def status(self) -> CameraStatus:
        with self._lock:
            return self._snapshot.status.copy()

    # ---------- 内部 ----------
    def _set_status(self, state: str, message: str) -> None:
        with self._lock:
            self._snapshot.status.state = state
            self._snapshot.status.message = message

    def _open(self):
        """依次尝试 DirectShow / MSMF，返回 VideoCapture 或 None。"""
        index = int(self.config.camera_index)
        for backend, name in ((cv2.CAP_DSHOW, "DirectShow"), (cv2.CAP_MSMF, "MSMF")):
            try:
                cap = cv2.VideoCapture(index, backend)
            except cv2.error:
                cap = None
            if cap is not None and cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
                cap.set(cv2.CAP_PROP_FPS, 30)
                ok, frame = cap.read()
                if ok and frame is not None and frame.size > 0:
                    log.info("摄像头已打开（%s, index=%d）", name, index)
                    return cap, frame
                cap.release()
            elif cap is not None:
                cap.release()
        return None, None

    def _run(self) -> None:
        if not self.config.camera_enabled:
            self._set_status("off", "摄像头已关闭")
            return
        try:
            self._detector = FaceDetector(score_threshold=self.config.sensitivity)
        except Exception as exc:  # noqa: BLE001
            log.exception("人脸模型加载失败")
            self._set_status("error", f"人脸模型加载失败：{exc}")
            return
        if getattr(self.config, "posture_enabled", True):
            try:
                self._pose = PoseDetector(getattr(self.config, "pose_model", POSE_MODELS[0]))
                log.info("姿态模型已加载")
            except Exception as exc:  # noqa: BLE001
                self._pose = None
                self._pose_error = str(exc)[:120]
                log.warning("姿态模型不可用，仅使用人脸位置判断：%s", exc)
        self._set_status("init", "正在打开摄像头…")
        fail_count = 0
        while not self._stop.is_set():
            cap, frame = self._open()
            if cap is None:
                fail_count += 1
                message = (
                    "无法打开摄像头。\n请检查：摄像头是否被其他程序占用、"
                    "Windows 设置 → 隐私和安全性 → 相机 是否允许桌面应用访问。"
                )
                self._set_status("error", message)
                if fail_count == 1:
                    log.warning("摄像头打开失败（index=%s）", self.config.camera_index)
                self._stop.wait(min(15.0, 2.0 * fail_count + 2.0))
                continue
            fail_count = 0
            try:
                self._capture_loop(cap, frame)
            except Exception:  # noqa: BLE001
                log.exception("摄像头采集线程异常，2 秒后自动重连")
                self._set_status("error", "摄像头异常，正在自动重连…")
                try:
                    cap.release()
                except Exception:  # noqa: BLE001
                    pass
                self._stop.wait(2.0)

    def _capture_loop(self, cap, first_frame) -> None:
        fps_t0 = time.monotonic()
        frames = 0
        fps = 0.0
        last_face = 0.0
        last_pose = 0.0
        faces: list = []
        seen = False
        face_center: tuple[float, float] | None = None
        pose_lms: list[Landmark] | None = None
        frame = first_frame
        posture: Posture = "unknown"
        detector_born = time.monotonic()
        try:
            self._cap = cap
            while not self._stop.is_set():
                now = time.monotonic()
                if now - detector_born > 3600 and self._stop.is_set() is False:
                    try:
                        self._detector = FaceDetector(score_threshold=self.config.sensitivity)
                        if getattr(self.config, "posture_enabled", True):
                            self._pose = PoseDetector(
                                getattr(self.config, "pose_model", POSE_MODELS[0]))
                        detector_born = now
                        log.info("已重建人脸/姿态检测器（长时间运行维护）")
                    except Exception:  # noqa: BLE001
                        detector_born = now
                        log.exception("重建检测器失败，继续使用旧实例")
                if frame is None:
                    ok, frame = cap.read()
                    if not ok or frame is None or frame.size == 0:
                        self._set_status("error", "摄像头信号中断，正在重连…")
                        break
                if frame.shape[1] > 640:
                    frame = cv2.resize(
                        frame, (640, int(frame.shape[0] * 640 / frame.shape[1])),
                        interpolation=cv2.INTER_AREA)
                frames += 1
                if now - fps_t0 >= 1.0:
                    fps = frames / (now - fps_t0)
                    frames = 0
                    fps_t0 = now

                if now - last_face >= self.face_interval:
                    last_face = now
                    try:
                        faces = self._detector.detect(frame) if self._detector else []
                    except Exception:  # noqa: BLE001
                        log.exception("人脸检测异常")
                        faces = []
                    seen = len(faces) > 0
                    face_center = None
                    if faces:
                        best = max(faces, key=lambda f: f[2] * f[3])
                        h, w = frame.shape[:2]
                        face_center = ((best[0] + best[2] / 2) / w, (best[1] + best[3] / 2) / h)
                    if self.on_presence:
                        try:
                            self.on_presence(seen, now)
                        except Exception:  # noqa: BLE001
                            log.exception("presence 回调异常")

                if now - last_pose >= self.pose_interval:
                    last_pose = now
                    if self._pose:
                        try:
                            pose_lms = self._pose.detect(frame, now)
                        except Exception:  # noqa: BLE001
                            pose_lms = None
                    person = seen or pose_lms is not None
                    h, w = frame.shape[:2]
                    profile = extract_profile(faces, pose_lms, w, h)
                    try:
                        posture = self.posture.update(
                            now, pose=pose_lms, profile=profile,
                            face_present=seen, person_present=person)
                    except Exception:  # noqa: BLE001
                        log.exception("姿态分析异常")
                    if self.on_posture and posture != self._last_posture:
                        self._last_posture = posture
                        try:
                            self.on_posture(posture, now)
                        except Exception:  # noqa: BLE001
                            log.exception("posture 回调异常")

                with self._lock:
                    snap = self._snapshot
                    snap.frame = frame
                    snap.faces = faces
                    snap.seen = seen
                    snap.posture = posture
                    snap.posture_reason = self.posture.reason
                    snap.standing_seconds = self.posture.standing_seconds(now)
                    snap.profile = profile
                    snap.pose = pose_lms
                    snap.stamp = now
                    snap.status.state = "ok"
                    snap.status.message = ""
                    snap.status.fps = fps
                    snap.status.detections = len(faces)
                    snap.status.posture = posture
                    snap.status.posture_reason = self.posture.reason
                    snap.status.pose_ok = self._pose is not None
                frame = None
                self._stop.wait(0.01)
        finally:
            self._cap = None
            try:
                cap.release()
            except Exception:  # noqa: BLE001
                pass


class SimulatedCamera:
    """无摄像头时使用：模拟“在座/离开/站立”，并生成示意画面。"""

    def __init__(self, config, on_presence=None, on_posture=None):
        self.config = config
        self.on_presence = on_presence
        self.on_posture = on_posture
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._frame = None
        self._status = CameraStatus("ok", "演示模式：模拟摄像头", posture="sitting", pose_ok=True)
        self._present = True
        self._posture: Posture = "sitting"
        self._last_posture: Posture = "unknown"

    def start(self) -> None:
        self._stop.clear()
        self._frame = self._render()
        self._thread = threading.Thread(target=self._run, name="sim-camera", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        with self._lock:
            self._status = CameraStatus("off", "摄像头已关闭")

    def restart(self) -> None:
        self.stop()
        self.start()

    def snapshot(self) -> CameraSnapshot:
        with self._lock:
            return CameraSnapshot(
                frame=self._frame, faces=[], seen=self._present,
                posture=self._posture, posture_reason="演示模式",
                stamp=time.monotonic(), status=self._status.copy(),
            )

    @property
    def status(self) -> CameraStatus:
        with self._lock:
            return self._status.copy()

    def set_present(self, present: bool) -> None:
        with self._lock:
            self._present = present
            self._frame = self._render()

    def set_posture(self, posture: Posture) -> None:
        with self._lock:
            self._posture = posture
            self._frame = self._render()

    def _run(self) -> None:
        while not self._stop.is_set():
            if self.on_presence:
                try:
                    self.on_presence(self._present, time.monotonic())
                except Exception:  # noqa: BLE001
                    pass
            if self.on_posture and self._posture != self._last_posture:
                self._last_posture = self._posture
                try:
                    self.on_posture(self._posture, time.monotonic())
                except Exception:  # noqa: BLE001
                    pass
            self._stop.wait(0.25)

    def _render(self):
        img = np.full((360, 640, 3), 26, dtype=np.uint8)
        cv2.rectangle(img, (0, 0), (639, 359), (40, 44, 52), 2)
        color = (120, 220, 160) if self._present else (90, 110, 130)
        cv2.circle(img, (320, 170), 70, color, -1)
        cv2.ellipse(img, (320, 330), (120, 70), 0, 180, 360, color, -1)
        label = "DEMO / " + ("STANDING" if self._posture == "standing" else "SITTING")
        cv2.putText(img, label, (24, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (90, 200, 160), 2,
                    cv2.LINE_AA)
        return img
