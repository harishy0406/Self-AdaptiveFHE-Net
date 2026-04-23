"""
SAHF - Utility Functions
=========================
Common utility functions for the Self-Adaptive Homomorphic Framework.
Includes logging, timing, mathematical helpers, and data I/O.
"""

import os
import sys
import json
import time
import logging
import numpy as np
from datetime import datetime
from functools import wraps

# Force UTF-8 output on Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        # In Jupyter and some environments, reconfigure() is not available
        pass


# ─── Logging Setup ─────────────────────────────────────────────
def setup_logger(name: str = "SAHF", level: int = logging.INFO) -> logging.Logger:
    """Configure and return a formatted logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "[%(asctime)s] %(name)s | %(levelname)s | %(message)s",
            datefmt="%H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


logger = setup_logger()


# ─── Timer Decorator ───────────────────────────────────────────
def timer(func):
    """Decorator to measure function execution time."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        logger.info(f"[TIMER] {func.__name__} executed in {elapsed:.4f}s")
        return result
    return wrapper


# ─── Mathematical Helpers ──────────────────────────────────────
def noise_growth_model(noise_t: float, op_type: str, depth: int, scale: float) -> float:
    """
    Formal noise growth model:
        Noise(t+1) = f(Noise_t, Op_t, Depth_t, Scale_t)
    
    Implements:
        O' = O × (1 + w1·Depth + w2·Op_weight + w3·Scale_factor)
    
    Args:
        noise_t: Current noise level
        op_type: Type of operation ('add' or 'multiply')
        depth: Current computational depth
        scale: Current scale factor
    
    Returns:
        Predicted next noise value
    """
    # Learnable weights (empirically tuned)
    W1_DEPTH = 0.08       # Depth contribution
    W2_OP_ADD = 0.02      # Addition noise weight
    W2_OP_MUL = 0.15      # Multiplication noise weight  
    W3_SCALE = 0.04       # Scale factor contribution
    
    op_weight = W2_OP_MUL if op_type == "multiply" else W2_OP_ADD
    scale_factor = np.log1p(scale) / 10.0  # Normalize scale contribution
    
    growth = 1.0 + W1_DEPTH * depth + op_weight + W3_SCALE * scale_factor
    noise_next = noise_t * growth
    
    # Add small stochastic component for realism
    noise_next += np.random.normal(0, 0.005)
    
    return np.clip(noise_next, 0.0, 1.0)


def compute_noise_proxy(depth: int, scale: float, num_muls: int, 
                        base_noise: float = 0.01) -> float:
    """
    Compute a noise proxy indicator:
        noise ≈ depth × scale_growth × operation_weight
    
    Args:
        depth: Current circuit depth
        scale: Current scale value
        num_muls: Number of multiplications performed
        base_noise: Base noise floor
    
    Returns:
        Estimated noise level [0, 1]
    """
    scale_growth = np.log1p(scale) / 20.0
    op_weight = 1.0 + 0.3 * num_muls
    noise = base_noise + depth * scale_growth * op_weight * 0.01
    return np.clip(noise, 0.0, 1.0)


# ─── Data I/O Utilities ───────────────────────────────────────
def save_metrics(metrics: dict, filepath: str):
    """Save metrics dictionary to JSON file."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(metrics, f, indent=2, default=str)
    logger.info(f"[METRICS] Saved to {filepath}")


def load_metrics(filepath: str) -> dict:
    """Load metrics from JSON file."""
    with open(filepath, 'r') as f:
        return json.load(f)


def ensure_directories(base_path: str):
    """Create all required project directories."""
    dirs = [
        "data", "models", "results", "results/plots",
        "src", "notebooks", "dashboard"
    ]
    for d in dirs:
        os.makedirs(os.path.join(base_path, d), exist_ok=True)
    logger.info("[DIRS] All project directories verified")


# ─── Sliding Window Creator ───────────────────────────────────
def create_sliding_windows(data: np.ndarray, window_size: int = 60):
    """
    Create sliding window sequences for time series prediction.
    
    Args:
        data: 2D array of shape (n_samples, n_features) — last column is target
        window_size: Number of timesteps per window
    
    Returns:
        X: Input sequences (n_windows, window_size, n_features-1)
        y: Target values (n_windows,)
    """
    X, y = [], []
    for i in range(window_size, len(data)):
        X.append(data[i - window_size:i, :-1])  # Features
        y.append(data[i, -1])                    # Target (last column)
    return np.array(X), np.array(y)


# ─── Timestamp Utility ─────────────────────────────────────────
def get_timestamp() -> str:
    """Return formatted timestamp string."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ─── Print Banner ──────────────────────────────────────────────
def print_banner():
    """Print the SAHF project banner."""
    banner = """
    ==============================================================
    |     SAHF - Self-Adaptive Homomorphic Framework             |
    |     ML-Based Noise Prediction for Confidential AI          |
    |     -----------------------------------------------        |
    |     TRL 4-5 | CKKS Scheme | LSTM Predictor                 |
    ==============================================================
    """
    print(banner)


if __name__ == "__main__":
    print_banner()
    logger.info("Utility module loaded successfully")
    
    # Test noise model
    noise = 0.1
    for i in range(5):
        noise = noise_growth_model(noise, "multiply", depth=i+1, scale=2**30)
        logger.info(f"Step {i+1}: noise = {noise:.6f}")
