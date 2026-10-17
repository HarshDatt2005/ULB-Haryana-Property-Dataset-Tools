# ============================================================
# AI SUPER-RESOLUTION & LETTERBOXING SCRIPT
# ============================================================

import cv2
from cv2 import dnn_superres
from PIL import Image
import numpy as np
from pathlib import Path
import urllib.request
import os

# ------------------------------------------------------------
# CONFIGURATION - CHANGE YOUR FOLDER PATH HERE
# ------------------------------------------------------------
IMAGE_FOLDER = r"C:\Users\Harsh Datt\Data Science\BOT\property_images"

OUTPUT_FOLDER_NAME = "ai_enhanced_600x600"
FINAL_SIZE = 600

# We are using EDSR (Enhanced Deep Residual Networks) x4 Model
MODEL_FILENAME = "EDSR_x4.pb"
MODEL_URL = "https://github.com/Saafke/EDSR_Tensorflow/raw/master/models/EDSR_x4.pb"


def download_ai_model():
    """Downloads the 38MB AI model automatically if missing."""
    if not os.path.exists(MODEL_FILENAME):
        print(f"Downloading AI Model ({MODEL_FILENAME})...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_FILENAME)
        print("Download complete!\n")


def process_image_with_ai(input_file, output_file, sr_model):
    """Upscales using AI, then letterboxes to exactly 600x600."""
    
    # 1. Read Image
    img = cv2.imread(str(input_file))
    if img is None:
        print(f"Skipped (Cannot read): {input_file.name}")
        return

    # 2. Apply AI Super Resolution (4x upscaling)
    upscaled_img = sr_model.upsample(img)

    # 3. Convert OpenCV Image (BGR) to PIL Image (RGB)
    upscaled_img = cv2.cvtColor(upscaled_img, cv2.COLOR_BGR2RGB)
    pil_image = Image.fromarray(upscaled_img)

    # 4. Resize maintaining aspect ratio (so it fits inside 600x600)
    pil_image.thumbnail((FINAL_SIZE, FINAL_SIZE), Image.Resampling.LANCZOS)

    # 5. Letterbox (Pad with black bars to make it perfectly square)
    letterboxed_canvas = Image.new("RGB", (FINAL_SIZE, FINAL_SIZE), (0, 0, 0))
    
    upper_left = (
        (FINAL_SIZE - pil_image.width) // 2,
        (FINAL_SIZE - pil_image.height) // 2
    )
    
    letterboxed_canvas.paste(pil_image, upper_left)

    # 6. Save the AI-Enhanced Image
    letterboxed_canvas.save(
        output_file,
        format="JPEG",
        quality=95,
        optimize=True
    )


def main():
    input_folder = Path(IMAGE_FOLDER)

    if not input_folder.exists():
        print(f"\nERROR: Folder does not exist:\n{input_folder}")
        return

    output_folder = input_folder.parent / OUTPUT_FOLDER_NAME
    output_folder.mkdir(parents=True, exist_ok=True)

    # Download AI weights
    download_ai_model()

    # Initialize OpenCV Deep Learning Super Resolution
    print("Loading AI Model into memory...")
    sr = dnn_superres.DnnSuperResImpl_create()
    sr.readModel(MODEL_FILENAME)
    sr.setModel("edsr", 4) 

    # Get images
    extensions = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    image_files = [f for f in input_folder.iterdir() if f.is_file() and f.suffix.lower() in extensions]

    print("=" * 60)
    print("AI SUPER-RESOLUTION PROCESSING")
    print("=" * 60)
    
    successful = 0

    for number, input_file in enumerate(image_files, start=1):
        output_file = output_folder / f"{input_file.stem}_ai_600x600.jpg"

        try:
            print(f"[{number}/{len(image_files)}] AI Enhancing: {input_file.name}...")
            process_image_with_ai(input_file, output_file, sr)
            successful += 1
        except Exception as e:
            print(f"ERROR: {input_file.name} -> {e}")

    print("\n" + "=" * 60)
    print(f"DONE! Processed: {successful}/{len(image_files)}")
    print(f"Check output folder: {output_folder}")
    print("=" * 60)

if __name__ == "__main__":
    main()