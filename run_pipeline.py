"""
SAHF - Complete Pipeline Runner
=================================
Executes the entire SAHF pipeline end-to-end:
  1. Generate FHE noise dataset
  2. Preprocess data
  3. Train LSTM model
  4. Run baseline vs adaptive comparison
  5. Generate plots
  6. Save metrics

Usage:
    python run_pipeline.py
"""

import os
import sys
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns

# Project root
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT_DIR)

from src.utils import (
    logger, print_banner, ensure_directories, save_metrics, timer
)
from src.fhe_simulation import CKKSContextManager, generate_fhe_noise_dataset
from src.model import build_lstm_model, DataPreprocessor, train_model, NoisePredictor
from src.decision_engine import (
    AdaptiveDecisionEngine, BaselineSystem, AdaptiveSystem,
    run_comparison, ACTION_CONTINUE, ACTION_PARTIAL, ACTION_FULL
)
from src.telemetry import TelemetryEngine


# ─── Configuration ─────────────────────────────────────────────
CONFIG = {
    "dataset_steps": 3000,
    "window_size": 60,
    "epochs": 100,
    "batch_size": 32,
    "comparison_steps": 500,
    "baseline_interval": 8,
    "seed": 42,
    "paths": {
        "dataset": os.path.join(ROOT_DIR, "data", "fhe_noise_dataset.csv"),
        "model": os.path.join(ROOT_DIR, "models", "lstm_model.keras"),
        "metrics": os.path.join(ROOT_DIR, "results", "metrics.json"),
        "plots": os.path.join(ROOT_DIR, "results", "plots"),
    }
}


# ─── Plot Style ────────────────────────────────────────────────
def setup_plot_style():
    """Configure professional plot styling."""
    plt.style.use('dark_background')
    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.size': 11,
        'axes.titlesize': 14,
        'axes.titleweight': 'bold',
        'axes.labelsize': 12,
        'figure.facecolor': '#0f0c29',
        'axes.facecolor': '#1a1a2e',
        'axes.edgecolor': '#333366',
        'axes.grid': True,
        'grid.alpha': 0.15,
        'grid.color': '#444488',
        'text.color': '#ccccee',
        'xtick.color': '#8888aa',
        'ytick.color': '#8888aa',
        'legend.facecolor': '#1a1a2e',
        'legend.edgecolor': '#333366',
        'figure.dpi': 150,
        'savefig.dpi': 150,
        'savefig.bbox': 'tight',
        'savefig.facecolor': '#0f0c29',
    })


# ═══════════════════════════════════════════════════════════════
# STEP 1: DATASET GENERATION
# ═══════════════════════════════════════════════════════════════
def step1_generate_dataset():
    """Generate FHE noise dataset from actual operations."""
    logger.info("=" * 60)
    logger.info("STEP 1: DATASET GENERATION")
    logger.info("=" * 60)
    
    df = generate_fhe_noise_dataset(
        num_steps=CONFIG["dataset_steps"],
        save_path=CONFIG["paths"]["dataset"],
        seed=CONFIG["seed"]
    )
    
    logger.info(f"\nDataset Summary:")
    logger.info(f"  Shape: {df.shape}")
    logger.info(f"  Columns: {list(df.columns)}")
    logger.info(f"\n{df.describe().to_string()}")
    
    # Plot dataset overview
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.suptitle("FHE Noise Dataset Overview", fontsize=16, color='#a8edea')
    
    # Noise over time
    axes[0, 0].plot(df['noise'], color='#667eea', linewidth=0.8, alpha=0.8)
    axes[0, 0].set_title('Noise Over Time')
    axes[0, 0].set_xlabel('Step')
    axes[0, 0].set_ylabel('Noise Level')
    
    # Next noise distribution
    axes[0, 1].hist(df['next_noise'], bins=50, color='#764ba2', alpha=0.7, edgecolor='none')
    axes[0, 1].set_title('Next Noise Distribution')
    axes[0, 1].set_xlabel('Next Noise')
    axes[0, 1].set_ylabel('Frequency')
    
    # Depth distribution
    axes[0, 2].hist(df['depth'], bins=30, color='#4ade80', alpha=0.7, edgecolor='none')
    axes[0, 2].set_title('Depth Distribution')
    axes[0, 2].set_xlabel('Depth')
    axes[0, 2].set_ylabel('Frequency')
    
    # Delta noise
    axes[1, 0].plot(df['delta_noise'], color='#fbbf24', linewidth=0.5, alpha=0.7)
    axes[1, 0].set_title('Delta Noise Per Step')
    axes[1, 0].set_xlabel('Step')
    axes[1, 0].set_ylabel('Delta')
    
    # Operation type distribution
    op_counts = df['op_type'].value_counts()
    axes[1, 1].bar(['Addition (0)', 'Multiplication (1)'], 
                    [op_counts.get(0, 0), op_counts.get(1, 0)],
                    color=['#4ade80', '#f87171'], alpha=0.8)
    axes[1, 1].set_title('Operation Type Distribution')
    axes[1, 1].set_ylabel('Count')
    
    # Noise vs Depth scatter
    scatter = axes[1, 2].scatter(df['depth'], df['noise'], 
                                  c=df['op_type'], s=3, alpha=0.5,
                                  cmap='coolwarm')
    axes[1, 2].set_title('Noise vs Depth (colored by op)')
    axes[1, 2].set_xlabel('Depth')
    axes[1, 2].set_ylabel('Noise')
    plt.colorbar(scatter, ax=axes[1, 2], label='Op Type')
    
    plt.tight_layout()
    plt.savefig(os.path.join(CONFIG["paths"]["plots"], "01_dataset_overview.png"))
    plt.close()
    
    logger.info("📊 Dataset overview plot saved")
    
    return df


# ═══════════════════════════════════════════════════════════════
# STEP 2: DATA PREPROCESSING
# ═══════════════════════════════════════════════════════════════
def step2_preprocess(df):
    """Preprocess dataset for LSTM training."""
    logger.info("\n" + "=" * 60)
    logger.info("STEP 2: DATA PREPROCESSING")
    logger.info("=" * 60)
    
    preprocessor = DataPreprocessor(window_size=CONFIG["window_size"])
    
    data = preprocessor.prepare_data(df)
    
    logger.info(f"\nPreprocessed shapes:")
    for key, val in data.items():
        logger.info(f"  {key}: {val.shape}")
    
    return data, preprocessor


# ═══════════════════════════════════════════════════════════════
# STEP 3: MODEL TRAINING
# ═══════════════════════════════════════════════════════════════
def step3_train(data, preprocessor):
    """Build and train the LSTM model."""
    logger.info("\n" + "=" * 60)
    logger.info("STEP 3: MODEL TRAINING")
    logger.info("=" * 60)
    
    # Input shape: (window_size, num_features)
    input_shape = (data["X_train"].shape[1], data["X_train"].shape[2])
    
    model = build_lstm_model(input_shape)
    model.summary()
    
    results = train_model(
        model, data,
        epochs=CONFIG["epochs"],
        batch_size=CONFIG["batch_size"],
        model_save_path=CONFIG["paths"]["model"]
    )
    
    # Plot training history
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("LSTM Training History", fontsize=16, color='#a8edea')
    
    # Loss
    axes[0].plot(results["history"]["loss"], label='Train Loss', 
                 color='#667eea', linewidth=2)
    axes[0].plot(results["history"]["val_loss"], label='Val Loss',
                 color='#fbbf24', linewidth=2)
    axes[0].set_title('Loss (Huber)')
    axes[0].set_xlabel('Epoch')
    axes[0].set_ylabel('Loss')
    axes[0].legend()
    
    # MAE
    axes[1].plot(results["history"]["mae"], label='Train MAE',
                 color='#667eea', linewidth=2)
    axes[1].plot(results["history"]["val_mae"], label='Val MAE',
                 color='#fbbf24', linewidth=2)
    axes[1].axhline(y=0.05, color='#4ade80', linestyle='--', alpha=0.7,
                    label='Target MAE (0.05)')
    axes[1].set_title('Mean Absolute Error')
    axes[1].set_xlabel('Epoch')
    axes[1].set_ylabel('MAE')
    axes[1].legend()
    
    plt.tight_layout()
    plt.savefig(os.path.join(CONFIG["paths"]["plots"], "02_training_history.png"))
    plt.close()
    
    logger.info("📊 Training history plot saved")
    
    # Predictions vs Actual on test set
    from tensorflow.keras.models import load_model
    best_model = load_model(CONFIG["paths"]["model"])
    
    test_preds_scaled = best_model.predict(data["X_test"], verbose=0).flatten()
    test_actual_scaled = data["y_test"]
    
    test_preds = preprocessor.inverse_transform_target(test_preds_scaled)
    test_actual = preprocessor.inverse_transform_target(test_actual_scaled)
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Model Predictions vs Actual", fontsize=16, color='#a8edea')
    
    # Time series comparison
    n_show = min(300, len(test_preds))
    axes[0].plot(range(n_show), test_actual[:n_show], label='Actual',
                 color='#4ade80', linewidth=1.5, alpha=0.8)
    axes[0].plot(range(n_show), test_preds[:n_show], label='Predicted',
                 color='#f87171', linewidth=1.5, alpha=0.8)
    axes[0].set_title('Predicted vs Actual Noise')
    axes[0].set_xlabel('Sample')
    axes[0].set_ylabel('Noise Level')
    axes[0].legend()
    
    # Scatter plot
    axes[1].scatter(test_actual, test_preds, alpha=0.3, s=10, color='#667eea')
    lims = [min(test_actual.min(), test_preds.min()), 
            max(test_actual.max(), test_preds.max())]
    axes[1].plot(lims, lims, '--', color='#4ade80', alpha=0.7, label='Perfect')
    axes[1].set_title('Prediction Scatter')
    axes[1].set_xlabel('Actual Noise')
    axes[1].set_ylabel('Predicted Noise')
    axes[1].legend()
    
    plt.tight_layout()
    plt.savefig(os.path.join(CONFIG["paths"]["plots"], "03_predictions_vs_actual.png"))
    plt.close()
    
    logger.info("📊 Predictions plot saved")
    
    # Error distribution
    errors = np.abs(test_preds - test_actual)
    
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(errors, bins=50, color='#764ba2', alpha=0.7, edgecolor='none')
    ax.axvline(x=np.mean(errors), color='#fbbf24', linestyle='--', 
               linewidth=2, label=f'Mean Error: {np.mean(errors):.4f}')
    ax.axvline(x=np.median(errors), color='#4ade80', linestyle='--',
               linewidth=2, label=f'Median Error: {np.median(errors):.4f}')
    ax.set_title('Prediction Error Distribution', fontsize=14, color='#a8edea')
    ax.set_xlabel('Absolute Error')
    ax.set_ylabel('Frequency')
    ax.legend()
    plt.savefig(os.path.join(CONFIG["paths"]["plots"], "04_error_distribution.png"))
    plt.close()
    
    logger.info("📊 Error distribution plot saved")
    
    return results, best_model


# ═══════════════════════════════════════════════════════════════
# STEP 4: BASELINE VS ADAPTIVE COMPARISON
# ═══════════════════════════════════════════════════════════════
def step4_comparison(preprocessor, best_model):
    """Run comparison between baseline and adaptive systems."""
    logger.info("\n" + "=" * 60)
    logger.info("STEP 4: BASELINE VS ADAPTIVE COMPARISON")
    logger.info("=" * 60)
    
    # Create predictor
    predictor = NoisePredictor(
        model_path=CONFIG["paths"]["model"],
        preprocessor=preprocessor
    )
    
    # Run comparison
    comparison = run_comparison(
        num_steps=CONFIG["comparison_steps"],
        baseline_interval=CONFIG["baseline_interval"],
        predictor=predictor,
        seed=CONFIG["seed"]
    )
    
    # ── Plot: Noise Comparison ──────────────────────────────────
    b_noise = comparison["baseline"]["noise_history"]
    a_noise = comparison["adaptive"]["noise_history"]
    a_pred = comparison["adaptive"].get("prediction_history", [])
    b_events = comparison["baseline"]["bootstrap_events"]
    a_events = comparison["adaptive"]["bootstrap_events"]
    
    steps = list(range(len(b_noise)))
    
    fig, axes = plt.subplots(2, 1, figsize=(16, 10), 
                              gridspec_kw={'height_ratios': [3, 1]})
    fig.suptitle("Baseline vs Adaptive: Noise Over Time", 
                 fontsize=16, color='#a8edea')
    
    # Noise comparison
    axes[0].plot(steps, b_noise, label='Baseline Noise',
                 color='#f87171', linewidth=1.2, alpha=0.7)
    axes[0].plot(steps, a_noise, label='Adaptive Noise',
                 color='#4ade80', linewidth=1.5)
    
    if a_pred:
        axes[0].plot(steps[:len(a_pred)], a_pred, label='Predicted Noise',
                     color='#fbbf24', linewidth=1, linestyle=':', alpha=0.6)
    
    # Bootstrap events
    if b_events:
        axes[0].scatter(b_events, [b_noise[min(e, len(b_noise)-1)] for e in b_events],
                        marker='x', s=40, color='#f87171', label='Baseline Bootstrap',
                        zorder=5)
    if a_events:
        axes[0].scatter(a_events, [a_noise[min(e, len(a_noise)-1)] for e in a_events],
                        marker='D', s=40, color='#4ade80', label='Adaptive Bootstrap',
                        zorder=5)
    
    # Thresholds
    axes[0].axhline(y=0.85, color=(0.97, 0.44, 0.44, 0.4), linestyle='--',
                    label='Full Bootstrap (0.85)')
    axes[0].axhline(y=0.50, color=(0.98, 0.75, 0.14, 0.3), linestyle='--',
                    label='Partial Refresh (0.50)')
    
    axes[0].set_ylabel('Noise Level')
    axes[0].legend(loc='upper left', fontsize=9)
    axes[0].set_xlim(0, len(steps))
    
    # Actions timeline
    if "action_history" in comparison["adaptive"]:
        actions = comparison["adaptive"]["action_history"]
        action_map = {ACTION_CONTINUE: 0, ACTION_PARTIAL: 1, ACTION_FULL: 2}
        action_colors_map = {ACTION_CONTINUE: '#4ade80', ACTION_PARTIAL: '#fbbf24', 
                             ACTION_FULL: '#f87171'}
        action_vals = [action_map.get(a, 0) for a in actions]
        colors = [action_colors_map.get(a, '#4ade80') for a in actions]
        
        axes[1].scatter(range(len(action_vals)), action_vals, c=colors, s=5, alpha=0.7)
        axes[1].set_yticks([0, 1, 2])
        axes[1].set_yticklabels(['CONTINUE', 'PARTIAL', 'FULL'])
        axes[1].set_xlabel('Step')
        axes[1].set_ylabel('Action')
        axes[1].set_xlim(0, len(steps))
    
    plt.tight_layout()
    plt.savefig(os.path.join(CONFIG["paths"]["plots"], "05_noise_comparison.png"))
    plt.close()
    
    # ── Plot: Performance Bars ──────────────────────────────────
    imp = comparison["improvement"]
    
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle("Performance Comparison", fontsize=16, color='#a8edea')
    
    # Bootstraps
    bars = axes[0].bar(['Baseline', 'Adaptive'],
                       [imp["baseline_bootstraps"], imp["adaptive_bootstraps"]],
                       color=['#f87171', '#4ade80'], alpha=0.8, width=0.5)
    axes[0].set_title(f'Total Bootstraps\n(↓{imp["bootstrap_reduction_pct"]:.1f}%)')
    axes[0].set_ylabel('Count')
    for bar in bars:
        axes[0].text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.5,
                     f'{int(bar.get_height())}', ha='center', va='bottom',
                     fontweight='bold', color='#e0e0ff')
    
    # Latency
    bars = axes[1].bar(['Baseline', 'Adaptive'],
                       [imp["baseline_latency"], imp["adaptive_latency"]],
                       color=['#f87171', '#4ade80'], alpha=0.8, width=0.5)
    axes[1].set_title(f'Total Latency\n(↓{imp["latency_improvement_pct"]:.1f}%)')
    axes[1].set_ylabel('Seconds')
    for bar in bars:
        axes[1].text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.5,
                     f'{bar.get_height():.1f}s', ha='center', va='bottom',
                     fontweight='bold', color='#e0e0ff')
    
    # Avg Noise
    bars = axes[2].bar(['Baseline', 'Adaptive'],
                       [imp["baseline_avg_noise"], imp["adaptive_avg_noise"]],
                       color=['#f87171', '#4ade80'], alpha=0.8, width=0.5)
    axes[2].set_title('Average Noise Level')
    axes[2].set_ylabel('Noise')
    for bar in bars:
        axes[2].text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.005,
                     f'{bar.get_height():.4f}', ha='center', va='bottom',
                     fontweight='bold', color='#e0e0ff')
    
    plt.tight_layout()
    plt.savefig(os.path.join(CONFIG["paths"]["plots"], "06_performance_comparison.png"))
    plt.close()
    
    logger.info("📊 All comparison plots saved")
    
    return comparison


# ═══════════════════════════════════════════════════════════════
# STEP 5: SAVE ALL METRICS
# ═══════════════════════════════════════════════════════════════
def step5_save_metrics(training_results, comparison):
    """Compile and save all metrics to JSON."""
    logger.info("\n" + "=" * 60)
    logger.info("STEP 5: SAVING METRICS")
    logger.info("=" * 60)
    
    # Clean comparison for JSON serialization
    comp_clean = {
        "improvement": comparison["improvement"],
        "baseline": {
            "total_steps": comparison["baseline"]["total_steps"],
            "total_bootstraps": comparison["baseline"]["total_bootstraps"],
            "total_latency": comparison["baseline"]["total_latency"],
            "avg_noise": comparison["baseline"]["avg_noise"],
            "max_noise": comparison["baseline"]["max_noise"],
        },
        "adaptive": {
            "total_steps": comparison["adaptive"]["total_steps"],
            "total_bootstraps": comparison["adaptive"]["total_bootstraps"],
            "total_latency": comparison["adaptive"]["total_latency"],
            "avg_noise": comparison["adaptive"]["avg_noise"],
            "max_noise": comparison["adaptive"]["max_noise"],
        }
    }
    
    all_metrics = {
        "project": "SAHF - Self-Adaptive Homomorphic Framework",
        "trl_level": "4-5",
        "model": training_results,
        "comparison": comp_clean,
        "config": {
            "dataset_steps": CONFIG["dataset_steps"],
            "window_size": CONFIG["window_size"],
            "epochs": CONFIG["epochs"],
            "batch_size": CONFIG["batch_size"],
            "comparison_steps": CONFIG["comparison_steps"],
            "baseline_interval": CONFIG["baseline_interval"]
        }
    }
    
    save_metrics(all_metrics, CONFIG["paths"]["metrics"])
    
    logger.info(f"\n📋 Final Metrics Summary:")
    logger.info(f"  Model Test MAE:       {training_results['test_mae']:.6f}")
    logger.info(f"  Bootstrap Reduction:  {comparison['improvement']['bootstrap_reduction_pct']:.1f}%")
    logger.info(f"  Latency Improvement:  {comparison['improvement']['latency_improvement_pct']:.1f}%")
    
    return all_metrics


# ═══════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════
@timer
def main():
    """Run the complete SAHF pipeline."""
    print_banner()
    
    # Ensure directories exist
    ensure_directories(ROOT_DIR)
    setup_plot_style()
    
    # Step 1: Generate dataset
    df = step1_generate_dataset()
    
    # Step 2: Preprocess
    data, preprocessor = step2_preprocess(df)
    
    # Step 3: Train model
    training_results, best_model = step3_train(data, preprocessor)
    
    # Step 4: Comparison
    comparison = step4_comparison(preprocessor, best_model)
    
    # Step 5: Save metrics
    all_metrics = step5_save_metrics(training_results, comparison)
    
    # Final summary
    logger.info("\n" + "=" * 60)
    logger.info("🎉 SAHF PIPELINE COMPLETE!")
    logger.info("=" * 60)
    logger.info(f"  Dataset:  {CONFIG['paths']['dataset']}")
    logger.info(f"  Model:    {CONFIG['paths']['model']}")
    logger.info(f"  Metrics:  {CONFIG['paths']['metrics']}")
    logger.info(f"  Plots:    {CONFIG['paths']['plots']}")
    logger.info("")
    logger.info("  Next steps:")
    logger.info("    1. Run dashboard:  streamlit run dashboard/app.py")
    logger.info("    2. Open notebook:  jupyter notebook notebooks/sahf_model.ipynb")
    logger.info("=" * 60)
    
    return all_metrics


if __name__ == "__main__":
    main()
