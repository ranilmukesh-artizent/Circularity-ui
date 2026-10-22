"""Mix the narration clips at their recorded start times onto the screen recording; write MP4 and SRT. python mux.py OUT.mp4"""
import json, re, subprocess, sys
from pathlib import Path
import imageio_ffmpeg

D = Path(__file__).resolve().parent
FF = imageio_ffmpeg.get_ffmpeg_exe()
out = Path(sys.argv[1])
tl = json.loads((D / 'timeline.json').read_text())
N = json.loads((D / 'narration.json').read_text(encoding='utf-8'))
DUR = json.loads((D / 'durations.json').read_text())
vid = sorted((D / 'rec').glob('*.webm'), key=lambda p: p.stat().st_size)[-1]
cuts = tl.get('cuts', [])
shift = lambda t: t - sum(min(b, t) - a for a, b in cuts if a < t)
clips = [[k, round(shift(t), 3)] for k, t in tl['clips']]
total = shift(tl['total'])
sel = '+'.join(f'between(t,{a},{b})' for a, b in cuts) or '0'
args = [FF, '-y', '-i', str(vid)]
for k, _ in clips:
    args += ['-i', str(D / 'audio' / f'{k}.wav')]
f = ''.join(f'[{i+1}:a]aresample=48000,adelay={int(t*1000)}|{int(t*1000)}[a{i}];' for i, (k, t) in enumerate(clips))
f += ''.join(f'[a{i}]' for i in range(len(clips))) + f'amix=inputs={len(clips)}:normalize=0:dropout_transition=0,apad,volume=1.6[aout]'
f = f"[0:v]fps=30,select='not({sel})',setpts=N/30/TB[vout];" + f
args += ['-filter_complex', f, '-map', '[vout]', '-map', '[aout]', '-t', str(total + 0.5),
         '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-r', '30', '-pix_fmt', 'yuv420p',
         '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', str(out)]
r = subprocess.run(args, capture_output=True, text=True)
print(r.stderr[-1500:] if r.returncode else 'ok ' + str(out))

# subtitles: each clip split into sentences, timed by length
def ts(x):
    h, m = int(x // 3600), int(x % 3600 // 60); s = x % 60
    return f'{h:02d}:{m:02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}'.replace(',1000', ',999')
srt, n = [], 1
for k, t in clips:
    text = N[k].replace(' I D ', ' ID ').replace('E R P', 'ERP')
    parts = [p.strip() for p in re.split(r'(?<=[.:?!])\s+', text) if p.strip()]
    tot = sum(len(p) for p in parts); cur = t
    for p in parts:
        d = DUR[k] * len(p) / tot
        srt.append(f'{n}\n{ts(cur)} --> {ts(cur + d)}\n{p}\n'); n += 1; cur += d
out.with_suffix('.srt').write_text('\n'.join(srt), encoding='utf-8')
print('subtitles', out.with_suffix('.srt'))
