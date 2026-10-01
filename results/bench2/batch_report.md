# Benchmark-2 batch report

Thresholds: `centroid_rmse_px <= 1`, `acquisition_time_s <= 2`, `max_reacquisition_s <= 1`, `lock_retention_pct >= 95`, `end_to_end_fps >= 20`

| Video | GT | Size (est.) | Centroid RMSE (px) | Acq. (s) | Max re-acq. (s) | Lock ret. (%) | Detect (%) | False alarms | E2E FPS | Thresholds |
|---|---|---|---|---|---|---|---|---|---|---|
| 01_official_clean.mp4 | yes | 10 | 0.059 | 0.067 | 0.0 | 100.0 | 100.0 | 0 | 33.5 | ✅ PASS |
| 02_max_noise.mp4 | yes | 9 | 0.194 | 0.067 | 0.0 | 100.0 | 100.0 | 0 | 55.8 | ✅ PASS |
| 03_fog_small_5px.mp4 | yes | 6 | 0.996 | 0.367 | 0.067 | 98.62 | 85.0 | 0 | 58.1 | ✅ PASS |
| 04_rain_large_20px.mp4 | yes | 20 | 0.179 | 0.067 | 0.0 | 100.0 | 100.0 | 0 | 55.9 | ✅ PASS |
| 05_lowlight_fast_random.mp4 | yes | 10 | 0.414 | 0.067 | 0.0 | 100.0 | 100.0 | 0 | 54.7 | ✅ PASS |
| 06_haze_circle_shape.mp4 | yes | 8 | 0.219 | 0.067 | 0.0 | 100.0 | 100.0 | 0 | 56.3 | ✅ PASS |
| 07_colour_1080p.mp4 | yes | 10 | 0.188 | 0.067 | 0.0 | 100.0 | 100.0 | 0 | 114.0 | ✅ PASS |
| 08_beacon_absent_gaps.mp4 | yes | 10 | 0.202 | 0.067 | 0.033 | 100.0 | 77.33 | 0 | 40.4 | ✅ PASS |

**8 / 8 videos meet every threshold.**
