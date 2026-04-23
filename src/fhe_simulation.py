"""
SAHF - FHE Simulation Engine
==============================
Implements Fully Homomorphic Encryption operations using TenSEAL (CKKS scheme).
Provides both real FHE operations + noise proxy tracking for dataset generation.

Key Features:
- CKKS context creation (poly_modulus_degree=8192)
- Vector encryption/decryption
- Homomorphic addition and multiplication
- Noise proxy tracking (depth, scale, multiplications)
- Dataset generation from actual FHE operations
"""

import numpy as np
import pandas as pd
import time
from typing import List, Tuple, Dict, Optional

# Try to import tenseal; fall back to simulation if unavailable
import sys
if sys.platform == 'win32':
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass

try:
    import tenseal as ts
    TENSEAL_AVAILABLE = True
except ImportError:
    TENSEAL_AVAILABLE = False

from .utils import logger, timer, compute_noise_proxy, noise_growth_model


# ─── CKKS Context Manager ─────────────────────────────────────
class CKKSContextManager:
    """
    Manages TenSEAL CKKS encryption context and operations.
    Tracks noise proxies for each operation performed.
    """
    
    def __init__(self, poly_modulus_degree: int = 8192, 
                 coeff_mod_bit_sizes: List[int] = None,
                 global_scale: float = 2**40):
        """
        Initialize CKKS encryption context.
        
        Args:
            poly_modulus_degree: Ring polynomial degree (security parameter)
            coeff_mod_bit_sizes: Coefficient modulus chain bit sizes
            global_scale: Encoding precision scale factor
        """
        self.poly_modulus_degree = poly_modulus_degree
        self.global_scale = global_scale
        
        if coeff_mod_bit_sizes is None:
            # Default chain for depth-3 computations
            coeff_mod_bit_sizes = [60, 40, 40, 60]
        
        self.coeff_mod_bit_sizes = coeff_mod_bit_sizes
        
        # Telemetry state
        self.depth = 0
        self.num_additions = 0
        self.num_multiplications = 0
        self.noise_estimate = 0.01  # Initial noise floor
        self.scale_history = [global_scale]
        self.operation_log = []
        self.step_counter = 0
        self.since_last_reset = 0
        
        # Create TenSEAL context
        self._create_context()
        
        logger.info(f"[FHE] CKKS Context initialized | poly_degree={poly_modulus_degree}")
    
    def _create_context(self):
        """Create the TenSEAL CKKS context."""
        if TENSEAL_AVAILABLE:
            self.context = ts.context(
                ts.SCHEME_TYPE.CKKS,
                poly_modulus_degree=self.poly_modulus_degree,
                coeff_mod_bit_sizes=self.coeff_mod_bit_sizes
            )
            self.context.generate_galois_keys()
            self.context.global_scale = self.global_scale
            logger.info("[OK] TenSEAL CKKS context created successfully")
        else:
            self.context = None
            logger.warning("[WARN] TenSEAL not available - using simulation mode")
    
    def encrypt_vector(self, data: List[float]) -> object:
        """
        Encrypt a plain vector using CKKS scheme.
        
        Args:
            data: List of float values to encrypt
        
        Returns:
            Encrypted CKKS vector (or simulated object)
        """
        if TENSEAL_AVAILABLE and self.context is not None:
            encrypted = ts.ckks_vector(self.context, data)
            return encrypted
        else:
            # Simulation: return wrapped numpy array
            return _SimulatedCiphertext(np.array(data))
    
    def decrypt_vector(self, encrypted_vec) -> List[float]:
        """
        Decrypt a CKKS encrypted vector.
        
        Args:
            encrypted_vec: Encrypted vector to decrypt
        
        Returns:
            Decrypted list of float values
        """
        if TENSEAL_AVAILABLE and hasattr(encrypted_vec, 'decrypt'):
            return encrypted_vec.decrypt()
        elif isinstance(encrypted_vec, _SimulatedCiphertext):
            # Add noise proportional to current noise estimate
            noise = np.random.normal(0, self.noise_estimate * 0.01, 
                                     len(encrypted_vec.data))
            return list(encrypted_vec.data + noise)
        return list(encrypted_vec)
    
    def homomorphic_add(self, ct_a, ct_b):
        """
        Perform homomorphic addition: ct_a + ct_b.
        Addition introduces minimal noise growth.
        
        Args:
            ct_a: First ciphertext
            ct_b: Second ciphertext
        
        Returns:
            Result ciphertext
        """
        start_time = time.perf_counter()
        
        if TENSEAL_AVAILABLE and hasattr(ct_a, '__add__'):
            result = ct_a + ct_b
        elif isinstance(ct_a, _SimulatedCiphertext):
            result = _SimulatedCiphertext(ct_a.data + ct_b.data)
        else:
            result = ct_a
        
        elapsed = time.perf_counter() - start_time
        
        # Update telemetry
        self.num_additions += 1
        self.step_counter += 1
        self.since_last_reset += 1
        
        # Noise growth for addition is minimal
        old_noise = self.noise_estimate
        self.noise_estimate = noise_growth_model(
            self.noise_estimate, "add", self.depth, self.global_scale
        )
        
        delta_noise = self.noise_estimate - old_noise
        
        self._log_operation("add", elapsed, delta_noise)
        
        return result
    
    def homomorphic_multiply(self, ct_a, ct_b):
        """
        Perform homomorphic multiplication: ct_a × ct_b.
        Multiplication causes significant noise growth and depth increase.
        
        Args:
            ct_a: First ciphertext
            ct_b: Second ciphertext
        
        Returns:
            Result ciphertext
        """
        start_time = time.perf_counter()
        
        if TENSEAL_AVAILABLE and hasattr(ct_a, '__mul__'):
            result = ct_a * ct_b
        elif isinstance(ct_a, _SimulatedCiphertext):
            result = _SimulatedCiphertext(ct_a.data * ct_b.data)
        else:
            result = ct_a
        
        elapsed = time.perf_counter() - start_time
        
        # Update telemetry — multiplication is expensive
        self.num_multiplications += 1
        self.depth += 1
        self.step_counter += 1
        self.since_last_reset += 1
        self.scale_history.append(self.global_scale * (self.depth + 1))
        
        # Significant noise growth
        old_noise = self.noise_estimate
        self.noise_estimate = noise_growth_model(
            self.noise_estimate, "multiply", self.depth, self.global_scale
        )
        
        delta_noise = self.noise_estimate - old_noise
        
        self._log_operation("multiply", elapsed, delta_noise)
        
        return result
    
    def bootstrap(self, mode: str = "full"):
        """
        Simulate bootstrapping to reset/reduce noise.
        
        Args:
            mode: 'full' resets noise completely, 'partial' reduces by 50%
        """
        start_time = time.perf_counter()
        
        if mode == "full":
            # Full bootstrap: reset all noise state
            self.noise_estimate = 0.01
            self.depth = 0
            self.num_multiplications = 0
            self.num_additions = 0
            self.since_last_reset = 0
            self.scale_history = [self.global_scale]
            bootstrap_cost = np.random.uniform(5.0, 10.0)  # Simulated cost in seconds
            logger.info(f"[BOOTSTRAP] FULL | cost={bootstrap_cost:.2f}s | noise reset to 0.01")
        else:
            # Partial refresh: reduce noise by ~50%
            self.noise_estimate *= 0.5
            self.depth = max(0, self.depth - 1)
            self.since_last_reset = 0
            bootstrap_cost = np.random.uniform(2.0, 5.0)
            logger.info(f"[BOOTSTRAP] PARTIAL | cost={bootstrap_cost:.2f}s | noise -> {self.noise_estimate:.4f}")
        
        elapsed = time.perf_counter() - start_time
        self._log_operation(f"bootstrap_{mode}", elapsed + bootstrap_cost, 0.0)
        
        return bootstrap_cost
    
    def get_telemetry(self) -> Dict:
        """
        Get current FHE state telemetry snapshot.
        
        Returns:
            Dictionary of current state metrics
        """
        return {
            "step": self.step_counter,
            "depth": self.depth,
            "scale": float(self.scale_history[-1]),
            "noise_estimate": float(self.noise_estimate),
            "num_additions": self.num_additions,
            "num_multiplications": self.num_multiplications,
            "since_last_reset": self.since_last_reset,
            "total_operations": self.num_additions + self.num_multiplications
        }
    
    def _log_operation(self, op_type: str, elapsed: float, delta_noise: float):
        """Log an operation to the internal history."""
        self.operation_log.append({
            "step": self.step_counter,
            "op_type": op_type,
            "depth": self.depth,
            "scale": float(self.scale_history[-1]),
            "noise_estimate": float(self.noise_estimate),
            "delta_noise": float(delta_noise),
            "elapsed_ms": float(elapsed * 1000),
            "num_muls": self.num_multiplications,
            "num_adds": self.num_additions,
            "since_last_reset": self.since_last_reset
        })
    
    def reset(self):
        """Full state reset — like creating a fresh context."""
        self.depth = 0
        self.num_additions = 0
        self.num_multiplications = 0
        self.noise_estimate = 0.01
        self.scale_history = [self.global_scale]
        self.operation_log = []
        self.step_counter = 0
        self.since_last_reset = 0
        logger.info("[RESET] FHE Context fully reset")


# ─── Simulated Ciphertext (Fallback when TenSEAL unavailable) ──
class _SimulatedCiphertext:
    """Lightweight ciphertext simulation for environments without TenSEAL."""
    
    def __init__(self, data: np.ndarray):
        self.data = data.copy()
    
    def __add__(self, other):
        if isinstance(other, _SimulatedCiphertext):
            return _SimulatedCiphertext(self.data + other.data)
        return _SimulatedCiphertext(self.data + other)
    
    def __mul__(self, other):
        if isinstance(other, _SimulatedCiphertext):
            return _SimulatedCiphertext(self.data * other.data)
        return _SimulatedCiphertext(self.data * other)
    
    def __len__(self):
        return len(self.data)


# ─── Dataset Generator ────────────────────────────────────────
@timer
def generate_fhe_noise_dataset(num_steps: int = 3000, 
                                save_path: str = "data/fhe_noise_dataset.csv",
                                seed: int = 42) -> pd.DataFrame:
    """
    Generate a realistic FHE noise dataset by performing actual operations.
    
    For each step:
    - Randomly pick an operation (add or multiply)
    - Execute on encrypted vectors via CKKSContextManager
    - Record noise proxy features and target
    
    Args:
        num_steps: Number of operational steps to simulate
        save_path: Path to save the CSV dataset
        seed: Random seed for reproducibility
    
    Returns:
        DataFrame with columns:
            step, op_type, depth, scale, delta_noise, noise_ratio,
            since_last_reset, next_noise
    """
    np.random.seed(seed)
    
    logger.info(f"[DATA] Generating FHE noise dataset with {num_steps} steps...")
    
    ctx = CKKSContextManager()
    
    # Initialize encrypted vectors
    vec_a = ctx.encrypt_vector([1.0, 2.0, 3.0, 4.0])
    vec_b = ctx.encrypt_vector([0.5, 1.5, 2.5, 3.5])
    
    records = []
    
    # Operation weights: multiply is less common but noisier
    op_probs = {"add": 0.55, "multiply": 0.45}
    ops = list(op_probs.keys())
    probs = list(op_probs.values())
    
    for step_i in range(num_steps):
        # Snapshot current state before operation
        pre_noise = ctx.noise_estimate
        pre_depth = ctx.depth
        pre_scale = ctx.scale_history[-1]
        pre_since_reset = ctx.since_last_reset
        
        # Pick random operation
        op = np.random.choice(ops, p=probs)
        
        if op == "add":
            try:
                vec_a = ctx.homomorphic_add(vec_a, vec_b)
            except Exception:
                vec_a = ctx.encrypt_vector([1.0, 2.0, 3.0, 4.0])
                vec_b = ctx.encrypt_vector([0.5, 1.5, 2.5, 3.5])
                ctx.homomorphic_add(vec_a, vec_b)
        else:
            try:
                vec_a = ctx.homomorphic_multiply(vec_a, vec_b)
            except Exception:
                # Re-encrypt if operation fails (depth exceeded)
                ctx.bootstrap(mode="full")
                vec_a = ctx.encrypt_vector([1.0, 2.0, 3.0, 4.0])
                vec_b = ctx.encrypt_vector([0.5, 1.5, 2.5, 3.5])
                ctx.homomorphic_multiply(vec_a, vec_b)
        
        # Post-operation noise
        post_noise = ctx.noise_estimate
        delta_noise = post_noise - pre_noise
        noise_ratio = post_noise / max(pre_noise, 1e-10)
        
        record = {
            "step": step_i,
            "op_type": 1 if op == "multiply" else 0,  # Encoded
            "depth": pre_depth,
            "scale": pre_scale / 1e12,  # Normalize large scale values
            "delta_noise": delta_noise,
            "noise_ratio": min(noise_ratio, 10.0),  # Cap extreme ratios
            "since_last_reset": pre_since_reset,
            "noise": post_noise
        }
        records.append(record)
        
        # Auto-reset if noise exceeds critical threshold (keep dataset diverse)
        if ctx.noise_estimate > 0.95:
            ctx.bootstrap(mode="full")
            vec_a = ctx.encrypt_vector([1.0, 2.0, 3.0, 4.0])
            vec_b = ctx.encrypt_vector([0.5, 1.5, 2.5, 3.5])
        
        # Progress reporting
        if (step_i + 1) % 500 == 0:
            logger.info(f"  Step {step_i + 1}/{num_steps} | noise={post_noise:.4f}")
    
    # Create DataFrame and add target column (next_noise)
    df = pd.DataFrame(records)
    df["next_noise"] = df["noise"].shift(-1)
    df = df.dropna().reset_index(drop=True)
    
    # Save to CSV
    import os
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    df.to_csv(save_path, index=False)
    
    logger.info(f"[OK] Dataset generated: {len(df)} samples saved to {save_path}")
    logger.info(f"   Features: {list(df.columns)}")
    logger.info(f"   Noise range: [{df['noise'].min():.4f}, {df['noise'].max():.4f}]")
    
    return df


# ─── Main Entry Point ─────────────────────────────────────────
if __name__ == "__main__":
    from utils import print_banner
    print_banner()
    
    # Demo: create context and perform operations
    ctx = CKKSContextManager()
    
    a = ctx.encrypt_vector([1.0, 2.0, 3.0])
    b = ctx.encrypt_vector([4.0, 5.0, 6.0])
    
    # Addition
    c = ctx.homomorphic_add(a, b)
    result = ctx.decrypt_vector(c)
    print(f"Addition result: {[round(x, 4) for x in result]}")
    print(f"Telemetry: {ctx.get_telemetry()}")
    
    # Multiplication
    d = ctx.homomorphic_multiply(a, b)
    result = ctx.decrypt_vector(d)
    print(f"Multiplication result: {[round(x, 4) for x in result]}")
    print(f"Telemetry: {ctx.get_telemetry()}")
    
    # Generate dataset
    df = generate_fhe_noise_dataset(num_steps=3000, save_path="data/fhe_noise_dataset.csv")
    print(f"\nDataset shape: {df.shape}")
    print(df.describe())
