# BEACON-SIM performance log

Scenario **NOISY** · seed 0 · config 59d79ef8f7be · simulation

| Metric | Value | Official spec | Result |
|---|---|---|---|
| simulation_duration_s | 30.0 |  |  |
| frames | 900 |  |  |
| processing_fps | 172.1 | >= 20.0 | PASS |
| wall_fps | 52.1 |  |  |
| acquisition_time_s | 0.333 | <= 2.0 | PASS |
| acquisition_from_fov_s | 0.1 |  |  |
| mean_tracking_error_px | 1.74 | <= 10.0 | PASS |
| max_tracking_error_px | 39.76 |  |  |
| mean_tracking_error_urad | 189.9 |  |  |
| centroid_rmse_px | 0.165 |  |  |
| mean_centroid_error_px | 0.144 |  |  |
| lock_retention_pct | 100.0 |  |  |
| target_loss_pct | 0.0 | < 5.0 | PASS |
| reacquisitions | 1 |  |  |
| max_reacquisition_s | 0.033 | <= 1.0 | PASS |
| mean_reacquisition_s | 0.033 |  |  |
| processing_ms_mean | 5.81 |  |  |
| processing_ms_p95 | 10.55 |  |  |

**Overall: ALL OFFICIAL SPECS MET**

## Physical feasibility

Slew budget 800.0 px/s · required 120.0 px/s · spare 680.0 px/s · worst-case acquisition 0.88 s
- ✓ every official spec is physically achievable for this scenario
