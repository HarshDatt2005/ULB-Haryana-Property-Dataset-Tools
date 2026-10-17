# ULB Haryana Property Image Bot & Preprocessing Pipeline

This repository contains a complete pipeline for scraping property images from the public ULB Haryana portal and processing those low-resolution thumbnails into the exact 600x600 format required for computer vision and object detection models.

## Included Scripts

1. **`ulb_property_image_bot.py`**: Automatically navigates the ULB Haryana portal, iterates through all colonies, and downloads the best available Residential property photograph for each PID.
2. **`Enhancement.py`**: A traditional OpenCV/PIL image processing script that applies denoising, CLAHE contrast improvements, and unsharp masking, then letterboxes the thumbnails to exactly 600x600 without distorting the aspect ratio.
3. **`AI_Enhancement.py`**: A deep learning upscaling script that uses OpenCV's `dnn_superres` to apply the EDSR (Enhanced Deep Residual Networks) x4 model. It hallucinates missing high-frequency details to upscale heavily compressed thumbnails before letterboxing them to a 600x600 canvas.

---

## 1. Install Python

### Windows
Open Command Prompt:
```text
Windows + R
```
Type:
```cmd
cmd
```
Then:
```cmd
python --version
```
You need Python 3.10 or newer.

If Python is not installed, install it from:
https://www.python.org/downloads/

During installation, enable:
```text
Add Python to PATH
```
Close and reopen Command Prompt after installation.

---

## 2. Extract the project

Extract the ZIP file. You should have:
```text
property_pipeline/
│
├── ulb_property_image_bot.py
├── Enhancement.py
├── AI_Enhancement.py
└── README.md
```

---

## 3. Open the bot folder

Example:
```cmd
cd "C:\Users\YourName\Downloads\property_pipeline"
```
Then check:
```cmd
dir
```

---

## 4. Create a virtual environment

Recommended:
```cmd
python -m venv .venv
```
Activate it:
```cmd
.venv\Scripts\activate
```
You should see something like:
```text
(.venv) C:\Users\YourName\Downloads\property_pipeline>
```

---

## 5. Install dependencies

Run:
```cmd
pip install -r requirements.txt
```
*(Ensure your requirements.txt includes playwright, opencv-contrib-python, Pillow, and numpy)*

Then install Chromium for the web scraper:
```cmd
python -m playwright install chromium
```
You normally only need to do these installation steps once.

---

## 6. Run the Scraper: Test the Town

This is the recommended first test to copy all Colonies.

Run:
```cmd
python ulb_property_image_bot.py --headed --list-colonies --town "Faridabad"
```
The bot will:
* open Chromium
* select the Town
* read the live Colony dropdown
* print every Colony it finds

No images are downloaded when `--list-colonies` is used.

---

## 7. Run the Scraper: Process EVERY Colony

After the list test works, run:
```cmd
python ulb_property_image_bot.py --headed --town "Faridabad"
```
The bot will automatically iterate through every Colony, select Residential, search, and download the PID images. Existing `PID.jpeg` files are automatically skipped.

Images are saved by default in:
```text
property_images/
```
The bot also creates a `download_manifest.csv` recording the status of each PID (e.g., saved, exists, no_photo, download_failed).

---

## 8. Run Traditional Image Enhancement

Once your images are downloaded, you can prepare them for your object detection model using the traditional CV filters.

Before running, open `Enhancement.py` and ensure the `IMAGE_FOLDER` path points to your downloaded images:
```python
IMAGE_FOLDER = r"C:\Users\YourName\Downloads\property_pipeline\property_images"
```
Run the script:
```cmd
python Enhancement.py
```
The script will:
1. Upscale the image to make processing easier.
2. Reduce JPEG compression noise using `fastNlMeansDenoisingColored`.
3. Improve local contrast using CLAHE.
4. Scale and Letterbox the image to exactly 600x600 pixels (padding with black bars to preserve aspect ratio).
5. Save the outputs as high-quality JPEGs in a new folder named `enhanced_600x600`.

---

## 9. Run AI Image Enhancement (Super-Resolution)

If the thumbnails lack too much detail, you can use the AI Super-Resolution script instead.

Before running, open `AI_Enhancement.py` and verify your `IMAGE_FOLDER` path.

Run the script:
```cmd
python AI_Enhancement.py
```
The script will:
1. Automatically download the 38MB `EDSR_x4.pb` AI model from GitHub if it does not already exist on your machine.
2. Load the EDSR model into OpenCV's deep learning module.
3. Apply 4x AI Super-Resolution to hallucinate missing high-frequency details.
4. Letterbox the upscaled image to a perfect 600x600 canvas.
5. Save the outputs in a new folder named `ai_enhanced_600x600`.

---

## 10. macOS / Linux Quick Start

Create and activate the environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
```
Install:
```bash
pip install -r requirements.txt
python3 -m playwright install chromium
```
List Colonies:
```bash
python3 ulb_property_image_bot.py --headed --list-colonies --town "Faridabad"
```
Download Images:
```bash
python3 ulb_property_image_bot.py --headed --town "Faridabad"
```
Enhance Images (Traditional):
```bash
python3 Enhancement.py
```
Enhance Images (AI Super-Resolution):
```bash
python3 AI_Enhancement.py
```

---

## 11. Troubleshooting

### A. Scraper: "Could not find Town" or "No Colony values appeared"
Make sure the Town text matches the website dropdown exactly. The portal may be temporarily unavailable, or its dropdown/AJAX behavior may have changed. 
Try running with diagnostics:
```cmd
python ulb_property_image_bot.py --headed --verbose --list-colonies --town "YOUR TOWN"
```

### B. Enhancer: "Folder does not exist"
If `Enhancement.py` or `AI_Enhancement.py` fails with a folder error, you must open the Python file in a text editor and update the `IMAGE_FOLDER` variable at the top of the script to match the exact path on your computer.

### C. The Scraper encounters the same PID again
If `PID.jpeg` already exists, the bot skips it. This makes it safe to restart an interrupted run.
