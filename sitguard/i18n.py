"""中英文界面文案。

用法：
    from .i18n import fmt_duration, t, set_language
    t("pause")                      # 静态文案
    t("standing_seconds", n=12)     # 带占位符
"""

from __future__ import annotations

LANGUAGES = [("zh", "中文"), ("en", "English")]
_lang = "zh"


def set_language(lang: str) -> str:
    global _lang
    _lang = "en" if str(lang).lower().startswith("en") else "zh"
    return _lang


def get_language() -> str:
    return _lang


_T = {
    # 通用
    "app_title": ("SitGuard · 久坐提醒", "SitGuard · Sitting Reminder"),
    "brand_sub": ("久坐提醒", "Sitting reminder"),
    "settings": ("设置", "Settings"),
    "save": ("保存", "Save"),
    "cancel": ("取消", "Cancel"),
    "minutes": ("分钟", "min"),
    "seconds": ("秒", "s"),
    "times": ("{n} 次", "{n}"),
    "camera_off_btn": ("关摄像头", "Camera off"),
    "camera_on_btn": ("开摄像头", "Camera on"),

    # 主界面
    "init": ("初始化…", "Starting…"),
    "recognizing": ("正在识别…", "Detecting…"),
    "pause": ("暂停监控", "Pause"),
    "resume": ("继续监控", "Resume"),
    "test_reminder": ("测试提醒", "Test reminder"),
    "to_tray": ("收进托盘", "To tray"),
    "stat_sit": ("今日在座", "Sitting today"),
    "stat_breaks": ("完成休息", "Breaks"),
    "stat_reminders": ("提醒次数", "Reminders"),
    "footer": ("SitGuard v1.3.1 · 画面仅在本机处理",
               "SitGuard v1.3.1 · Processed locally only"),
    "stand_mode": ("站立模式", "Stand mode"),
    "sit_down": ("坐下", "Sit down"),
    "stand": ("站立", "Stand"),
    "paused_heading": ("监控已暂停", "Monitoring paused"),
    "paused_sub": ("不会计时，也不会提醒。点“继续监控”恢复。",
                   "No timing or reminders. Click Resume to continue."),
    "paused_ring": ("暂停", "Paused"),
    "break_heading": ("正在休息中", "On a break"),
    "break_sub": ("站起来 10 秒，或离开画面 12 秒，即可完成休息。",
                  "Stand 10s, or leave the frame 12s, to finish."),
    "break_countdown": ("休息倒计时", "Break countdown"),
    "get_up": ("起来活动一下", "Stand up and move"),
    "standing_heading": ("站立中，不计久坐", "Standing — timer paused"),
    "standing_sub": ("已站 {n} 秒，坐下后继续累计。",
                     "Standing for {n}s. Timer resumes when you sit."),
    "standing_sub_reset": ("已站 {n} 秒，再站 {m} 秒久坐从头计时。",
                            "Standing {n}s — {m}s more restarts sitting."),
    "sit_elapsed": ("已坐时长", "Sitting time"),
    "standing_seconds": ("已站 {n} 秒", "Standing {n}s"),
    "due_heading": ("该起来活动了", "Time to move"),
    "due_sub": ("已经连续久坐超过目标时长。",
                "You have been sitting longer than your limit."),
    "near_heading": ("就快到一个周期了", "Almost due"),
    "near_sub": ("再坚持一小会儿，到点会提醒你起身。",
                 "A little longer — you will be reminded."),
    "focus_heading": ("正在陪伴你专注", "Focusing with you"),
    "focus_sub": ("检测到你坐在屏幕前，正在累计久坐时间。",
                  "You are at the screen; sitting time is counting."),
    "away_heading": ("暂时离开屏幕", "Away from screen"),
    "away_sub": ("计时已暂停，回来坐下后继续累计。",
                 "Timer paused; it resumes when you return."),
    "until_reminder": ("距离提醒", "Until reminder"),
    "sat_for": ("已坐 {t}", "Sitting {t}"),
    "present_standing": ("● 站立中 {n} 秒", "● Standing {n}s"),
    "present_sitting": ("● 在座（坐姿）", "● Seated"),
    "present_unknown": ("● 在座（识别姿态中）", "● Present (detecting pose)"),
    "away_minutes": ("● 离开 {m} 分钟", "● Away {m} min"),
    "no_person": ("● 没检测到人", "● No person"),
    "pose_ok": ("姿态检测正常", "Pose detection active"),
    "pose_face_only": ("仅人脸检测（姿态不可用）", "Face only (pose unavailable)"),
    "pose_cal_hint": ("姿态检测正常 · 建议做姿势校准",
                      "Pose active · Calibration recommended"),
    "cam_error": ("● 摄像头不可用", "● Camera unavailable"),
    "cam_error_hint": ("请检查摄像头连接或权限",
                       "Check camera connection or permission"),
    "cam_off": ("● 摄像头已关闭", "● Camera off"),
    "camera_off_msg": ("摄像头已关闭", "Camera off"),
    "cam_starting": ("正在启动摄像头…", "Starting camera…"),
    "preview": ("摄像头预览", "Camera preview"),
    "preview_wait": ("等待摄像头…", "Waiting for camera…"),
    "preview_off": ("摄像头未就绪", "Camera not ready"),
    "badge_present": ("● 在座", "● Present"),
    "badge_standing": ("● 站立", "● Standing"),
    "badge_sitting": ("● 坐姿", "● Seated"),
    "badge_away": ("● 离开", "● Away"),
    "badge_off": ("● 关闭", "● Off"),

    # 休息弹窗
    "overlay_brand": ("SITGUARD · 久坐提醒", "SITGUARD · SITTING REMINDER"),
    "overlay_title": ("该站起来活动一下了", "Time to stand up and move"),
    "overlay_idle": ("站起来走一走，让眼睛离开屏幕 5 分钟。",
                     "Stand up, walk a little, and look away from the screen."),
    "btn_stood": ("我站起来了", "I stood up"),
    "btn_snooze": ("稍后提醒（5 分钟）", "Snooze (5 min)"),
    "btn_close_break": ("关闭本次提醒", "Close this reminder"),
    "cam_pose": ("摄像头 · 姿态检测", "Camera · Pose"),
    "overlay_foot": ("站起来 10 秒，或离开画面 12 秒\n都会自动完成休息",
                     "Stand 10s, or leave the frame 12s\nto finish automatically"),
    "overlay_reason": ("你已连续坐了 {d}，该活动一下了。",
                       "You have been sitting for {d}. Time to move."),
    "standing_almost": ("已检测到站立，正在结束本次提醒…",
                        "Standing detected — closing…"),
    "standing_need": ("检测到站立 {s} 秒，再站 {n} 秒即可完成。",
                      "Standing {s}s — {n}s more."),
    "gone_left": ("看不到你了，继续站/离开 {n} 秒即可完成休息。",
                  "Cannot see you — {n}s more to finish."),
    "pose_off_tip": ("姿态检测不可用：点“我站起来了”或“关闭本次提醒”即可结束。",
                     "Pose unavailable: click “I stood up” or “Close this reminder”."),
    "overlay_tip": ("站起来 10 秒，或离开画面 12 秒，休息会自动完成；也可以直接点按钮。",
                    "Stand 10s or leave the frame 12s to finish; buttons also work."),
    "overlay_mon_standing": ("● 检测到站立，保持一下", "● Standing — hold on"),
    "overlay_mon_gone": ("● 已离开画面，按起身处理", "● Out of frame — counted as standing"),
    "overlay_mon_sitting": ("● 还坐着，站起来吧", "● Still seated — stand up"),
    "overlay_mon_away": ("● 已离开座位", "● Away"),

    # 设置
    "settings_title": ("SitGuard 设置", "SitGuard Settings"),
    "settings_heading": ("设置", "Settings"),
    "settings_sub": ("修改后立即生效并保存", "Changes apply immediately and are saved"),
    "row_sit": ("久坐提醒间隔", "Remind after"),
    "row_break": ("休息时长", "Break duration"),
    "row_away": ("离开多久算休息", "Reset sitting after away"),
    "row_stand_break": ("站立多久完成休息", "Finish break after standing"),
    "row_break_absent": ("离开画面多久完成休息", "Finish break when out of frame"),
    "row_stand_reset": ("站立多久重新计时", "Restart sitting after standing"),
    "row_cam": ("摄像头编号", "Camera index"),
    "row_sens": ("人脸检测灵敏度", "Face detection sensitivity"),
    "row_lang": ("界面语言", "Language"),
    "hint_sit": ("连续坐姿达到该时长后弹窗提醒",
                 "Popup after this much continuous sitting"),
    "hint_break": ("提醒弹窗里的倒计时长度", "Countdown length in the popup"),
    "hint_away": ("离开超过该时长，久坐计时清零",
                  "Sitting time resets after this absence"),
    "hint_stand_break": ("弹窗期间站立达到该时长即自动完成",
                         "Break completes after standing this long"),
    "hint_break_absent": ("站起来后整个人离开镜头，也会按起身完成",
                          "Leaving the frame also counts as standing up"),
    "hint_stand_reset": ("站立超过该时长，久坐计时从 0 重新开始",
                         "Sitting timer restarts from 0 after standing this long"),
    "hint_cam": ("外接摄像头可改 1 试试", "Try 1 for an external camera"),
    "hint_sens": ("数值越小越灵敏；误判时可调高",
                  "Lower = more sensitive; raise it if false positives"),
    "chk_pose": ("启用姿态检测（区分坐/站）", "Enable pose detection (sit/stand)"),
    "chk_sound": ("启用提示音", "Enable sound"),
    "chk_autostart": ("开机自动启动", "Start with Windows"),
    "chk_preview": ("显示摄像头预览", "Show camera preview"),
    "chk_tray": ("关闭窗口时最小化到托盘", "Minimize to tray on close"),
    "chk_top": ("窗口置顶", "Always on top"),
    "cal_btn": ("姿势校准…", "Calibrate posture…"),
    "cal_hint": ("记录你的坐姿与站姿，识别更准",
                 "Record sitting & standing poses"),
    "settings_saved": ("设置已保存", "Settings saved"),
    "invalid_number": ("请输入有效数字", "Please enter a valid number"),
    "language_changed": ("界面语言已切换", "Language changed"),

    # 校准
    "cal_title": ("SitGuard 姿势校准", "SitGuard Posture Calibration"),
    "cal_heading": ("姿势校准", "Posture calibration"),
    "cal_desc": ("分别记录你“坐着”和“站着”时的画面特征，之后按你的实际姿势判断。\n"
                 "站姿可以整个人离开画面——这也会被记录为“站姿”。",
                 "Record how you look sitting and standing, and the app will judge "
                 "by your own poses.\nYour standing pose may be completely out of "
                 "frame — that will be recorded too."),
    "cal_sit_btn": ("记录坐姿", "Record sitting"),
    "cal_stand_btn": ("记录站姿", "Record standing"),
    "cal_sit_none": ("坐姿：未记录", "Sitting: not recorded"),
    "cal_stand_none": ("站姿：未记录", "Standing: not recorded"),
    "cal_sit_done": ("坐姿：{d}", "Sitting: {d}"),
    "cal_stand_done": ("站姿：{d}", "Standing: {d}"),
    "cal_desc_visible": ("已记录（脸高 {f}%，肩高 {s}%）",
                         "Recorded (face {f}%, shoulder {s}%)"),
    "cal_desc_face": ("已记录（脸高 {f}%）", "Recorded (face {f}%)"),
    "cal_unrecorded": ("未记录", "not recorded"),
    "cal_desc_noface": ("已记录（看不到脸 → 按离开画面识别）",
                        "Recorded (no face → out-of-frame)"),
    "cal_sampling": ("正在采样，请保持当前姿势 2 秒…",
                     "Sampling — hold still for 2s…"),
    "cal_no_frame": ("没有拿到画面，请确认摄像头已开启。",
                     "No frame — check that the camera is on."),
    "cal_need_both": ("请先分别记录坐姿和站姿。", "Record both sitting and standing first."),
    "cal_done": ("校准完成：之后会按你实际的坐/站特征判断。",
                 "Calibration complete — using your own poses."),
    "cal_done_noface": ("校准完成：站姿看不到脸，之后离开画面会按起身处理。",
                        "Calibration complete — out of frame counts as standing."),
    "cal_save": ("保存校准", "Save calibration"),
    "cal_saved": ("姿势校准已保存", "Calibration saved"),

    # 托盘 / 提示
    "tray_open": ("打开 SitGuard", "Open SitGuard"),
    "tray_pause": ("暂停 / 恢复监控", "Pause / resume"),
    "tray_break": ("立即休息一下", "Take a break"),
    "tray_cam": ("开关摄像头", "Toggle camera"),
    "tray_exit": ("退出", "Exit"),
    "tray_tip": ("SitGuard 久坐提醒", "SitGuard — Sitting Reminder"),
    "toast_tray": ("已收进托盘，仍在后台监控", "Minimized to tray — still monitoring"),
    "toast_cam_off": ("摄像头已关闭，仅按手动模式计时",
                      "Camera off — manual mode"),
    "toast_cam_on": ("摄像头已开启", "Camera on"),
    "toast_camera_recover": ("摄像头无响应，正在自动重连…",
                             "Camera not responding — reconnecting…"),
    "toast_break_start": ("时间到，起来活动一下！", "Time to stand up and move!"),
    "toast_break_end": ("{d}，继续加油 💪", "{d} — nice work 💪"),
    "toast_away": ("检测到你离开，计时暂停", "Away detected — timer paused"),
    "toast_reset_break": ("离开足够久，久坐时间已清零",
                          "Away long enough — sitting time reset"),
    "toast_reset_standing": ("站立活动达标，久坐时间已清零",
                             "Standing counts — sitting time reset"),
    "toast_snoozed": ("好，{m}后再提醒", "Okay — reminder in {m}"),
    "toast_paused": ("已暂停监控", "Monitoring paused"),
    "toast_resumed": ("已恢复监控", "Monitoring resumed"),
    "toast_standing": ("已标记为站立，不计久坐时间",
                       "Marked as standing — sitting timer paused"),
    "toast_sitting": ("已标记为坐姿", "Marked as sitting"),
    "toast_demo_on": ("已切换演示模式", "Demo mode on"),
    "toast_demo_off": ("已切回摄像头模式", "Camera mode on"),
    "toast_cal_prompt": ("建议在设置里做一次「姿势校准」，站立识别更准",
                         "Tip: run Posture Calibration for better standing detection"),
    "toast_autostart_fail": ("开机自启设置失败（可能被安全软件拦截）",
                             "Could not enable startup (blocked by security software?)"),
    "break_end_standing": ("站立 {n} 秒", "Standing {n}s"),
    "break_end_gone": ("离开画面 {n} 秒", "Out of frame {n}s"),
    "break_end_timeout": ("倒计时结束", "Countdown finished"),
    "break_end_manual": ("手动确认", "Manual confirm"),
}


def t(key: str, **kwargs) -> str:
    pair = _T.get(key)
    if not pair:
        return key
    text = pair[1] if _lang == "en" else pair[0]
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text


def fmt_duration(seconds: float) -> str:
    """本地化的时长描述。"""
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, sec = divmod(rem, 60)
    if _lang == "en":
        if h:
            return f"{h}h {m}m"
        if m:
            return f"{m} min"
        return f"{sec} s"
    if h:
        return f"{h} 小时 {m} 分"
    if m:
        return f"{m} 分钟"
    return f"{sec} 秒"

