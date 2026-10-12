"""5 張自行繪製的測試圖，每張 4 秒；檢查 H.264、尺寸、600 影格與解碼。"""
import argparse
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from studio.export import export_video, ffmpeg_path
from studio.models import load_photo, new_label
from studio.rendering import font_path


def samples():
    photos = []
    palette = ("#b7a58c", "#879789", "#c0b2a5", "#80939f", "#a48e79")
    for i, color in enumerate(palette):
        image = Image.new("RGB", (1200, 1600), color)
        draw = ImageDraw.Draw(image)
        # 測試用室內空間示意；非實際客戶案例，也非 AI 分析結果。
        draw.polygon([(0, 0), (900, 140), (900, 1030), (0, 1150)], fill="#e6ded2")
        draw.polygon([(900, 140), (1200, 0), (1200, 1200), (900, 1030)], fill="#cec4b3")
        draw.rectangle((100, 260, 700, 730), fill="#90a6aa", outline="#faf1df", width=22)
        draw.line((400, 260, 400, 730), fill="#faf1df", width=20)
        draw.rounded_rectangle((100, 960, 810, 1240), 35, fill=color)
        draw.rectangle((760, 810, 960, 1260), fill="#816c50")
        buffer = BytesIO(); image.save(buffer, "PNG")
        photo = load_photo(f"測試示意_{i+1}.png", buffer.getvalue())
        label = new_label(4)
        label.update(text=["木紋地板", "展示收納", "空間採光", "壁面色彩", "案例細節"][i],
                     animation="left", start=.3, enter=.7, y=.25 + i * .05)
        photo.labels.append(label)
        photos.append(photo)
    return photos


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, choices=[360, 720, 1080], default=1080)
    parser.add_argument("--output", default="artifacts/verification.mp4")
    args = parser.parse_args()
    height = args.width * 16 // 9
    started = time.monotonic()
    data = export_video(samples(), args.width, height, progress=lambda p, s: print(s, flush=True) if p in (.98, 1.) else None)
    path = Path(args.output); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    binary = ffmpeg_path()
    probe = subprocess.run([binary, "-hide_banner", "-i", str(path), "-map", "0:v:0",
                            "-f", "null", "-"], capture_output=True, timeout=180)
    log = probe.stderr.decode("utf-8", errors="replace")
    assert probe.returncode == 0, log
    assert "h264" in log and f"{args.width}x{height}" in log and "00:00:20.00" in log, log
    assert "frame=  600" in log or "frame=600" in log, log
    frame_path = path.with_suffix(".png")
    subprocess.run([binary, "-y", "-ss", "1.5", "-i", str(path), "-frames:v", "1", str(frame_path)], check=True, capture_output=True)
    report = dict(photos=5, seconds=20, frames=600, width=args.width, height=height, fps=30,
                  codec="h264", decode="passed", bytes=len(data), elapsed_seconds=round(time.monotonic()-started, 2),
                  font=font_path(), sample_type="自行繪製之室內空間示意")
    path.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
