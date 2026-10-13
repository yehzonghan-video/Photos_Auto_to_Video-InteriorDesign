"""同 frontend/animation.js 的時間公式；座標以最終 9:16 畫面為基準。"""


def pose(label, time):
    if time < label["start"] or time >= label["end"]:
        return None
    p = min(1., (time - label["start"]) / label["enter"]) if label["enter"] else 1.
    ease = 1 - (1 - p) ** 3
    remaining = 1 - ease
    x, y, scale, alpha = 0., 0., 1., 1.
    animation = label["animation"]
    if animation == "left": x = -.22 * remaining
    if animation == "right": x = .22 * remaining
    if animation == "up": y = -.16 * remaining
    if animation == "down": y = .16 * remaining
    if animation == "fade": alpha = ease
    if animation == "scale": scale, alpha = .65 + .35 * ease, ease
    if animation not in ("none", "fade", "scale"): alpha = ease
    # 與 Canvas 相同的文字漸隱；沒有 exit 的既有標籤維持原動畫。
    exit_duration = label.get("exit", 0)
    if exit_duration and time > label["end"] - exit_duration:
        q = min(1., (label["end"] - time) / exit_duration)
        alpha *= 1 - (1 - q) ** 3
    return dict(x=x, y=y, scale=scale, alpha=alpha)


def overlay_pose(item, time):
    end = item["start"] + item["duration"]
    entry = pose(dict(start=item["start"], end=end, enter=item["enter"], animation=item["animation"]), time)
    if entry is None:
        return None
    if item["exit"] and time > end-item["exit"]:
        leaving = pose(dict(start=0, end=item["exit"]+1, enter=item["exit"], animation=item["exit_animation"]), end-time)
        entry = dict(x=entry["x"]+leaving["x"], y=entry["y"]+leaving["y"],
                     scale=entry["scale"]*leaving["scale"], alpha=entry["alpha"]*leaving["alpha"])
    return entry
