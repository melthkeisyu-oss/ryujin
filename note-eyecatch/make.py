import sys
from PIL import Image, ImageDraw, ImageFont
num, title, out = sys.argv[1], sys.argv[2], sys.argv[3]
base = Image.open('080.png').convert('RGB')
W,H = base.size
CUT = 431
ORANGE=(255,117,29); R=26.2
# render clean dotted bottom at 4x supersample
S=4
bot = Image.new('RGB',(W*S,(H-CUT)*S),'white')
d = ImageDraw.Draw(bot)
for k in range(-1,8):
    for (y0,x0) in ((77.4,65.7),(12.5,129.5)):
        y = y0+128.9*k
        if y < CUT-40 or y > H+40: continue
        for j in range(-1,11):
            x = x0+127.5*j
            cx,cy=x*S,(y-CUT)*S
            d.ellipse([cx-R*S,cy-R*S,cx+R*S,cy+R*S],fill=ORANGE)
bot = bot.resize((W,H-CUT), Image.LANCZOS)
img = base.copy(); img.paste(bot,(0,CUT))
d = ImageDraw.Draw(img)
# number: outlined
fn = ImageFont.truetype('/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf', 60)
t = '#'+num
bb = d.textbbox((0,0),t,font=fn)
x = (W-(bb[2]-bb[0]))//2 - bb[0]; y = 455 - bb[1]
d.text((x,y),t,font=fn,fill='white',stroke_width=3,stroke_fill='black')
# title
ft = ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc', 27, index=0)
# letter spacing ~2px
def spaced_width(s,f,sp):
    return sum(d.textbbox((0,0),ch,font=f)[2] for ch in s)+sp*(len(s)-1)
sp=2
tw = spaced_width(title,ft,sp)
x = (W-tw)//2; y=538
for ch in title:
    d.text((x,y),ch,font=ft,fill='black',stroke_width=1,stroke_fill='black')
    x += d.textbbox((0,0),ch,font=ft)[2]+sp
img.save(out,'PNG',optimize=True)
print(out, img.size)
