#!/usr/bin/env python3
"""研修eラーニング 生成スクリプト

台本（content/<年度>/*.json）と年度ごとの事実データ（facts/<年度>.json）から、
  - スライド画像（字幕入り）
  - 読み上げ音声（pyopenjtalk）
  - MP4動画
  - 確認テスト付きの受講ページ（dist/<年度>/index.html）
を作る。

使い方:
  python build.py R8            # 令和8年度分をすべて作る
  python build.py R9 01_gyakutai # 1本だけ作る
  python build.py R8 --dry       # 動画は作らず、台本の文字数と予想時間だけ確認
"""
import copy, html, json, re, subprocess, sys, wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
FONT = "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"
W, H = 1920, 1080
NAVY, ACCENT, INK, MUTED = (31, 58, 95), (230, 140, 60), (30, 34, 40), (110, 118, 128)
SR = 48000
PAUSE_SENT, PAUSE_SLIDE = 0.35, 0.9
ORG = "NPO法人琉仁福祉会"

def font(size):
    return ImageFont.truetype(FONT, size)

# ---------- 台本の読み込み（前年度版の差分を当てる） ----------
def fill(text, facts):
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(facts.get(m.group(1), "{{%s}}" % m.group(1))), text)

def load_module(year, path, facts):
    data = json.loads(path.read_text(encoding="utf-8"))
    if "base" in data:  # 前年度の台本を土台に、差分だけ書き換える
        base_year, base_id = data["base"].split("/")
        base = json.loads((ROOT / "content" / base_year / f"{base_id}.json").read_text(encoding="utf-8"))
        merged = copy.deepcopy(base)
        for k, v in data.items():
            if k not in ("base", "slide_ops", "quiz_ops"):
                merged[k] = v
        slides = merged["slides"]
        # 見出しで場所を指定した操作は、番号に置き換えてから当てる（前年度の台本が増減しても壊れない）
        ops = []
        for op in data.get("slide_ops", []):
            op = dict(op)
            if "heading" in op:
                hits = [i for i, s in enumerate(slides) if s.get("heading") == op["heading"]]
                if not hits:
                    raise SystemExit(f"{path.name}: 見出し「{op['heading']}」が前年度の台本にありません")
                op["at"] = hits[0]
            ops.append(op)
        for op in sorted(ops, key=lambda o: -o["at"]):
            if op["op"] == "replace":
                slides[op["at"]] = op["slide"]
            elif op["op"] == "insert_after":
                slides[op["at"] + 1:op["at"] + 1] = op["slides"]
            elif op["op"] == "delete":
                del slides[op["at"]]
        quiz = merged["quiz"]
        for op in data.get("quiz_ops", []):
            if op["op"] == "replace":
                quiz[op["at"]] = op["item"]
            elif op["op"] == "append":
                quiz.append(op["item"])
        data = merged
    s = json.dumps(data, ensure_ascii=False)
    return json.loads(fill(s, facts))

# ---------- スライド描画 ----------
def wrap(draw, text, fnt, width):
    lines, line = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(line); line = ""; continue
        if draw.textlength(line + ch, font=fnt) > width and line:
            # 行頭禁則（句読点を行頭に置かない）
            if ch in "、。）」』":
                line += ch; continue
            lines.append(line); line = ch
        else:
            line += ch
    if line:
        lines.append(line)
    return lines

def render(slide, caption, mod, idx, total):
    img = Image.new("RGB", (W, H), (250, 250, 247))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 8], fill=ACCENT)
    meta = f"{mod['year_label']}　{mod['title']}　{idx}/{total}"
    d.text((W - 60, 40), meta, font=font(30), fill=MUTED, anchor="ra")
    d.text((60, 40), ORG, font=font(30), fill=MUTED)
    if slide.get("type") == "title":
        d.rectangle([0, 300, W, 640], fill=NAVY)
        d.text((W // 2, 400), mod["title"], font=font(96), fill="white", anchor="mm")
        d.text((W // 2, 530), mod["subtitle"], font=font(48), fill=(220, 228, 240), anchor="mm")
        d.text((W // 2, 720), f"所要時間 約{mod['minutes']}分　最終確認日 {mod['checked']}", font=font(36), fill=INK, anchor="mm")
    else:
        d.rectangle([60, 110, 76, 200], fill=ACCENT)
        hy = 155
        for ln in wrap(d, slide["heading"], font(64), W - 200)[:2]:
            d.text((100, hy), ln, font=font(64), fill=NAVY, anchor="lm"); hy += 80
        y = hy + 40
        for b in slide.get("bullets", []):
            big = b.startswith("!")
            t = b.lstrip("!")
            f = font(52 if big else 46)
            lines = wrap(d, t, f, W - 330)
            d.ellipse([110, y + 14, 132, y + 36], fill=ACCENT if big else NAVY)
            for ln in lines:
                d.text((160, y), ln, font=f, fill=INK); y += int(f.size * 1.35)
            y += 22
        if slide.get("table"):
            y = draw_table(d, slide["table"], y + 10)
    # 字幕
    if caption:
        cf = font(42)
        lines = wrap(d, caption, cf, W - 240)[:3]
        bh = 40 + len(lines) * 58
        top = H - bh - 30
        d.rounded_rectangle([80, top, W - 80, H - 30], radius=18, fill=(20, 24, 30))
        cy = top + 22
        for ln in lines:
            d.text((W // 2, cy), ln, font=cf, fill="white", anchor="ma"); cy += 58
    return img

def draw_table(d, rows, y):
    f = font(38)
    cols = len(rows[0])
    x0, x1 = 120, W - 120
    # 左の列は中身に合わせた幅、残りを等分
    first = max(d.textlength(str(r[0]), font=f) for r in rows) + 60
    rest = (x1 - x0 - first) / max(cols - 1, 1)
    widths = [first] + [rest] * (cols - 1)
    for r, row in enumerate(rows):
        cells = [wrap(d, str(cell), f, widths[c] - 40) for c, cell in enumerate(row)]
        rh = 24 + max(len(c) for c in cells) * 50
        fill_c = NAVY if r == 0 else ((255, 255, 255) if r % 2 else (238, 241, 246))
        d.rectangle([x0, y, x1, y + rh], fill=fill_c, outline=(200, 205, 212))
        cx = x0
        for c, lines in enumerate(cells):
            ty = y + 12
            for ln in lines:
                d.text((cx + 20, ty), ln, font=f, fill="white" if r == 0 else INK); ty += 50
            cx += widths[c]
        y += rh
    return y

# ---------- 音声 ----------
def tts(text):
    import pyopenjtalk
    x, sr = pyopenjtalk.tts(text)
    assert sr == SR
    return (x / 32768.0).astype(np.float32) if x.dtype != np.float32 else x

def silence(sec):
    return np.zeros(int(SR * sec), dtype=np.float32)

def write_wav(path, x):
    y = np.clip(x * 32767 if np.abs(x).max() <= 1.5 else x, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(y.tobytes())

def spoken(text):
    """字幕の文字を、読み上げ用に直す（字幕はそのまま、音声だけ読みを整える）"""
    for a, b in READINGS.items():
        text = text.replace(a, b)
    return text

READINGS = {
    "BCP": "ビーシーピー", "％": "パーセント", "%": "パーセント", "1/100": "100分の1",
    "通所系": "つうしょけい", "居住系": "きょじゅうけい", "身体拘束等": "身体拘束とう",
    "従事者等": "従事者とう", "施設等": "施設とう", "嘔吐物": "おうと物", "嘔吐": "おうと",
}

# ---------- 1本を作る ----------
def build_module(year, path, facts, dry=False):
    mod = load_module(year, path, facts)
    mod["year_label"] = facts["year_label"]
    out = ROOT / "dist" / year
    work = out / "work" / mod["id"]
    work.mkdir(parents=True, exist_ok=True)
    slides = mod["slides"]
    chars = sum(len(s) for sl in slides for s in sl.get("say", []))
    mod["minutes"] = max(1, round(chars / 5.1 / 60))  # 表紙の「所要時間」は台本の長さから出す
    if dry:
        return mod, chars, None
    audio, concat = [], []
    n = 0
    for i, sl in enumerate(slides, 1):
        says = sl.get("say", []) or [""]
        for j, s in enumerate(says):
            a = tts(spoken(s)) if s else silence(1.5)
            gap = PAUSE_SLIDE if j == len(says) - 1 else PAUSE_SENT
            seg = np.concatenate([a, silence(gap)])
            audio.append(seg)
            img = render(sl, s, mod, i, len(slides))
            p = work / f"f{n:03d}.png"; img.save(p)
            concat.append((p, len(seg) / SR)); n += 1
    wav = work / "narration.wav"
    write_wav(wav, np.concatenate(audio))
    lst = work / "list.txt"
    with lst.open("w") as f:
        for p, dur in concat:
            f.write(f"file '{p}'\nduration {dur:.3f}\n")
        f.write(f"file '{concat[-1][0]}'\n")
    mp4 = out / f"{mod['id']}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-i", str(wav), "-vf", "fps=5,format=yuv420p", "-c:v", "libx264", "-tune", "stillimage",
                    "-crf", "28", "-c:a", "aac", "-b:a", "96k", "-shortest", "-movflags", "+faststart", str(mp4)],
                   check=True)
    secs = sum(d for _, d in concat)
    # 教材ページ用にスライド1枚目の画像（サムネイル）を残す
    render(slides[0], "", mod, 1, len(slides)).resize((640, 360)).save(out / f"{mod['id']}_thumb.jpg", quality=85)
    return mod, chars, secs

# ---------- 受講ページ ----------
def build_index(year, facts, mods):
    out = ROOT / "dist" / year
    cards = []
    for m, secs in mods:
        qs = []
        for qi, q in enumerate(m["quiz"]):
            opts = "".join(
                f'<label><input type="radio" name="q{qi}" value="{ci}"> {html.escape(c)}</label>'
                for ci, c in enumerate(q["choices"]))
            qs.append(f'<fieldset data-answer="{q["answer"]}" data-explain="{html.escape(q["explain"])}">'
                      f'<legend>問{qi+1}　{html.escape(q["q"])}</legend>{opts}<p class="ex"></p></fieldset>')
        src = "".join(f'<li><a href="{html.escape(s["url"])}" target="_blank" rel="noopener">{html.escape(s["name"])}</a></li>'
                      for s in m.get("sources", []))
        mins = f"{secs/60:.0f}分" if secs else f"約{m['minutes']}分"
        cards.append(f'''
<section class="mod" id="m-{m["id"]}" data-title="{html.escape(m["title"])}">
  <h2>{html.escape(m["title"])}<small>{mins}</small></h2>
  <video controls preload="none" poster="{m["id"]}_thumb.jpg" src="{m["id"]}.mp4"></video>
  <details><summary>確認テスト（{len(m["quiz"])}問・8割以上で修了）</summary>
    <form>{"".join(qs)}<button type="button" class="grade">採点する</button><p class="result"></p></form>
  </details>
  <details><summary>この研修の根拠（最終確認日 {m["checked"]}）</summary><ul>{src}</ul>
  <p class="note">{html.escape(m.get("review_note", ""))}</p></details>
</section>''')
    page = TEMPLATE.replace("{{YEAR}}", facts["year_label"]).replace("{{CARDS}}", "".join(cards)) \
        .replace("{{REPORT_TO}}", facts.get("report_to", ""))
    (out / "index.html").write_text(page, encoding="utf-8")

TEMPLATE = """<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{YEAR}} 法定研修</title>
<style>
:root{--ink:#1e2228;--muted:#6e7680;--navy:#1f3a5f;--accent:#e68c3c;--bg:#fafaf7;--card:#fff;--line:#dde1e6}
@media (prefers-color-scheme:dark){:root{--ink:#e8e8e3;--muted:#9aa2aa;--navy:#8fb3e0;--bg:#16191d;--card:#1f2328;--line:#343a40}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.7 "Hiragino Sans","Yu Gothic",sans-serif;padding:24px 16px 64px}
main{max-width:860px;margin:0 auto}h1{font-size:26px;margin:0 0 4px}header p{color:var(--muted);margin:0 0 20px}
.who{background:var(--card);border:1px solid var(--line);padding:14px;border-radius:10px;margin-bottom:20px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.who input{font:inherit;padding:6px 10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink);min-width:12em}
.mod{background:var(--card);border:1px solid var(--line);border-left:6px solid var(--accent);border-radius:10px;padding:16px;margin-bottom:20px}
.mod h2{margin:0 0 10px;font-size:20px;color:var(--navy)}.mod h2 small{font-size:13px;color:var(--muted);margin-left:8px}
video{width:100%;border-radius:8px;background:#000;aspect-ratio:16/9}
details{margin-top:10px}summary{cursor:pointer;font-weight:700}
fieldset{border:1px solid var(--line);border-radius:8px;margin:10px 0;padding:10px}legend{font-weight:700;padding:0 4px}
label{display:block;padding:4px 0}.ex{color:var(--muted);font-size:14px;margin:6px 0 0}
button{font:inherit;padding:8px 18px;border:0;border-radius:6px;background:var(--navy);color:#fff;cursor:pointer}
.ok{color:#2f8f5b;font-weight:700}.ng{color:#c23b3b;font-weight:700}.note{color:var(--muted);font-size:13px}
.log{margin-top:24px}.log button{margin-right:8px}
</style></head><body><main>
<header><h1>{{YEAR}} 法定研修（eラーニング）</h1>
<p>動画を見て、確認テストに答えてください。8割以上で修了です。修了したら、最後に受講記録を送ってください。</p></header>
<div class="who">氏名 <input id="name" placeholder="例：山田 花子"> 事業所 <input id="office" placeholder="例：越谷事業所"></div>
{{CARDS}}
<section class="log"><h2>受講記録</h2><p id="summary">まだ修了した研修はありません。</p>
<button id="csv">記録をダウンロード（CSV）</button><button id="mail">管理者にメールで送る</button></section>
</main><script>
const done={};
function save(){try{localStorage.setItem('elearn-{{YEAR}}',JSON.stringify(done))}catch(e){}}
try{Object.assign(done,JSON.parse(localStorage.getItem('elearn-{{YEAR}}')||'{}'))}catch(e){}
function who(){return [document.getElementById('name').value.trim(),document.getElementById('office').value.trim()]}
function refresh(){const k=Object.keys(done);document.getElementById('summary').textContent=k.length?k.map(t=>t+'（'+done[t].score+'・'+done[t].date+'）').join('／'):'まだ修了した研修はありません。'}
document.querySelectorAll('.grade').forEach(b=>b.onclick=()=>{
 const sec=b.closest('.mod'),fs=sec.querySelectorAll('fieldset');let ok=0,ans=0;
 fs.forEach(f=>{const c=f.querySelector('input:checked');const ex=f.querySelector('.ex');
  if(c){ans++;if(c.value===f.dataset.answer){ok++;ex.innerHTML='<span class="ok">正解</span> '+f.dataset.explain}else{ex.innerHTML='<span class="ng">不正解</span> '+f.dataset.explain}}else{ex.textContent='未回答です'}});
 const r=sec.querySelector('.result');if(ans<fs.length){r.textContent='すべての問題に答えてください。';return}
 const pass=ok/fs.length>=0.8;r.innerHTML=pass?'<span class="ok">修了です（'+ok+'/'+fs.length+'問正解）</span>':'<span class="ng">'+ok+'/'+fs.length+'問正解。動画を見直して、もう一度答えてください。</span>';
 if(pass){done[sec.dataset.title]={score:ok+'/'+fs.length,date:new Date().toLocaleDateString('ja-JP')};save();refresh()}});
function rows(){const [n,o]=who();return Object.keys(done).map(t=>[n,o,t,done[t].score,done[t].date])}
document.getElementById('csv').onclick=()=>{const [n]=who();if(!n){alert('氏名を入力してください');return}
 const csv='\\ufeff氏名,事業所,研修,得点,修了日\\n'+rows().map(r=>r.join(',')).join('\\n');
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));a.download='受講記録_'+n+'.csv';a.click()};
document.getElementById('mail').onclick=()=>{const [n]=who();if(!n){alert('氏名を入力してください');return}
 const body=rows().map(r=>r.join('　')).join('\\n');location.href='mailto:{{REPORT_TO}}?subject='+encodeURIComponent('【受講記録】{{YEAR}} 法定研修 '+n)+'&body='+encodeURIComponent(body)};
refresh();
</script></body></html>"""

def main():
    year = sys.argv[1]
    only = [a for a in sys.argv[2:] if not a.startswith("--")]
    dry = "--dry" in sys.argv or "--index" in sys.argv  # --index：動画は作り直さず、受講ページだけ作る
    facts = json.loads((ROOT / "facts" / f"{year}.json").read_text(encoding="utf-8"))
    mods = []
    for p in sorted((ROOT / "content" / year).glob("*.json")):
        if only and p.stem not in only:
            continue
        m, chars, secs = build_module(year, p, facts, dry)
        est = chars / 5.1
        print(f"{year}/{m['id']}: {len(m['slides'])}枚 {chars}字 予想{est/60:.1f}分" + (f" 実際{secs/60:.1f}分" if secs else ""))
        mods.append((m, secs))
    if ("--index" in sys.argv or not dry) and not only:
        build_index(year, facts, mods)
        print("受講ページ:", ROOT / "dist" / year / "index.html")

if __name__ == "__main__":
    main()
