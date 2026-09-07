#!/usr/bin/env python3
"""公開ゲートの客観項目を機械判定する。

  python3 gate_check.py "<フォーカスKW>" post.json aioseo.json [media.json]

判定できない主観項目（slug のローマ字性、事実の安全性、重複）は対象外。
終了コード 0 = 全項目 PASS、1 = FAIL あり、2 = 入力エラー。
"""
import json, os, re, sys


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def unwrap(v):
    """WordPress の {'rendered': ...} 形式を素の文字列にする。"""
    if isinstance(v, dict):
        return v.get("rendered", "")
    return v or ""


def strip_html(h):
    h = re.sub(r"(?is)<(script|style).*?</\1>", " ", h)
    h = re.sub(r"<[^>]+>", " ", h)
    h = re.sub(r"&nbsp;?|&[a-zA-Z#0-9]+;", " ", h)
    return h


def main():
    if len(sys.argv) < 4:
        print("usage: gate_check.py KEYWORD post.json aioseo.json [media.json]",
              file=sys.stderr)
        return 2
    kw = sys.argv[1]
    post = load(sys.argv[2])
    aio = load(sys.argv[3])
    media = load(sys.argv[4]) if len(sys.argv) > 4 and os.path.exists(sys.argv[4]) else {}

    # AIOSEO は {"posts":[{...}]} で返ることがある
    if isinstance(aio, dict) and "posts" in aio and aio["posts"]:
        aio = aio["posts"][0]

    title = unwrap(post.get("title"))
    html = unwrap(post.get("content"))
    excerpt = strip_html(unwrap(post.get("excerpt"))).strip()
    slug = post.get("slug", "") or ""
    featured = post.get("featured_media", 0) or 0

    a_title = (aio.get("title") or "").strip()
    a_desc = (aio.get("description") or "").strip()
    alt = (media.get("alt_text") or "").strip()

    text = strip_html(html)
    body = re.sub(r"\s", "", text)

    h2s = re.findall(r"(?is)<h2[^>]*>(.*?)</h2>", html)
    h2s = [strip_html(x).strip() for x in h2s]
    h3s = re.findall(r"(?is)<h3[^>]*>(.*?)</h3>", html)
    h3s = [strip_html(x).strip() for x in h3s]
    faq = [x for x in h3s if x.startswith("Q.") or x.startswith("Q．")]

    hrefs = re.findall(r'(?i)<a[^>]+href="(https?://[^"]+)"', html)
    ext = [u for u in hrefs if "npo-largo.com" not in u]
    inn = [u for u in hrefs if "npo-largo.com" in u]

    # 本文1段落目の最初の一文
    paras = re.findall(r"(?is)<p[^>]*>(.*?)</p>", html)
    first_sentence = ""
    for p in paras:
        t = strip_html(p).strip()
        if t:
            first_sentence = re.split(r"[。！？]", t)[0]
            break

    results = []

    def chk(name, ok, detail):
        results.append((name, bool(ok), detail))

    chk("1 KW形式", kw and not re.search(r"[\s　・／/、。！？!?]", kw) and 2 <= len(kw) <= 10,
        f"KW='{kw}' ({len(kw)}字)")
    chk("2a KWがタイトル先頭10字", kw in title[:10], f"title[:10]='{title[:10]}'")
    chk("2b KWが1段落目の最初の一文", kw in first_sentence, f"'{first_sentence[:40]}'")
    chk("2c KWがh2に1つ以上", any(kw in h for h in h2s), f"h2={len(h2s)}本")
    chk("2d KWがexcerpt先頭50字", kw in excerpt[:50], f"excerpt {len(excerpt)}字")
    chk("2e KWがAIOSEO desc先頭50字", kw in a_desc[:50], f"desc {len(a_desc)}字")
    chk("2f KWがAIOSEO title先頭10字", kw in a_title[:10], f"a_title[:10]='{a_title[:10]}'")
    chk("3 KW本文3回以上", body.count(kw) >= 3, f"{body.count(kw)}回")
    chk("4 本文2500字以上", len(body) >= 2500, f"{len(body)}字")
    chk("5 h2が5本以上", len(h2s) >= 5, f"{len(h2s)}本")
    chk("6 FAQ 3〜5問", 3 <= len(faq) <= 5, f"{len(faq)}問")
    chk("7 表が1つ以上", len(re.findall(r"(?i)<table", html)) >= 1,
        f"{len(re.findall(r'(?i)<table', html))}個")
    chk("8a 外部リンク1本以上", len(ext) >= 1, f"{len(ext)}本")
    chk("8b 内部リンク2本以上", len(inn) >= 2, f"{len(inn)}本")
    chk("9a アイキャッチ設定済み", featured not in (0, "0", None), f"featured_media={featured}")
    chk("9b alt_textにKW", kw in alt, f"alt='{alt[:40]}'")
    chk("10a AIOSEO title 35〜45字", 35 <= len(a_title) <= 45, f"{len(a_title)}字")
    chk("10b AIOSEO desc 120〜160字", 120 <= len(a_desc) <= 160, f"{len(a_desc)}字")

    print("=== 機械判定 ===")
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}  [{detail}]")

    ng = [n for n, ok, _ in results if not ok]
    print()
    print(f"slug（参考・機械判定の対象外）: {slug}")
    if ng:
        print(f"VERDICT: FAIL  ({len(ng)}項目) -> {', '.join(ng)}")
        return 1
    print("VERDICT: PASS  (機械項目はすべて充足)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
