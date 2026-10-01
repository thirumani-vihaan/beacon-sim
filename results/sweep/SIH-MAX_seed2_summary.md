# BEACON-SIM performance log

Scenario **SIH-MAX** · seed 2 · config 372d8d6c5615 · simulation

| Metric | Value | Official spec | Result |
|---|---|---|---|
| simulation_duration_s | 30.0 |  |  |
| frames | 900 |  |  |
| processing_fps | 154.4 | >= 20.0 | PASS |
| wall_fps | 44.9 |  |  |
| acquisition_time_s | 0.167 | <= 2.0 | PASS |
| acquisition_from_fov_s | 0.067 |  |  |
| mean_tracking_error_px | 4.04 | <= 10.0 | PASS |
| max_tracking_error_px | 60.16 |  |  |
| mean_tracking_error_urad | 440.6 |  |  |
| centroid_rmse_px | 0.163 |  |  |
| mean_centroid_error_px | 0.142 |  |  |
| lock_retention_pct | 100.0 |  |  |
| target_loss_pct | 0.0 | < 5.0 | PASS |
| reacquisitions | 1 |  |  |
| max_reacquisition_s | 0.033 | <= 1.0 | PASS |
| mean_reacquisition_s | 0.033 |  |  |
| processing_ms_mean | 6.48 |  |  |
| processing_ms_p95 | 13.32 |  |  |

**Overall: ALL OFFICIAL SPECS MET**

## Physical feasibility

Slew budget 1600.0 px/s · required 720.0 px/s · spare 880.0 px/s · worst-case acquisition 0.68 s
- ✓ every official spec is physically achievable for this scenario
