# Sample grader-style videos

Large videos are not committed. Generate a Benchmark-2 style clip (2000×2000 @ 30 fps + ground-truth CSV) with:

```powershell
python -m beacon_sim --make-video samples/grader_style_noisy.mp4 --preset NOISY --seconds 12
python -m beacon_sim --bench samples/grader_style_noisy.mp4
```
