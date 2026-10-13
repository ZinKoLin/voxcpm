
# ==================================================
# CHANNEL 99 AI STUDIO — VERSION 3.1
# Persistent Presets + Temporary Output Storage
# Keep Latest 5 WAV Files Only
# ==================================================

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

# ==================================================
# 1. CONFIGURATION
# ==================================================

# Cell 2 must run first
if "model" not in globals():
    raise RuntimeError(
        "Model မရှိသေးပါ။ Cell 2 ကို အရင် Run ပါ။"
    )

BASE_DIR = Path(
    "/content/drive/MyDrive/Channel99_Studio"
)

PRESET_DIR = BASE_DIR / "presets"
DATABASE_FILE = PRESET_DIR / "presets.json"

# Generated outputs stay in Colab only
OUTPUT_DIR = Path("/content/Channel99_Outputs")

PRESET_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SAMPLE_RATE = model.tts_model.sample_rate

MAX_OUTPUT_FILES = 5

if not DATABASE_FILE.exists():
    DATABASE_FILE.write_text(
        json.dumps(
            {"voices": []},
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

print("✅ Configuration Ready")
print("📁 Presets:", PRESET_DIR)
print("📁 Temporary Outputs:", OUTPUT_DIR)
print("🎧 Sample Rate:", SAMPLE_RATE)


# ==================================================
# 2. OUTPUT AUTO CLEANUP
# ==================================================

def cleanup_old_outputs(keep=MAX_OUTPUT_FILES):
    """
    Keep the latest 5 WAV files.
    Delete older generated WAV files automatically.
    """

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    wav_files = sorted(
        OUTPUT_DIR.glob("*.wav"),
        key=lambda p: p.stat().st_mtime_ns,
        reverse=True
    )

    for old_file in wav_files[keep:]:
        try:
            old_file.unlink()
            print(
                "🗑️ Old output deleted:",
                old_file.name
            )
        except OSError as e:
            print(
                "⚠️ Cleanup failed:",
                old_file.name,
                e
            )

    remaining = len(
        list(OUTPUT_DIR.glob("*.wav"))
    )

    print(
        f"✅ Output cleanup complete: "
        f"{remaining} WAV file(s) remain"
    )


# Clean old temporary outputs on startup
cleanup_old_outputs()


# ==================================================
# 3. PRESET DATABASE
# ==================================================

def load_database():
    try:
        with open(
            DATABASE_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            db = json.load(f)

        if not isinstance(db, dict):
            raise ValueError("Invalid database")

        if not isinstance(db.get("voices"), list):
            raise ValueError("Invalid voice list")

        return db

    except Exception as e:
        raise gr.Error(
            f"Preset Database Error: {e}"
        )


def save_database(db):
    temporary = DATABASE_FILE.with_suffix(".tmp")

    with open(
        temporary,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            db,
            f,
            ensure_ascii=False,
            indent=2
        )

    os.replace(
        temporary,
        DATABASE_FILE
    )


def get_choices():
    db = load_database()

    return [
        (voice["name"], voice["id"])
        for voice in db["voices"]
    ]


def find_voice(voice_id):
    db = load_database()

    for voice in db["voices"]:
        if voice["id"] == voice_id:
            return voice

    return None


def get_voice_path(record):
    filename = Path(
        record["audio_file"]
    ).name

    return PRESET_DIR / filename


# ==================================================
# 4. AUDIO FILE PROCESSING
# ==================================================

def prepare_audio(source, destination):

    if not source:
        raise gr.Error(
            "Audio ဖိုင် Upload လုပ်ပါ။"
        )

    if not os.path.isfile(str(source)):
        raise gr.Error(
            "Upload လုပ်ထားတဲ့ Audio မတွေ့ပါ။"
        )

    command = [
        "ffmpeg",
        "-y",
        "-loglevel", "error",
        "-i", str(source),
        "-vn",
        "-ac", "1",
        "-ar", "24000",
        "-c:a", "pcm_s16le",
        str(destination)
    ]

    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=90
        )

        info = sf.info(str(destination))

        if info.frames <= 0:
            raise ValueError(
                "Empty audio file"
            )

        if not 2 <= info.duration <= 120:
            raise ValueError(
                "Audio must be 2–120 seconds."
            )

    except Exception as e:
        destination.unlink(
            missing_ok=True
        )

        raise gr.Error(
            f"Audio Processing Error: {e}"
        )

    return str(destination)


# ==================================================
# 5. SAVE PRESET VOICE
# ==================================================

def add_voice(name, audio, transcript):

    name = (name or "").strip()
    transcript = (transcript or "").strip()

    if not name:
        raise gr.Error(
            "Voice Name ထည့်ပါ။"
        )

    if len(name) > 80:
        raise gr.Error(
            "Voice Name အရမ်းရှည်နေပါတယ်။"
        )

    if not audio:
        raise gr.Error(
            "Reference Audio Upload လုပ်ပါ။"
        )

    db = load_database()

    if any(
        v["name"] == name
        for v in db["voices"]
    ):
        raise gr.Error(
            "ဒီနာမည်နဲ့ Preset ရှိပြီးသားပါ။"
        )

    voice_id = uuid.uuid4().hex

    destination = (
        PRESET_DIR / f"{voice_id}.wav"
    )

    prepare_audio(
        audio,
        destination
    )

    record = {
        "id": voice_id,
        "name": name,
        "audio_file": destination.name,
        "prompt_text": transcript,
        "created_at": datetime.now().isoformat()
    }

    db["voices"].append(record)

    try:
        save_database(db)

    except Exception:
        destination.unlink(missing_ok=True)
        raise

    return (
        gr.update(
            choices=get_choices(),
            value=voice_id
        ),
        f"✅ {name} ကို Google Drive မှာ သိမ်းပြီးပါပြီ။",
        "",
        None,
        ""
    )


# ==================================================
# 6. DELETE PRESET VOICE
# ==================================================

def delete_voice(voice_id):

    record = find_voice(voice_id)

    if record is None:
        raise gr.Error(
            "ဖျက်မယ့် Preset Voice ရွေးပါ။"
        )

    db = load_database()

    db["voices"] = [
        v for v in db["voices"]
        if v["id"] != voice_id
    ]

    save_database(db)

    audio_path = get_voice_path(record)

    audio_path.unlink(
        missing_ok=True
    )

    choices = get_choices()

    next_voice = (
        choices[0][1]
        if choices else None
    )

    return (
        gr.update(
            choices=choices,
            value=next_voice
        ),
        f"🗑️ {record['name']} ကို ဖျက်ပြီးပါပြီ။"
    )


def refresh_voices():

    choices = get_choices()

    selected = (
        choices[0][1]
        if choices else None
    )

    return gr.update(
        choices=choices,
        value=selected
    )


# ==================================================
# 7. TEXT PROCESSING
# ==================================================

def split_text(text):

    text = (text or "").strip()

    if not text:
        raise gr.Error(
            "ဖတ်ခိုင်းမယ့် စာသား ထည့်ပါ။"
        )

    sentences = re.split(
        r"(?<=[။.!?])\s*|\n+",
        text
    )

    chunks = []

    for sentence in sentences:

        sentence = sentence.strip()

        if not sentence:
            continue

        while len(sentence) > 120:

            cut = sentence.rfind(
                " ", 0, 120
            )

            if cut < 40:
                cut = 120

            piece = sentence[:cut].strip()

            if piece:
                chunks.append(piece)

            sentence = sentence[cut:].strip()

        if sentence:
            chunks.append(sentence)

    if not chunks:
        raise gr.Error(
            "စာသားမရှိပါ။"
        )

    return chunks


def clean_memory():

    gc.collect()

    if torch.cuda.is_available():
        torch.cuda.empty_cache()


# ==================================================
# 8. MAIN AUDIO GENERATION ENGINE
# ==================================================

def generate_engine(
    text,
    audio_path=None,
    transcript=None,
    mode="Reference Only",
    style=None,
    prefix="audio"
):

    chunks = split_text(text)

    # Generation parameters
    kwargs = {
        "cfg_value": 2.0,
        "inference_timesteps": 15,
        "retry_badcase": True,
        "max_len": 2000
    }

    # --------------------------------------
    # REFERENCE VOICE CONFIGURATION
    # --------------------------------------

    if audio_path:

        if not os.path.isfile(str(audio_path)):
            raise gr.Error(
                "Reference Audio မတွေ့ပါ။"
            )

        kwargs["reference_wav_path"] = str(
            audio_path
        )

        # Hi-Fi mode requires transcript
        if mode == "Hi-Fi (Transcript)":

            if not (transcript or "").strip():
                raise gr.Error(
                    "Hi-Fi Mode အတွက် "
                    "Reference Transcript လိုပါတယ်။"
                )

            kwargs["prompt_wav_path"] = str(
                audio_path
            )

            kwargs["prompt_text"] = (
                transcript.strip()
            )

    # --------------------------------------
    # GENERATE AUDIO CHUNKS
    # --------------------------------------

    waves = []

    pause = np.zeros(
        int(SAMPLE_RATE * 0.18),
        dtype=np.float32
    )

    try:

        for index, chunk in enumerate(chunks):

            spoken_text = chunk

            if style and style.strip():
                spoken_text = (
                    f"({style.strip()}){chunk}"
                )

            print(
                f"🎙️ Generating "
                f"{index + 1}/{len(chunks)}:",
                chunk[:60]
            )

            with torch.inference_mode():

                wav = model.generate(
                    text=spoken_text,
                    **kwargs
                )

            wav = np.asarray(
                wav,
                dtype=np.float32
            ).reshape(-1)

            if wav.size == 0:
                raise ValueError(
                    "Model returned empty audio."
                )

            if not np.isfinite(wav).all():
                raise ValueError(
                    "Invalid audio values generated."
                )

            waves.append(wav)

            if index < len(chunks) - 1:
                waves.append(pause)

            clean_memory()

        # ----------------------------------
        # MERGE AUDIO CHUNKS
        # ----------------------------------

        final_audio = np.concatenate(waves)

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )

        filename = (
            f"{prefix}_{timestamp}.wav"
        )

        output_path = (
            OUTPUT_DIR / filename
        )

        # Save in Colab temporary storage
        sf.write(
            str(output_path),
            final_audio,
            SAMPLE_RATE
        )

        # ----------------------------------
        # AUTO DELETE OLD OUTPUTS
        # ----------------------------------

        cleanup_old_outputs(
            keep=MAX_OUTPUT_FILES
        )

        duration = (
            len(final_audio) / SAMPLE_RATE
        )

        status = (
            "✅ Voice Generated Successfully\n"
            f"Duration: {duration:.1f} seconds\n"
            f"Chunks: {len(chunks)}\n"
            f"Mode: {mode}\n"
            f"Stored Outputs: Max {MAX_OUTPUT_FILES}"
        )

        return (
            str(output_path),
            str(output_path),
            status
        )

    except gr.Error:
        raise

    except Exception as e:
        raise gr.Error(
            f"Generation Error: {e}"
        )

    finally:
        clean_memory()


# ==================================================
# 9. PRESET GENERATION
# ==================================================

def generate_preset(
    text,
    voice_id,
    mode
):

    record = find_voice(
        voice_id
    )

    if record is None:
        raise gr.Error(
            "Saved Preset မရှိသေးပါ။ "
            "အရင် Upload လုပ်ပါ။"
        )

    audio_path = get_voice_path(
        record
    )

    return generate_engine(
        text=text,
        audio_path=str(audio_path),
        transcript=record.get(
            "prompt_text", ""
        ),
        mode=mode,
        prefix="preset"
    )


# ==================================================
# 10. CLONE VOICE
# ==================================================

def generate_clone(
    text,
    audio,
    transcript,
    mode
):

    if not audio:
        raise gr.Error(
            "Reference Audio Upload လုပ်ပါ။"
        )

    return generate_engine(
        text=text,
        audio_path=audio,
        transcript=transcript,
        mode=mode,
        prefix="clone"
    )


# ==================================================
# 11. PROMPT VOICE
# ==================================================

def generate_prompt(
    text,
    style
):

    if not (style or "").strip():
        raise gr.Error(
            "Voice Style Prompt ထည့်ပါ။"
        )

    return generate_engine(
        text=text,
        style=style,
        prefix="prompt"
    )


# ==================================================
# 12. WEB USER INTERFACE
# ==================================================

voices = get_choices()

default_voice = (
    voices[0][1]
    if voices else None
)

with gr.Blocks(
    title="Channel 99 AI Studio V3.1"
) as interface:

    gr.Markdown(
        """
        # 🎙️ Channel 99 AI Studio
        ### Myanmar Voice Generator — V3.1

        **VoxCPM2 | Persistent Voice Library**

        ✅ Google Drive Preset Storage

        ✅ Temporary WAV Outputs

        ✅ Automatic Cleanup — Latest 5 Files
        """
    )

    with gr.Tabs():

        # ==================================
        # TAB 1 — PRESET VOICE
        # ==================================

        with gr.Tab("🎭 Preset Voice"):

            gr.Markdown(
                "## 🗣️ My Saved Voices"
            )

            with gr.Row():

                with gr.Column():

                    preset_dropdown = gr.Dropdown(
                        choices=voices,
                        value=default_voice,
                        label="Select Saved Voice",
                        interactive=True
                    )

                    with gr.Row():

                        refresh_btn = gr.Button(
                            "🔄 Refresh Library"
                        )

                        delete_btn = gr.Button(
                            "🗑️ Delete Preset",
                            variant="stop"
                        )

                    preset_mode = gr.Radio(
                        choices=[
                            "Reference Only",
                            "Hi-Fi (Transcript)"
                        ],
                        value="Reference Only",
                        label="Voice Cloning Mode"
                    )

                    preset_text = gr.Textbox(
                        label="📝 မြန်မာစာ ထည့်ပါ",
                        lines=8,
                        placeholder=(
                            "မင်္ဂလာပါ။ "
                            "ဒီနေ့မှာ အားလုံးကို "
                            "ကြိုဆိုပါတယ်။"
                        )
                    )

                    preset_button = gr.Button(
                        "🎙️ Generate Preset Voice",
                        variant="primary"
                    )

                with gr.Column():

                    preset_audio = gr.Audio(
                        label="🎧 Generated Voice"
                    )

                    preset_download = gr.File(
                        label="⬇️ Download WAV"
                    )

                    preset_status = gr.Textbox(
                        label="Status",
                        interactive=False
                    )

            gr.Markdown("---")

            gr.Markdown(
                "## ➕ Add New Preset Voice"
            )

            with gr.Row():

                with gr.Column():

                    new_name = gr.Textbox(
                        label="Voice Name",
                        placeholder=(
                            "ဥပမာ - ကိုကို / "
                            "ခိုင်ခိုင် / Narrator"
                        )
                    )

                    new_audio = gr.Audio(
                        label="Upload WAV / MP3",
                        sources=[
                            "upload",
                            "microphone"
                        ],
                        type="filepath"
                    )

                    new_transcript = gr.Textbox(
                        label=(
                            "Reference Text "
                            "(Optional)"
                        ),
                        lines=4,
                        placeholder=(
                            "အသံထဲမှာ ပြောထားတဲ့ "
                            "စာသားအတိအကျ။ "
                            "Hi-Fi Mode အတွက် လိုပါတယ်။"
                        )
                    )

                    save_button = gr.Button(
                        "💾 Save Voice to Google Drive",
                        variant="primary"
                    )

                with gr.Column():

                    library_status = gr.Textbox(
                        label="Library Status",
                        interactive=False
                    )

                    gr.Markdown(
                        """
                        ### How to Save

                        1. Enter a voice name.
                        2. Upload WAV or MP3.
                        3. Enter transcript if available.
                        4. Click Save Voice.
                        5. Select saved voice above.

                        **Saved voices are kept in
                        Google Drive permanently
                        until you delete them.**
                        """
                    )

            # Save voice
            save_button.click(
                fn=add_voice,
                inputs=[
                    new_name,
                    new_audio,
                    new_transcript
                ],
                outputs=[
                    preset_dropdown,
                    library_status,
                    new_name,
                    new_audio,
                    new_transcript
                ]
            )

            # Refresh voices
            refresh_btn.click(
                fn=refresh_voices,
                outputs=preset_dropdown
            )

            # Delete voice
            delete_btn.click(
                fn=delete_voice,
                inputs=preset_dropdown,
                outputs=[
                    preset_dropdown,
                    library_status
                ]
            )

            # Generate preset audio
            preset_button.click(
                fn=generate_preset,
                inputs=[
                    preset_text,
                    preset_dropdown,
                    preset_mode
                ],
                outputs=[
                    preset_audio,
                    preset_download,
                    preset_status
                ]
            )

        # ==================================
        # TAB 2 — CLONE VOICE
        # ==================================

        with gr.Tab("🎤 Clone Voice"):

            gr.Markdown(
                "## Clone Voice Without Saving"
            )

            with gr.Row():

                with gr.Column():

                    clone_text = gr.Textbox(
                        label="📝 Text to Speak",
                        lines=8
                    )

                    clone_audio = gr.Audio(
                        label="🎵 Reference Audio",
                        type="filepath",
                        sources=[
                            "upload",
                            "microphone"
                        ]
                    )

                    clone_transcript = gr.Textbox(
                        label=(
                            "Reference Transcript "
                            "(Optional)"
                        ),
                        lines=4
                    )

                    clone_mode = gr.Radio(
                        choices=[
                            "Reference Only",
                            "Hi-Fi (Transcript)"
                        ],
                        value="Reference Only",
                        label="Cloning Mode"
                    )

                    clone_button = gr.Button(
                        "🎤 Generate Cloned Voice",
                        variant="primary"
                    )

                with gr.Column():

                    clone_output = gr.Audio(
                        label="🎧 Cloned Audio"
                    )

                    clone_download = gr.File(
                        label="⬇️ Download WAV"
                    )

                    clone_status = gr.Textbox(
                        label="Status",
                        interactive=False
                    )

            clone_button.click(
                fn=generate_clone,
                inputs=[
                    clone_text,
                    clone_audio,
                    clone_transcript,
                    clone_mode
                ],
                outputs=[
                    clone_output,
                    clone_download,
                    clone_status
                ]
            )

        # ==================================
        # TAB 3 — PROMPT VOICE
        # ==================================

        with gr.Tab("✨ Prompt Voice"):

            gr.Markdown(
                "## AI Voice Design"
            )

            with gr.Row():

                with gr.Column():

                    prompt_text = gr.Textbox(
                        label="📝 Text to Speak",
                        lines=8
                    )

                    prompt_style = gr.Textbox(
                        label="🎨 Voice Style Prompt",
                        lines=3,
                        value=(
                            "A calm and warm female "
                            "narrator with a natural "
                            "speaking pace"
                        )
                    )

                    gr.Examples(
                        examples=[
                            [
                                "A calm male narrator "
                                "with deep voice"
                            ],
                            [
                                "A warm female voice "
                                "with soft tone"
                            ],
                            [
                                "A professional news "
                                "anchor with clear voice"
                            ],
                            [
                                "A dramatic storyteller "
                                "with slow pace"
                            ],
                            [
                                "An energetic and cheerful "
                                "young host"
                            ]
                        ],
                        inputs=prompt_style
                    )

                    prompt_button = gr.Button(
                        "✨ Generate Prompt Voice",
                        variant="primary"
                    )

                with gr.Column():

                    prompt_output = gr.Audio(
                        label="🎧 AI Generated Audio"
                    )

                    prompt_download = gr.File(
                        label="⬇️ Download WAV"
                    )

                    prompt_status = gr.Textbox(
                        label="Status",
                        interactive=False
                    )

            prompt_button.click(
                fn=generate_prompt,
                inputs=[
                    prompt_text,
                    prompt_style
                ],
                outputs=[
                    prompt_output,
                    prompt_download,
                    prompt_status
                ]
            )

    # ==================================
    # FOOTER
    # ==================================

    gr.Markdown(
        """
        ---

        ### 🎙️ Channel 99 AI Studio V3.1

        **Storage System**

        - Preset Voices: Google Drive
        - Generated WAV: Colab Temporary Storage
        - Maximum Generated Files: 5
        - Oldest WAV: Automatically Deleted

        Only clone voices you own or have permission to use.
        """
    )


# ==================================================
# 13. LAUNCH WEB UI
# ==================================================

interface.queue(
    default_concurrency_limit=1
)

print("✅ Saved Presets:", len(voices))
print("✅ Max Output Files:", MAX_OUTPUT_FILES)
print("📁 Temporary Storage:", OUTPUT_DIR)

print(
    "🚀 Starting Channel 99 AI Studio V3.1..."
)

interface.launch(
    share=True,
    debug=False,
    show_error=True,
    allowed_paths=[
        str(PRESET_DIR),
        str(OUTPUT_DIR)
    ]
)
