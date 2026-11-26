from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "docs" / "images"
FONT_REGULAR = Path("C:/Windows/Fonts/msyh.ttc")
FONT_BOLD = Path("C:/Windows/Fonts/msyhbd.ttc")
INK = "#202b32"
MUTED = "#657582"
BLUE = "#356e9a"
PAPER = "#f1f4f5"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REGULAR), size)


def open_rgb(name: str) -> Image.Image:
    return Image.open(MEDIA / name).convert("RGB")


def fit(image: Image.Image, width: int, height: int) -> Image.Image:
    image = image.copy()
    image.thumbnail((width, height), Image.Resampling.LANCZOS)
    return image


def workflow_frame(filename: str, label: str, index: int) -> Image.Image:
    canvas = Image.new("RGB", (1000, 600), PAPER)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 1000, 72), fill="white")
    draw.text((28, 18), "Retouch Desk", font=font(25, True), fill=INK)
    draw.text((222, 25), f"{index:02d} / 04", font=font(15), fill=BLUE)
    draw.text((965, 23), label, font=font(18), fill=INK, anchor="ra")

    source = open_rgb(filename)
    preview = fit(source, 940, 500)
    x = (1000 - preview.width) // 2
    y = 82 + (500 - preview.height) // 2
    draw.rounded_rectangle((x - 5, y - 5, x + preview.width + 5, y + preview.height + 5), radius=4, fill="white", outline="#d6dde1", width=1)
    canvas.paste(preview, (x, y))
    return canvas


def save_workflow_gif() -> None:
    steps = [
        ("demo-before.png", "原始图片"),
        ("app-english-selection.png", "框选英文并核对识别"),
        ("app-chinese-selection.png", "框选中文并确认替换文字"),
        ("demo-after.png", "修改前后效果"),
    ]
    frames = [workflow_frame(filename, label, index) for index, (filename, label) in enumerate(steps, start=1)]
    frames[0].save(
        MEDIA / "workflow-demo.gif",
        save_all=True,
        append_images=frames[1:],
        duration=[1600, 2000, 2000, 2200],
        loop=0,
        optimize=True,
    )


def save_social_preview() -> None:
    canvas = Image.new("RGB", (1280, 640), PAPER)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 1280, 9), fill=BLUE)

    icon = Image.open(ROOT / "assets" / "app-icon.png").convert("RGBA")
    icon.thumbnail((58, 58), Image.Resampling.LANCZOS)
    canvas.paste(icon, (56, 56), icon)
    draw.text((130, 62), "Retouch Desk", font=font(27, True), fill=INK)
    draw.text((58, 160), "图片中文字修改", font=font(51, True), fill=INK)
    draw.text((60, 239), "本地 CPU 图片文字编辑工具", font=font(26), fill=MUTED)
    draw.line((60, 302, 455, 302), fill="#cbd4d9", width=2)

    draw.text((60, 334), "矩形 / 自由画圈选区  ·  OCR 辅助识别", font=font(20), fill=INK)
    draw.text((60, 378), "手动确认文字  ·  预览后导出 PNG", font=font(20), fill=INK)
    draw.text((60, 442), "无需 GPU 或云端模型", font=font(23, True), fill=BLUE)
    draw.text((60, 548), "Windows 10 / 11  ·  v0.5.0", font=font(17), fill=MUTED)

    draw.text((540, 75), "BEFORE", font=font(15, True), fill=MUTED)
    draw.text((910, 75), "AFTER", font=font(15, True), fill=MUTED)

    for x, filename in ((530, "demo-before.png"), (900, "demo-after.png")):
        image = fit(open_rgb(filename), 340, 210)
        draw.rounded_rectangle((x - 7, 101, x + 347, 327), radius=6, fill="white", outline="#d4dce0", width=1)
        paste_x = x + (340 - image.width) // 2
        paste_y = 107 + (210 - image.height) // 2
        canvas.paste(image, (paste_x, paste_y))

    canvas.save(MEDIA / "social-preview.png", optimize=True)


if __name__ == "__main__":
    save_workflow_gif()
    save_social_preview()
