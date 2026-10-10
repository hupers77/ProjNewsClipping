"""앱 아이콘(app.ico) 생성: uv run python packaging/make_icon.py  (Pillow 필요 — streamlit 의존성)."""

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 256
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((8, 8, SIZE - 8, SIZE - 8), radius=48, fill=(43, 95, 217, 255))
# 신문 한 장: 흰 종이 + 머리 제목 + 본문 줄
d.rounded_rectangle((52, 48, 204, 208), radius=14, fill=(255, 255, 255, 255))
d.rectangle((70, 66, 186, 94), fill=(43, 95, 217, 255))
for i, y in enumerate((112, 130, 148, 166, 184)):
    d.rectangle((70, y, 186 if i % 2 == 0 else 150, y + 8), fill=(176, 184, 200, 255))
out = Path(__file__).with_name("app.ico")
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(f"wrote {out}")
