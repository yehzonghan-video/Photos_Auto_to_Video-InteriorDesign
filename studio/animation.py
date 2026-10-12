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
    return dict(x=x, y=y, scale=scale, alpha=alpha)
