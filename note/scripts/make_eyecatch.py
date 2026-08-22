#!/usr/bin/env python3
"""npo-largo 記事のアイキャッチ(1200x630 OGP)を生成する。

使い方:
    python3 make_eyecatch.py "記事タイトル" "フォーカスKW" 出力パス.png

日本語フォントは以下の順に探索し、見つかったものを使う。
すべて見つからない場合は非ゼロ終了するので、呼び出し側は
「アイキャッチ未設定」として処理を続行すること（記事作成は止めない）。
"""
import sys, os, glob

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/fonts-japanese-mincho.ttf",
]

BG      = (14, 74, 76)      # 深い青緑
ACCENT  = (233, 178, 68)    # 山吹
TEXT    = (255, 255, 255)
SUBTEXT = (198, 219, 219)

W, H = 1200, 630


def find_font():
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    for pat in ("/usr/share/fonts/**/*.ttc", "/usr/share/fonts/**/*.ttf",
                "/usr/share/fonts/**/*.otf"):
        for p in sorted(glob.glob(pat, recursive=True)):
            name = os.path.basename(p).lower()
            if "emoji" in name or "unifont" in name:
                continue
            if any(k in name for k in ("japanese", "cjk", "noto", "ipa", "gothic")):
                return p
    return None


def wrap(text, per_line):
    return [text[i:i + per_line] for i in range(0, len(text), per_line)]


def main():
    if len(sys.argv) < 4:
        print("usage: make_eyecatch.py TITLE KEYWORD OUT.png", file=sys.stderr)
        return 2
    title, keyword, out = sys.argv[1], sys.argv[2], sys.argv[3]

    from PIL import Image, ImageDraw, ImageFont

    font_path = find_font()
    if not font_path:
        print("NO_JAPANESE_FONT", file=sys.stderr)
        return 3

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # 左のアクセントバー
    d.rectangle([0, 0, 18, H], fill=ACCENT)
    # 右下の装飾
    d.rectangle([W - 260, H - 6, W, H], fill=ACCENT)

    # タイトルは長さに応じて字数/行とサイズを決め、最大3行に収める
    n = len(title)
    if n <= 24:
        size, per = 68, 12
    elif n <= 36:
        size, per = 60, 14
    elif n <= 48:
        size, per = 52, 16
    else:
        size, per = 44, 19
    ftitle = ImageFont.truetype(font_path, size)
    lines = wrap(title, per)[:3]

    line_h = size + 22
    total = line_h * len(lines)
    y = (H - total) // 2 - 18
    for ln in lines:
        d.text((78, y), ln, font=ftitle, fill=TEXT)
        y += line_h

    # 上部のキーワードバッジ
    fkw = ImageFont.truetype(font_path, 30)
    label = f"　{keyword}　"
    bbox = d.textbbox((0, 0), label, font=fkw)
    bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.rectangle([78, 62, 78 + bw + 16, 62 + bh + 24], fill=ACCENT)
    d.text((86, 70), label, font=fkw, fill=BG)

    # 下部のクレジット
    ffoot = ImageFont.truetype(font_path, 28)
    d.text((78, H - 96), "NPO法人 琉仁福祉会 ｜ 精神保健福祉士が解説",
           font=ffoot, fill=SUBTEXT)

    img.save(out, "PNG", optimize=True)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
