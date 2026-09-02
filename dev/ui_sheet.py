from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
HERE = Path(__file__).resolve().parent
themes = ["native", "paper", "clinic", "bigprint", "slate"]
titles = {"native": "1  NATIVE - looks like any other Windows program",
          "paper": "2  PAPER - warm off-white, serif headings, a printed ledger",
          "clinic": "3  CLINIC - white, one deep green, calm and modern",
          "bigprint": "4  BIG PRINT - larger type, high contrast, for tired eyes and old screens",
          "slate": "5  SLATE - dark, for a laptop left on at a night desk"}
ims = [Image.open(HERE / f"ui-{t}.png").convert("RGB") for t in themes]
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
except Exception:
    font = ImageFont.load_default()
gap = 56
w = max(i.width for i in ims)
h = sum(i.height for i in ims) + gap * len(ims) + 10
sheet = Image.new("RGB", (w, h), "#2B2B2B")
d = ImageDraw.Draw(sheet)
y = 0
for im, t in zip(ims, themes):
    d.text((16, y + 14), titles[t], fill="white", font=font)
    y += gap
    sheet.paste(im, (0, y))
    y += im.height
sheet.save(HERE / "ui-all.png")
print("sheet", sheet.size)
