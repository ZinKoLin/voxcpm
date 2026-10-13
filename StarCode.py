#step 1
%pip install -q voxcpm gradio soundfile numpy

import torch
import gradio

print("✅ Packages installed")
print("GPU Available:", torch.cuda.is_available())
print("Gradio Version:", gradio.__version__)



#### Step 2

from google.colab import drive
drive.mount("/content/drive")

import os
import re
import json
import uuid
import gc
import subprocess
from pathlib import Path
from datetime import datetime

import numpy as np
import torch
import soundfile as sf
import gradio as gr

from voxcpm import VoxCPM

# --------------------------------------
# GOOGLE DRIVE PATHS
# --------------------------------------

BASE_DIR = Path(
    "/content/drive/MyDrive/Channel99_Studio"
)

MODEL_DIR = BASE_DIR / "VoxCPM" / "models"
PRESET_DIR = BASE_DIR / "presets"
OUTPUT_DIR = Path("/content/Channel99_Outputs")

DATABASE_FILE = PRESET_DIR / "presets.json"

PRESET_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Do not overwrite saved voices.
if not DATABASE_FILE.exists():
    DATABASE_FILE.write_text(
        json.dumps(
            {"voices": []},
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

# --------------------------------------
# GPU AND MODEL
# --------------------------------------

if not torch.cuda.is_available():
    raise RuntimeError(
        "GPU မရှိပါ။ Colab Runtime မှာ T4 GPU ရွေးပါ။"
    )

if not MODEL_DIR.is_dir():
    raise FileNotFoundError(
        f"Model Folder မတွေ့ပါ: {MODEL_DIR}"
    )

print("✅ Google Drive Connected")
print("✅ Preset Database Ready")
print("GPU:", torch.cuda.get_device_name(0))
print("⏳ Loading VoxCPM Model...")

model = VoxCPM.from_pretrained(
    str(MODEL_DIR),
    load_denoiser=False
)

SAMPLE_RATE = model.tts_model.sample_rate

print("✅ VoxCPM Model Loaded Successfully")
print("Sample Rate:", SAMPLE_RATE)
print("Database:", DATABASE_FILE)
