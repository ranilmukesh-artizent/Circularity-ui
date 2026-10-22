"""Render narration.json to audio/<id>.wav with Kokoro (am_michael) and write durations.json.
Run with the voice venv:  %TEMP%\\cvlv\\Scripts\\python tts.py [KOKORO_DIR] [--only c4d,c7]
KOKORO_DIR holds kokoro-v1.0.onnx and voices-v1.0.bin (default %TEMP%\\cvlv\\kokoro)."""
import json, os, sys
from pathlib import Path
import numpy as np, soundfile as sf
from kokoro_onnx import Kokoro

D = Path(__file__).resolve().parent
args = [a for a in sys.argv[1:] if not a.startswith('--')]
K = Path(args[0]) if args else Path(os.environ['TEMP']) / 'cvlv' / 'kokoro'
only = sys.argv[sys.argv.index('--only') + 1].split(',') if '--only' in sys.argv else None
VOICE, SPEED, TAIL = 'am_michael', 0.94, 0.15

k = Kokoro(str(K / 'kokoro-v1.0.onnx'), str(K / 'voices-v1.0.bin'))
N = json.loads((D / 'narration.json').read_text(encoding='utf-8'))
dp = D / 'durations.json'
dur = json.loads(dp.read_text()) if dp.exists() else {}
(D / 'audio').mkdir(exist_ok=True)
for key, text in N.items():
    if only and key not in only:
        continue
    a, sr = k.create(text, voice=VOICE, speed=SPEED, lang='en-us')
    a = np.concatenate([a, np.zeros(int(sr * TAIL), dtype=a.dtype)])
    sf.write(D / 'audio' / f'{key}.wav', a, sr)
    dur[key] = round(len(a) / sr, 2)
    print(f'{key}: {dur[key]} s')
dp.write_text(json.dumps(dur, indent=1))
print('total', round(sum(dur[k] for k in N), 1), 's')
