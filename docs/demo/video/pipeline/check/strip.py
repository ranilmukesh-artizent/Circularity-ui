import subprocess, sys
from pathlib import Path
import imageio_ffmpeg
from PIL import Image, ImageDraw
FF=imageio_ffmpeg.get_ffmpeg_exe(); V=sys.argv[1]; a,b,st=float(sys.argv[2]),float(sys.argv[3]),float(sys.argv[4]); out=sys.argv[5]
O=Path('strip'); O.mkdir(exist_ok=True); [f.unlink() for f in O.glob('*.png')]
ts=[]; t=a
while t<=b: ts.append(t); t+=st
for i,t in enumerate(ts): subprocess.run([FF,'-y','-ss',f'{t:.2f}','-i',V,'-frames:v','1','-vf','scale=640:-1',str(O/f'{i:02d}.png')],capture_output=True)
W,H=640,400; cols=4; rows=(len(ts)+cols-1)//cols; sh=Image.new('RGB',(W*cols,H*rows),'white'); d=ImageDraw.Draw(sh)
for i,t in enumerate(ts):
    im=Image.open(O/f'{i:02d}.png'); x,y=(i%cols)*W,(i//cols)*H; sh.paste(im,(x,y)); d.rectangle([x,y,x+70,y+18],fill='black'); d.text((x+4,y+3),f'{t:.0f}s',fill='yellow')
sh.save(out)
