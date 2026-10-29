"""Generate synthetic OCR examples, without user images or real personal identifiers."""

import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main():
    if shutil.which("fc-match"):
        font_path = subprocess.check_output(
            ["fc-match", "-f", "%{file}", "Noto Sans CJK KR"]
        ).decode()
    else:
        font_path = str(Path(os.environ["WINDIR"]) / "Fonts" / "malgun.ttf")
    font = ImageFont.truetype(font_path, 48)
    folder = Path("artifacts")
    folder.mkdir(exist_ok=True)
    for filename, rows in {
        "ocr-sample.png": [
            "몸사 판매 맘눌뎀",
            "지인합성 야상극",
            "서울 학생 용돈 관리",
            "ㄱㄷ ㄷㄸ ㅇㄹ",
        ],
        "ocr-neutral.png": ["서울 학생 용돈 관리"],
    }.items():
        image = Image.new("RGB", (1200, 460), "white")
        draw = ImageDraw.Draw(image)
        for index, text in enumerate(rows):
            draw.text((45, 35 + index * 95), text, fill="#202020", font=font)
        image.save(folder / filename)
        print(filename)
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (400, 200), "white").save(folder / "ocr-oriented.jpg", exif=exif)


if __name__ == "__main__":
    main()
