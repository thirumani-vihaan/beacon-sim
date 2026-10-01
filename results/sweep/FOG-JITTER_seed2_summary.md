# BEACON-SIM performance log

Scenario **FOG-JITTER** · seed 2 · config 34b951a2274a · simulation

| Metric | Value | Official spec | Result |
|---|---|---|---|
| simulation_duration_s | 30.0 |  |  |
| frames | 900 |  |  |
| processing_fps | 134.4 | >= 20.0 | PASS |
| wall_fps | 50.1 |  |  |
| acquisition_time_s | 0.5 | <= 2.0 | PASS |
| acquisition_from_fov_s | 0.033 |  |  |
| mean_tracking_error_px | 1.64 | <= 10.0 | PASS |
| max_tracking_error_px | 21.76 |  |  |
| mean_tracking_error_urad | 179.3 |  |  |
| centroid_rmse_px | 0.142 |  |  |
| mean_centroid_error_px | 0.125 |  |  |
| lock_retention_pct | 100.0 |  |  |
| target_loss_pct | 0.0 | < 5.0 | PASS |
| reacquisitions | 1 |  |  |
| max_reacquisition_s | 0.033 | <= 1.0 | PASS |
| mean_reacquisition_s | 0.033 |  |  |
| processing_ms_mean | 7.44 |  |  |
| processing_ms_p95 | 16.23 |  |  |

**Overall: ALL OFFICIAL SPECS MET**

## Physical feasibility

Slew budget 800.0 px/s · required 240.0 px/s · spare 560.0 px/s · worst-case acquisition 1.07 s
- ✓ every official spec is physically achievable for this scenario
