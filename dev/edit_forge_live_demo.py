"""Edit actual footage only; explicitly label accelerated CPU waiting and hold a real plan frame."""
import json,os,shutil,subprocess
from pathlib import Path
out=Path('artifacts/forge-glimmer-demo');target=out/'openbridge-live-glimmer-presentation.mp4'
if target.exists():raise SystemExit('Presentation already exists; preserve exported evidence')
capture=json.loads((out/'capture-manifest.json').read_text(encoding='utf-8'));scenes={s['name']:s['at_seconds'] for s in capture['scenes']}
font=out/'export-font.ttf';shutil.copyfile(Path(os.environ['WINDIR'])/'Fonts/segoeui.ttf',font)
wait_start=scenes['live-meta']+4;wait_end=scenes['validated']-4;validated=scenes['validated'];consent=scenes['consent'];latency=capture['model_trace']['elapsed_ms']/1000
(out/'speed-label.txt').write_text(f'CPU wait shown at 8x speed | Actual local inference: {latency:.2f} seconds',encoding='utf-8')
(out/'hold-label.txt').write_text('Actual validated proposal | Frame held for readability',encoding='utf-8')
prefix=out.as_posix()
filters=f'''[0:v]trim=start=0:end={wait_start},setpts=PTS-STARTPTS[a];
[0:v]trim=start={wait_start}:end={wait_end},setpts=(PTS-STARTPTS)/8,drawtext=fontfile={prefix}/export-font.ttf:textfile={prefix}/speed-label.txt:fontcolor=white:fontsize=28:x=(w-text_w)/2:y=25:box=1:boxcolor=black@0.9:boxborderw=12[b];
[0:v]trim=start={wait_end}:end={validated},setpts=PTS-STARTPTS[c];
[0:v]trim=start={validated}:end={consent},setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=5,drawtext=fontfile={prefix}/export-font.ttf:textfile={prefix}/hold-label.txt:fontcolor=white:fontsize=28:x=(w-text_w)/2:y=25:box=1:boxcolor=black@0.9:boxborderw=12[d];
[0:v]trim=start={consent}:end=170,setpts=PTS-STARTPTS[e];
[a][b][c][d][e]concat=n=5:v=1:a=0,fps=30[v]'''
(out/'presentation-filters.txt').write_text(filters,encoding='utf-8')
subprocess.run(['ffmpeg','-i',str(out/'openbridge-live-glimmer-170s.mp4'),'-filter_complex_script',str(out/'presentation-filters.txt'),'-map','[v]','-c:v','libx264','-preset','medium','-crf','23','-pix_fmt','yuv420p','-movflags','+faststart','-an',str(target),'-loglevel','error'],check=True)
print('Presentation exported; raw 170-second video retained.',flush=True)
