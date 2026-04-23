"""
SAHF - ML Model Module
========================
LSTM-based noise prediction model for FHE noise forecasting.
Handles model building, training, evaluation, and inference.

Architecture:
    LSTM(64, return_sequences=True) → Dropout(0.2) → LSTM(32) →
    Dense(16, relu) → Dense(1)

Target: MAE < 0.05
"""

import os
import sys
import numpy as np
import pandas as pd
from typing import Tuple, Dict, Optional

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        # In Jupyter and some environments, reconfigure() is not available
        pass

from .utils import logger, timer, create_sliding_windows, save_metrics

# TensorFlow / Keras imports
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'  # Suppress TF info logs
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import LSTM, Dense, Dropout, Input
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau, ModelCheckpoint
from tensorflow.keras.losses import Huber
from sklearn.preprocessing import MinMaxScaler


# ─── Model Builder ─────────────────────────────────────────────
def build_lstm_model(input_shape: Tuple[int, int], 
                     learning_rate: float = 0.001) -> Sequential:
    """
    Build the LSTM noise prediction model.
    
    Architecture:
        Input → LSTM(64, return_seq=True) → Dropout(0.2) →
        LSTM(32) → Dense(16, relu) → Dense(1)
    
    Args:
        input_shape: (window_size, num_features) tuple
        learning_rate: Adam optimizer learning rate
    
    Returns:
        Compiled Keras Sequential model
    """
    model = Sequential([
        Input(shape=input_shape),
        LSTM(64, return_sequences=True, name="lstm_encoder_1"),
        Dropout(0.2, name="dropout_1"),
        LSTM(32, name="lstm_encoder_2"),
        Dense(16, activation='relu', name="dense_hidden"),
        Dense(1, name="output")
    ], name="SAHF_NoisePredictor")
    
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=learning_rate),
        loss=Huber(delta=1.0),
        metrics=['mae']
    )
    
    logger.info(f"[MODEL] LSTM Model built | input_shape={input_shape}")
    logger.info(f"   Parameters: {model.count_params():,}")
    
    return model


# ─── Data Preprocessor ─────────────────────────────────────────
class DataPreprocessor:
    """
    Handles all data preprocessing for the LSTM model:
    - MinMaxScaler normalization
    - Sliding window creation
    - Train/Validation/Test splitting
    """
    
    def __init__(self, window_size: int = 60):
        """
        Args:
            window_size: Number of timesteps per prediction window
        """
        self.window_size = window_size
        self.feature_scaler = MinMaxScaler()
        self.target_scaler = MinMaxScaler()
        self.feature_columns = None
        self.target_column = "next_noise"
        
    @timer
    def prepare_data(self, df: pd.DataFrame, 
                     feature_cols: list = None,
                     train_ratio: float = 0.70,
                     val_ratio: float = 0.15) -> Dict:
        """
        Full preprocessing pipeline: normalize → window → split.
        
        Args:
            df: Raw dataset DataFrame
            feature_cols: List of feature column names. If None, auto-detect.
            train_ratio: Fraction of data for training
            val_ratio: Fraction for validation (remainder = test)
        
        Returns:
            Dictionary with X_train, y_train, X_val, y_val, X_test, y_test
        """
        if feature_cols is None:
            feature_cols = ["op_type", "depth", "scale", "delta_noise", 
                           "noise_ratio", "since_last_reset", "noise"]
        
        self.feature_columns = feature_cols
        
        # Select features and target
        features = df[feature_cols].values
        target = df[self.target_column].values.reshape(-1, 1)
        
        # Normalize
        features_scaled = self.feature_scaler.fit_transform(features)
        target_scaled = self.target_scaler.fit_transform(target)
        
        # Combine for windowing (features + target as last column)
        combined = np.hstack([features_scaled, target_scaled])
        
        # Create sliding windows
        X, y = create_sliding_windows(combined, window_size=self.window_size)
        
        logger.info(f"[DATA] Windows created: X={X.shape}, y={y.shape}")
        
        # Split into train/val/test (70/15/15)
        n = len(X)
        train_end = int(n * train_ratio)
        val_end = int(n * (train_ratio + val_ratio))
        
        data = {
            "X_train": X[:train_end],
            "y_train": y[:train_end],
            "X_val": X[train_end:val_end],
            "y_val": y[train_end:val_end],
            "X_test": X[val_end:],
            "y_test": y[val_end:],
        }
        
        logger.info(f"[DATA] Data split:")
        logger.info(f"   Train: {data['X_train'].shape[0]} samples")
        logger.info(f"   Val:   {data['X_val'].shape[0]} samples")
        logger.info(f"   Test:  {data['X_test'].shape[0]} samples")
        
        return data
    
    def inverse_transform_target(self, scaled_values: np.ndarray) -> np.ndarray:
        """Convert scaled predictions back to original scale."""
        if scaled_values.ndim == 1:
            scaled_values = scaled_values.reshape(-1, 1)
        return self.target_scaler.inverse_transform(scaled_values).flatten()


# ─── Training Pipeline ─────────────────────────────────────────
@timer
def train_model(model: Sequential, 
                data: Dict,
                epochs: int = 100,
                batch_size: int = 32,
                model_save_path: str = "models/lstm_model.keras") -> Dict:
    """
    Train the LSTM model with callbacks.
    
    Args:
        model: Compiled Keras model
        data: Dictionary from DataPreprocessor.prepare_data()
        epochs: Maximum training epochs
        batch_size: Training batch size
        model_save_path: Path to save best model
    
    Returns:
        Dictionary with training history and final metrics
    """
    os.makedirs(os.path.dirname(model_save_path), exist_ok=True)
    
    # Callbacks
    callbacks = [
        EarlyStopping(
            monitor='val_mae',
            patience=15,
            restore_best_weights=True,
            verbose=1
        ),
        ReduceLROnPlateau(
            monitor='val_loss',
            factor=0.5,
            patience=7,
            min_lr=1e-6,
            verbose=1
        ),
        ModelCheckpoint(
            filepath=model_save_path,
            monitor='val_mae',
            save_best_only=True,
            verbose=1
        )
    ]
    
    logger.info(f"[TRAIN] Training started | epochs={epochs}, batch_size={batch_size}")
    
    history = model.fit(
        data["X_train"], data["y_train"],
        validation_data=(data["X_val"], data["y_val"]),
        epochs=epochs,
        batch_size=batch_size,
        callbacks=callbacks,
        verbose=1
    )
    
    # Evaluate on test set
    test_loss, test_mae = model.evaluate(
        data["X_test"], data["y_test"], verbose=0
    )
    
    logger.info(f"[OK] Training complete!")
    logger.info(f"   Test Loss: {test_loss:.6f}")
    logger.info(f"   Test MAE:  {test_mae:.6f}")
    
    if test_mae < 0.05:
        logger.info(f"   [TARGET MET] MAE ({test_mae:.4f}) < 0.05")
    else:
        logger.warning(f"   [TARGET NOT MET] MAE ({test_mae:.4f}) >= 0.05")
    
    results = {
        "train_loss": float(history.history['loss'][-1]),
        "train_mae": float(history.history['mae'][-1]),
        "val_loss": float(history.history['val_loss'][-1]),
        "val_mae": float(history.history['val_mae'][-1]),
        "test_loss": float(test_loss),
        "test_mae": float(test_mae),
        "epochs_trained": len(history.history['loss']),
        "model_path": model_save_path,
        "history": {
            "loss": [float(x) for x in history.history['loss']],
            "mae": [float(x) for x in history.history['mae']],
            "val_loss": [float(x) for x in history.history['val_loss']],
            "val_mae": [float(x) for x in history.history['val_mae']]
        }
    }
    
    return results


# ─── Prediction Engine ─────────────────────────────────────────
class NoisePredictor:
    """
    Wraps the trained LSTM model for real-time noise prediction.
    Maintains a sliding window buffer for inference.
    """
    
    def __init__(self, model_path: str = "models/lstm_model.keras",
                 preprocessor: DataPreprocessor = None):
        """
        Args:
            model_path: Path to trained Keras model
            preprocessor: DataPreprocessor with fitted scalers
        """
        self.model = None
        self.preprocessor = preprocessor
        self.model_path = model_path
        self.buffer = []
        self.window_size = preprocessor.window_size if preprocessor else 60
        
        self._load_model()
    
    def _load_model(self):
        """Load the trained LSTM model."""
        if os.path.exists(self.model_path):
            self.model = load_model(self.model_path)
            logger.info(f"[MODEL] Model loaded from {self.model_path}")
        else:
            logger.warning(f"[WARN] Model not found at {self.model_path}")
    
    def predict(self, feature_vector: np.ndarray) -> float:
        """
        Make a single noise prediction.
        Adds the feature vector to buffer and predicts when window is full.
        
        Args:
            feature_vector: Single timestep features (1D array)
        
        Returns:
            Predicted next noise level (or -1 if insufficient data)
        """
        if self.model is None:
            logger.warning("[WARN] No model loaded - cannot predict")
            return -1.0
        
        # Scale features
        if self.preprocessor:
            scaled = self.preprocessor.feature_scaler.transform(
                feature_vector.reshape(1, -1)
            ).flatten()
        else:
            scaled = feature_vector
        
        self.buffer.append(scaled)
        
        if len(self.buffer) < self.window_size:
            return -1.0  # Not enough data yet
        
        # Keep only the latest window
        window = np.array(self.buffer[-self.window_size:])
        X = window.reshape(1, self.window_size, -1)
        
        # Predict
        pred_scaled = self.model.predict(X, verbose=0)[0, 0]
        
        # Inverse transform
        if self.preprocessor:
            pred = self.preprocessor.inverse_transform_target(
                np.array([pred_scaled])
            )[0]
        else:
            pred = pred_scaled
        
        return float(np.clip(pred, 0.0, 1.0))
    
    def predict_batch(self, X: np.ndarray) -> np.ndarray:
        """
        Batch prediction on windowed data.
        
        Args:
            X: Input array of shape (n_samples, window_size, n_features)
        
        Returns:
            Array of predictions
        """
        if self.model is None:
            return np.zeros(len(X))
        
        predictions = self.model.predict(X, verbose=0).flatten()
        
        if self.preprocessor:
            predictions = self.preprocessor.inverse_transform_target(predictions)
        
        return np.clip(predictions, 0.0, 1.0)
    
    def reset_buffer(self):
        """Clear the prediction buffer."""
        self.buffer = []


# ─── Main Entry Point ─────────────────────────────────────────
if __name__ == "__main__":
    from utils import print_banner
    print_banner()
    
    # Demo: build and show model summary
    model = build_lstm_model(input_shape=(60, 7))
    model.summary()
