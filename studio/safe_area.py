"""依使用者提供的1080×1920安全區圖量測；只規範自動標題的初始位置。"""
import json
from pathlib import Path

SAFE_AREA = json.loads((Path(__file__).resolve().parents[1] / 'frontend' / 'safe-area.json').read_text(encoding='utf-8'))


def title_position():
    return dict(x=SAFE_AREA['inner']['left']/SAFE_AREA['width'],
                y=SAFE_AREA['inner']['top']/SAFE_AREA['height'])
