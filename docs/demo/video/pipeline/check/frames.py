"""Extract a frame at each clip's start+1s and end-0.4s from the muxed video; tile into contact sheets. python frames.py VIDEO"""
import json, subprocess, sys
from pathlib import Path
import imageio_ffmpeg
from PIL import Image, ImageDraw
P = Path(r'C:\repos\astra-prism-DI\ayush-ui\Circularity-ui\docs\demo\video\pipeline')
FF = imageio_ffmpeg.get_ffmpeg_exe(); V = sys.argv[1]
tl = json.loads((P/'timeline_cxo.json').read_text()); DUR = json.loads((P/'durations_cxo.json').read_text())
cuts = tl['cuts']; shift = lambda t: t - sum(min(b, t) - a for a, b in cuts if a < t)
O = Path('frames'); O.mkdir(exist_ok=True); [f.unlink() for f in O.glob('*.png')]
shots = []
clips = [[k, shift(t)] for k, t in tl['clips']]
for i, (k, t) in enumerate(clips):
    nxt = clips[i+1][1] if i+1 < len(clips) else t + DUR[k]
    if t + DUR[k] > nxt + 0.05: print('OVERLAP', k, round(t + DUR[k] - nxt, 2))
    for tag, x in (('a', t + 1.0), ('b', t + DUR[k] - 0.4)):
        f = O / f'{i:02d}{tag}-{k}.png'
        subprocess.run([FF, '-y', '-ss', f'{x:.2f}', '-i', V, '-frames:v', '1', '-vf', 'scale=720:-1', str(f)], capture_output=True)
        shots.append((f, f'{k}{tag} {x:.1f}s'))
for s in range(0, len(shots), 12):
    grp = shots[s:s+12]; W, H = 720, 450; sheet = Image.new('RGB', (W*3, H*4), 'white'); d = ImageDraw.Draw(sheet)
    for j, (f, lab) in enumerate(grp):
        try: im = Image.open(f)
        except Exception: continue
        x, y = (j % 3) * W, (j // 3) * H; sheet.paste(im, (x, y)); d.rectangle([x, y, x+170, y+22], fill='black'); d.text((x+5, y+5), lab, fill='yellow')
    sheet.save(f'sheet{s//12}.png')
print('sheets', (len(shots)+11)//12)
