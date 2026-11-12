"""真实摄像头联调：采集 + YuNet 检测 + 在场防抖，输出状态与截图。"""
import json
import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sitguard.camera import CameraWorker  # noqa: E402
from sitguard.config import Config  # noqa: E402
from sitguard.engine import SessionEngine  # noqa: E402


def main() -> int:
    cfg = Config().normalized()
    engine = SessionEngine(cfg)
    seen_events = []

    def on_presence(seen: bool, when: float) -> None:
        engine.notify_presence(seen, when)
        seen_events.append(seen)

    cam = CameraWorker(cfg, on_presence=on_presence)
    cam.start()
    try:
        duration = 14.0
        t0 = time.time()
        last_log = 0.0
        snapshot_frame = None
        while time.time() - t0 < duration:
            time.sleep(0.25)
            snap = cam.snapshot()
            st = snap.status
            engine.tick()
            if time.time() - last_log >= 1.0:
                last_log = time.time()
                n_faces = len(snap.faces)
                best = max((f[4] for f in snap.faces), default=0.0)
                print(f"t={time.time()-t0:5.1f}s state={st.state:5s} fps={st.fps:4.1f} "
                      f"faces={n_faces} score={best:.2f} present={engine.present} "
                      f"sit={engine.sitting_seconds:.1f}s msg={st.message[:40]}")
            if snap.frame is not None and snapshot_frame is None and time.time() - t0 > 3:
                snapshot_frame = snap.frame.copy()
        result = {
            "camera_state": cam.snapshot().status.state,
            "frames_seen": len(seen_events),
            "positive_frames": sum(1 for s in seen_events if s),
            "present": engine.present,
            "sitting_seconds": round(engine.sitting_seconds, 2),
            "fps": round(cam.snapshot().status.fps, 1),
            "faces_last": len(cam.snapshot().faces),
        }
        (ROOT / "camera_test.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
        if snapshot_frame is not None:
            cv2.imwrite(str(ROOT / "camera_test_frame.jpg"), snapshot_frame)
        print("RESULT", json.dumps(result, ensure_ascii=False))
        return 0
    finally:
        cam.stop()


if __name__ == "__main__":
    sys.exit(main())
