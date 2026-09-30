"""Kalman tracker (constant-velocity, screen coordinates) + lock state machine SEARCH->ACQUIRE->LOCK->COAST->REACQUIRE."""
from __future__ import annotations

import numpy as np
from filterpy.kalman import KalmanFilter

SEARCH, ACQUIRE, LOCK, COAST, REACQUIRE = "SEARCH", "ACQUIRE", "LOCK", "COAST", "REACQUIRE"
STATES = [SEARCH, ACQUIRE, LOCK, COAST, REACQUIRE]


class Tracker:
    CONFIRM = 3        # consistent hits to declare LOCK
    MISS_TO_COAST = 2  # consecutive misses before COAST
    COAST_MAX_S = 0.5  # coast on prediction this long, then widen search (REACQUIRE)

    def __init__(self, dt: float, meas_sigma: float = 1.5, accel_sigma: float = 350.0):
        self.dt = dt
        self.kf = KalmanFilter(dim_x=4, dim_z=2)
        self.kf.F = np.array([[1, 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0], [0, 0, 0, 1]], float)
        self.kf.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], float)
        q = accel_sigma ** 2
        g = np.array([[dt ** 2 / 2], [dt]])
        blk = g @ g.T * q
        self.kf.Q = np.zeros((4, 4))
        self.kf.Q[np.ix_([0, 2], [0, 2])] = blk
        self.kf.Q[np.ix_([1, 3], [1, 3])] = blk
        self.kf.R = np.eye(2) * meas_sigma ** 2
        self.state, self.hits, self.misses, self.coast_t = SEARCH, 0, 0, 0.0
        self.initialised = False

    # ------------------------------------------------------------------
    @property
    def pos(self) -> np.ndarray:
        return self.kf.x[:2, 0].copy()

    @property
    def vel(self) -> np.ndarray:
        return self.kf.x[2:, 0].copy()

    def gate(self) -> float:
        """Innovation gate in pixels; grows while coasting so a fast beacon can be re-captured."""
        base = 3.5 * float(np.sqrt(np.trace(self.kf.P[:2, :2]) / 2 + self.kf.R[0, 0])) + 12
        if self.state in (COAST, REACQUIRE):
            base += 400 * self.coast_t
        return min(base, 450.0)

    def predict(self) -> np.ndarray | None:
        if not self.initialised:
            return None
        self.kf.predict()
        return self.pos

    def update(self, meas: np.ndarray | None) -> str:
        """meas: detected beacon position in screen coords (or None). Returns the new state."""
        if meas is not None:
            if not self.initialised:
                self.kf.x = np.array([[meas[0]], [meas[1]], [0.0], [0.0]])
                self.kf.P = np.diag([4.0, 4.0, 300.0 ** 2, 300.0 ** 2])
                self.initialised = True
            else:
                self.kf.update(meas.reshape(2, 1))
            self.misses, self.coast_t = 0, 0.0
            self.hits += 1
            if self.state in (SEARCH, ACQUIRE):
                self.state = LOCK if self.hits >= self.CONFIRM else ACQUIRE
            elif self.state in (COAST, REACQUIRE):
                self.state = LOCK
        else:
            self.misses += 1
            if self.state == ACQUIRE:
                self.hits = 0
                self.state = SEARCH
                self.initialised = False
            elif self.state == LOCK and self.misses >= self.MISS_TO_COAST:
                self.state = COAST
            if self.state in (COAST, REACQUIRE):
                self.coast_t += self.dt
                if self.coast_t > self.COAST_MAX_S:
                    self.state = REACQUIRE
                    self.kf.x[2:] *= 0.9  # velocity confidence decays while blind
        return self.state

    def reset(self) -> None:
        self.state, self.hits, self.misses, self.coast_t, self.initialised = SEARCH, 0, 0, 0.0, False
