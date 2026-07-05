# Google Colab Training Guide

> Step-by-step instructions for running the Meridian Sentinel training notebooks in Google Colab, downloading the outputs, and placing them in the correct local directories before committing.

---

## Overview

The three notebooks are designed to run in Google Colab (free tier), not locally. They require GPU access for training and use Google Drive to persist large files between sessions.

| Notebook | Purpose | Run time | GPU needed |
|----------|---------|----------|-----------|
| `01_data_pipeline.ipynb` | EDA + feature engineering | ~15 min | No |
| `02_lstm_model.ipynb` | LSTM training | ~35 min (20 epochs) | Yes (T4) |
| `03_evaluation.ipynb` | Evaluation + ONNX export | ~5 min | No |

Run them in order. Notebook 03 depends on the model files produced by notebook 02.

---

## Prerequisites

- A Google account with access to Google Drive
- The repository cloned locally (so you can place downloaded files)
- Docker Desktop running (for serving the model after training)

---

## Step 1 — Open a Notebook in Colab

1. Go to [https://colab.research.google.com](https://colab.research.google.com)
2. Click **File → Open notebook**
3. Select the **GitHub** tab
4. Enter the repository URL:
   ```
   https://github.com/owenz4040/Meridaian
   ```
5. Select the branch (e.g. `feature/day6-docker-stack` or `main`)
6. Click the notebook you want to open

---

## Step 2 — Enable GPU (for notebook 02 only)

Before running notebook 02:

1. Click **Runtime → Change runtime type**
2. Set **Hardware accelerator** to **GPU**
3. Click **Save**

You do not need GPU for notebooks 01 or 03.

---

## Step 3 — Mount Google Drive

Every notebook includes a Drive mount cell near the top. Run it when prompted:

```python
from google.colab import drive
drive.mount('/content/drive')
```

A browser popup will ask you to authorise Drive access. Accept it. After mounting you will see:

```
Mounted at /content/drive
```

The notebooks save large files (checkpoints, processed data) to Drive automatically so they survive if your Colab session disconnects.

---

## Step 4 — Running Notebook 01 (`01_data_pipeline.ipynb`)

**What it does:**
- Downloads the PaySim dataset from Kaggle (6.3M transactions)
- Runs exploratory data analysis
- Builds 5-transaction sliding window sequences
- Engineers all 12 features
- Applies SHA-256 PII hashing on customer IDs
- Saves processed `.npy` arrays to Drive

**What you need before running:**
- Add your Kaggle API credentials to Colab secrets, or upload `kaggle.json` when prompted

**Files saved to Drive:**
```
/content/drive/MyDrive/meridian-sentinel/data/processed/
├── X_train.npy
├── X_val.npy
├── X_test.npy
├── y_train.npy
├── y_val.npy
└── y_test.npy
```

**What to download and where to put it:**

These processed arrays are large (~500 MB total) and are gitignored. You do not need to download them to your local machine unless you are running training locally (not recommended — use Colab).

No files need to be committed from notebook 01.

---

## Step 5 — Running Notebook 02 (`02_lstm_model.ipynb`)

**What it does:**
- Loads the processed sequences from Drive
- Runs a short calibration run (20% data, 5 epochs) to verify the training loop
- Runs full training (100% data, 20 epochs, WeightedRandomSampler, pos_weight=1.0)
- Saves the best checkpoint (highest val_acc epoch) and final checkpoint to Drive
- Saves training curves and history JSON

**Critical cells to check before running:**

Cell 12 — pos_weight must be hardcoded to 1.0:
```python
pos_weight_val = 1.0
```
Do not change this. The `WeightedRandomSampler` already balances the batches. A value > 1.0 will collapse the model.

**Files saved to Drive after training:**
```
/content/drive/MyDrive/meridian-sentinel/
├── models/
│   ├── lstm_checkpoint_best.pt    ← Best epoch checkpoint
│   └── lstm_final.pt              ← Final epoch checkpoint
└── results/
    ├── training_history.json
    ├── calibration_run_01.json
    └── figures/
        └── training_curves.png
```

**Download cell (last cell in notebook 02):**

The notebook's final cell downloads all model files automatically:

```python
from google.colab import files
import os

REPO_DIR = '/content/drive/MyDrive/meridian-sentinel'

to_download = [
    'models/lstm_checkpoint_best.pt',
    'models/lstm_final.pt',
    'results/training_history.json',
    'results/calibration_run_01.json',
    'results/figures/training_curves.png',
]

for path in to_download:
    full = os.path.join(REPO_DIR, path)
    if os.path.exists(full):
        files.download(full)
    else:
        print(f'MISSING: {full}')
```

Run this cell. Your browser will download each file one by one.

**Where to place each downloaded file locally:**

| Downloaded file | Place it at |
|----------------|-------------|
| `lstm_checkpoint_best.pt` | `models/lstm_checkpoint_best.pt` |
| `lstm_final.pt` | `models/lstm_final.pt` |
| `training_history.json` | `results/training_history.json` |
| `calibration_run_01.json` | `results/calibration_run_01.json` |
| `training_curves.png` | `results/figures/training_curves.png` |

**What to commit after placing the files:**

```bash
git add models/lstm_checkpoint_best.pt
git add models/lstm_final.pt
git add results/training_history.json
git add results/calibration_run_01.json
git add results/figures/training_curves.png
git commit -m "Add trained LSTM checkpoint and training results"
git push
```

The `.pt` files are committed because they are the source of truth for model weights. The ONNX file is NOT committed — it is generated at container startup from the `.pt` file.

---

## Step 6 — Running Notebook 03 (`03_evaluation.ipynb`)

**What it does:**
- Loads `lstm_checkpoint_best.pt` from Drive
- Runs inference on the test set at the configured threshold
- Computes accuracy, FPR, recall, TP, TN, FP, FN
- Saves the confusion matrix image and final metrics JSON
- Writes `MODEL_CARD.md`
- Exports the model to ONNX format (Drive only — for reference, not for local use)

**Cell 16 auto-selects the threshold:** it sweeps thresholds from 0.90 upward and picks the lowest one that clears the 98.55% accuracy target, printing the full accuracy/FPR/recall trade-off table. On the current model it selects `0.92`. You do not set the threshold by hand — the sweep decides and `THRESHOLD` flows into the metrics, MODEL_CARD, and confusion matrix downstream.

**Files saved to Drive after evaluation:**
```
/content/drive/MyDrive/meridian-sentinel/
├── results/
│   ├── final_metrics.json
│   └── figures/
│       └── confusion_matrix.png
└── models/
    ├── MODEL_CARD.md
    └── serving/
        └── lstm_v1/
            └── lstm_fraud_detector.onnx   ← Drive copy only (do NOT download this)
```

**Download cell (last cell in notebook 03):**

```python
from google.colab import files
import os

REPO_DIR = '/content/drive/MyDrive/meridian-sentinel'

to_download = [
    'results/final_metrics.json',
    'results/figures/confusion_matrix.png',
    'models/MODEL_CARD.md',
]

for path in to_download:
    full = os.path.join(REPO_DIR, path)
    if os.path.exists(full):
        files.download(full)
    else:
        print(f'MISSING: {full}')
```

**Where to place each downloaded file locally:**

| Downloaded file | Place it at |
|----------------|-------------|
| `final_metrics.json` | `results/final_metrics.json` |
| `confusion_matrix.png` | `results/figures/confusion_matrix.png` |
| `MODEL_CARD.md` | `models/MODEL_CARD.md` |

**Do NOT download or commit `lstm_fraud_detector.onnx` from Drive.** It is binary and unreliable to transfer via Colab download. The serving container generates it automatically from the `.pt` checkpoint.

**What to commit after placing the files:**

```bash
git add results/final_metrics.json
git add results/figures/confusion_matrix.png
git add models/MODEL_CARD.md
git commit -m "Add evaluation results at threshold=0.92"
git push
```

---

## Summary: Files to Download and Where They Go

| Notebook | File to download | Local destination | Commit? |
|----------|-----------------|-------------------|---------|
| 02 | `lstm_checkpoint_best.pt` | `models/lstm_checkpoint_best.pt` | Yes |
| 02 | `lstm_final.pt` | `models/lstm_final.pt` | Yes |
| 02 | `training_history.json` | `results/training_history.json` | Yes |
| 02 | `calibration_run_01.json` | `results/calibration_run_01.json` | Yes |
| 02 | `training_curves.png` | `results/figures/training_curves.png` | Yes |
| 03 | `final_metrics.json` | `results/final_metrics.json` | Yes |
| 03 | `confusion_matrix.png` | `results/figures/confusion_matrix.png` | Yes |
| 03 | `MODEL_CARD.md` | `models/MODEL_CARD.md` | Yes |
| 03 | `lstm_fraud_detector.onnx` | **DO NOT download** | No — generated by Docker |

---

## After Downloading — Regenerate the ONNX Model

Once the new `.pt` checkpoint is in place, regenerate the ONNX file inside the container:

```bash
# Delete the old ONNX file (if any)
# Windows
del models\serving\lstm_v1\lstm_fraud_detector.onnx
# Mac / Linux
rm models/serving/lstm_v1/lstm_fraud_detector.onnx

# Restart the container — it will run convert_to_onnx.py at startup
docker compose restart lstm-serving

# Watch the conversion
docker compose logs lstm-serving -f
```

Expected output:
```
ONNX exported: /models/lstm_fraud_detector.onnx  (482 KB)
INFO: Uvicorn running on http://0.0.0.0:8080
```

Then run the smoke tests to confirm the new model works:
```bash
python -m pytest tests/test_inference_api.py -v
```

---

## Troubleshooting Colab

**Drive not mounted / path not found**

Re-run the Drive mount cell. If it still fails, go to Runtime → Disconnect and delete runtime, then reconnect and run from the top.

**Session disconnected mid-training**

Colab free tier can disconnect after ~90 minutes of inactivity. If the session disconnects:
1. Reconnect
2. Re-mount Drive
3. Re-run the data loading cells (the `.npy` files are still on Drive)
4. Training will start from epoch 1 again — there is no checkpoint resume in the current notebook

**GPU not available**

The free tier GPU is not always available. Try again later, or use Colab Pro. Training without GPU takes ~10× longer but will complete.

**Downloaded file is 8.6 KB (corrupt)**

Do not use the Drive file browser download for the ONNX file — it produces a corrupt file. Use the `files.download()` cell provided in the notebooks for all downloads. If any file downloads as unexpectedly small (< 50 KB for `.pt` files), do not use it — re-run the save cell and download again.
