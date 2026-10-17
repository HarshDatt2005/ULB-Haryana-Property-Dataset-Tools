# ============================================================
# THUMBNAIL ENHANCER
# Change ONLY the IMAGE_FOLDER path below.
# ============================================================

import cv2
import numpy as np
from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter


# ------------------------------------------------------------
# CHANGE THIS PATH ONLY
# ------------------------------------------------------------
IMAGE_FOLDER = r"C:\Users\Harsh Datt\Data Science\BOT\property_images"


# ------------------------------------------------------------
# OUTPUT SETTINGS
# ------------------------------------------------------------
OUTPUT_FOLDER_NAME = "enhanced_600x600"
FINAL_SIZE = 600


# ------------------------------------------------------------
# IMAGE ENHANCEMENT SETTINGS
# ------------------------------------------------------------
CONTRAST = 1.12
BRIGHTNESS = 1.03
COLOR = 1.05
SHARPNESS = 1.30


# ============================================================
# ENHANCE ONE IMAGE
# ============================================================

def enhance_image(input_file, output_file):

    # Read image
    img = cv2.imread(str(input_file), cv2.IMREAD_COLOR)

    if img is None:
        print(f"Skipped: {input_file.name}")
        return

    # --------------------------------------------------------
    # Get original dimensions
    # --------------------------------------------------------
    height, width = img.shape[:2]

    # --------------------------------------------------------
    # Upscale BEFORE enhancement
    # Makes small thumbnails easier to process
    # --------------------------------------------------------
    target_long_side = 1200

    scale = max(
        4.0,
        target_long_side / max(width, height)
    )

    new_width = int(width * scale)
    new_height = int(height * scale)

    img = cv2.resize(
        img,
        (new_width, new_height),
        interpolation=cv2.INTER_CUBIC
    )

    # --------------------------------------------------------
    # Reduce JPEG/compression noise
    # --------------------------------------------------------
    img = cv2.fastNlMeansDenoisingColored(
        img,
        None,
        h=3,
        hColor=3,
        templateWindowSize=7,
        searchWindowSize=21
    )

    # --------------------------------------------------------
    # Improve local contrast using CLAHE
    # --------------------------------------------------------
    lab = cv2.cvtColor(
        img,
        cv2.COLOR_BGR2LAB
    )

    l_channel, a_channel, b_channel = cv2.split(lab)

    clahe = cv2.createCLAHE(
        clipLimit=1.5,
        tileGridSize=(8, 8)
    )

    l_channel = clahe.apply(l_channel)

    lab = cv2.merge(
        (l_channel, a_channel, b_channel)
    )

    img = cv2.cvtColor(
        lab,
        cv2.COLOR_LAB2BGR
    )

    # --------------------------------------------------------
    # Controlled sharpening
    # --------------------------------------------------------
    blurred = cv2.GaussianBlur(
        img,
        (0, 0),
        1.0
    )

    img = cv2.addWeighted(
        img,
        1.25,
        blurred,
        -0.25,
        0
    )

    # --------------------------------------------------------
    # Convert OpenCV -> PIL
    # --------------------------------------------------------
    img = cv2.cvtColor(
        img,
        cv2.COLOR_BGR2RGB
    )

    image = Image.fromarray(img)

    # --------------------------------------------------------
    # Fine adjustments
    # --------------------------------------------------------
    image = ImageEnhance.Contrast(
        image
    ).enhance(CONTRAST)

    image = ImageEnhance.Brightness(
        image
    ).enhance(BRIGHTNESS)

    image = ImageEnhance.Color(
        image
    ).enhance(COLOR)

    image = ImageEnhance.Sharpness(
        image
    ).enhance(SHARPNESS)

    # --------------------------------------------------------
    # Letterbox to exactly 600 x 600 (Preserves full image & aspect ratio)
    # --------------------------------------------------------
    image.thumbnail(
        (FINAL_SIZE, FINAL_SIZE),
        Image.Resampling.LANCZOS
    )

    letterboxed_canvas = Image.new(
        "RGB",
        (FINAL_SIZE, FINAL_SIZE),
        (0, 0, 0)
    )

    upper_left = (
        (FINAL_SIZE - image.width) // 2,
        (FINAL_SIZE - image.height) // 2
    )

    letterboxed_canvas.paste(image, upper_left)
    image = letterboxed_canvas

    # --------------------------------------------------------
    # Final subtle sharpening after resizing
    # --------------------------------------------------------
    image = image.filter(
        ImageFilter.UnsharpMask(
            radius=0.7,
            percent=55,
            threshold=3
        )
    )

    # --------------------------------------------------------
    # Save high-quality JPEG
    # --------------------------------------------------------
    image.save(
        output_file,
        format="JPEG",
        quality=95,
        optimize=True,
        subsampling=0
    )


# ============================================================
# MAIN
# ============================================================

def main():

    input_folder = Path(IMAGE_FOLDER)

    if not input_folder.exists():
        print("\nERROR:")
        print(f"Folder does not exist:\n{input_folder}")
        print("\nChange IMAGE_FOLDER at the top of the script.")
        return

    # Output folder automatically created inside input folder
    output_folder = (
        input_folder.parent / OUTPUT_FOLDER_NAME
    )

    output_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    # Supported formats
    extensions = {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".bmp"
    }

    image_files = [
        f
        for f in input_folder.iterdir()
        if f.is_file()
        and f.suffix.lower() in extensions
    ]

    if not image_files:
        print("\nNo images found in:")
        print(input_folder)
        return

    print("=" * 60)
    print("THUMBNAIL ENHANCER")
    print("=" * 60)
    print(f"Input : {input_folder}")
    print(f"Output: {output_folder}")
    print(f"Size  : {FINAL_SIZE} x {FINAL_SIZE}")
    print(f"Images: {len(image_files)}")
    print("=" * 60)

    successful = 0

    for number, input_file in enumerate(
        image_files,
        start=1
    ):

        output_file = (
            output_folder /
            f"{input_file.stem}_600x600.jpg"
        )

        try:

            print(
                f"[{number}/{len(image_files)}] "
                f"{input_file.name}"
            )

            enhance_image(
                input_file,
                output_file
            )

            successful += 1

        except Exception as e:

            print(
                f"ERROR: {input_file.name}"
            )

            print(
                f"        {e}"
            )

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)
    print(f"Processed : {successful}/{len(image_files)}")
    print(f"Output    : {output_folder}")
    print("=" * 60)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()