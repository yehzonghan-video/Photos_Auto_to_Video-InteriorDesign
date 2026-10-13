"""產生本專案自繪的幾何 PNG；不是客戶 LOGO 或第三方素材。"""
from pathlib import Path
from PIL import Image, ImageDraw


def main():
    folder=Path(__file__).resolve().parents[1]/"assets"/"overlays"
    folder.mkdir(parents=True,exist_ok=True)
    arrow=Image.new("RGBA",(480,240));draw=ImageDraw.Draw(arrow)
    draw.polygon([(12,84),(288,84),(288,12),(468,120),(288,228),(288,156),(12,156)],fill="#c36540",outline="#fff4df",width=8)
    arrow.save(folder/"arrow.png")
    frame=Image.new("RGBA",(640,280));draw=ImageDraw.Draw(frame)
    draw.rounded_rectangle((8,8,631,271),radius=34,fill=(36,49,39,205),outline="#e8bd78",width=8)
    frame.save(folder/"price-frame.png")


if __name__=="__main__":main()
