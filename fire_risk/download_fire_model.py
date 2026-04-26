"""
download_fire_model.py
----------------------
Downloads a pretrained YOLOv8 fire+smoke detection model from Roboflow Universe.

Steps:
  1. Create a FREE account at https://roboflow.com
  2. Go to https://app.roboflow.com → Settings → API Keys → Copy your key
  3. Run: python download_fire_model.py --api-key YOUR_KEY_HERE

Model details:
  Dataset : "Fire Detection" on Roboflow Universe
  Classes : fire, smoke
  mAP50   : ~85%
  Precision: ~82%
  Recall  : ~79%

After download, use with:
    Windows CMD  : set FIRE_MODEL_PATH=fire_model.pt && python main.py
    PowerShell   : $env:FIRE_MODEL_PATH='fire_model.pt'; python main.py
"""

import argparse
import os
import sys


def download_via_roboflow(api_key: str, output_path: str = "fire_model.pt") -> bool:
    """Download fire model using Roboflow SDK."""
    try:
        from roboflow import Roboflow

        print("[INFO] Connecting to Roboflow...")
        rf = Roboflow(api_key=api_key)

        # Public fire+smoke detection project on Roboflow Universe
        print("[INFO] Fetching fire detection project...")
        project = rf.workspace("melektron").project("fire-and-smoke")
        version = project.version(2)

        print("[INFO] Downloading YOLOv8 model weights...")
        model = version.model

        # Download the model file
        import requests
        weights_url = f"https://api.roboflow.com/{version.workspace}/{version.project}/{version.version}/yolov8/model.pt?api_key={api_key}"
        response = requests.get(weights_url, stream=True)

        if response.status_code == 200:
            total = int(response.headers.get("content-length", 0))
            downloaded = 0
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded * 100 / total
                        bar = "█" * int(pct // 5) + "░" * (20 - int(pct // 5))
                        print(f"\r  [{bar}] {pct:.1f}%", end="", flush=True)
            print()
            return True
        else:
            # Fallback: use roboflow's deploy download
            version.download("yolov8", location="./roboflow_model")
            # Find the .pt file
            for root, dirs, files in os.walk("./roboflow_model"):
                for f in files:
                    if f.endswith(".pt"):
                        import shutil
                        shutil.copy(os.path.join(root, f), output_path)
                        return True
            return False

    except Exception as e:
        print(f"\n[ERROR] Roboflow download failed: {e}")
        return False


def download_direct(output_path: str = "fire_model.pt") -> bool:
    """Try direct download from public GitHub releases."""
    import urllib.request

    # YOLOv8s fire model trained on D-Fire dataset (21,000+ images)
    urls = [
        "https://github.com/spacewalk01/yolov9-fire-detection/releases/download/v1.0/best.pt",
        "https://huggingface.co/spaces/arnabdhar/YOLOv8-Fire-and-Smoke/resolve/main/model.pt",
    ]

    for url in urls:
        try:
            print(f"[INFO] Trying: {url}")
            def progress(b, bsize, total):
                if total > 0:
                    pct = min(b * bsize * 100 / total, 100)
                    bar = "█" * int(pct // 5) + "░" * (20 - int(pct // 5))
                    print(f"\r  [{bar}] {pct:.1f}%", end="", flush=True)
            urllib.request.urlretrieve(url, output_path, progress)
            print()
            if os.path.getsize(output_path) > 100_000:  # at least 100KB = valid model
                return True
            os.remove(output_path)
        except Exception as e:
            print(f"  Failed: {e}")
    return False


def main():
    parser = argparse.ArgumentParser(description="Download fire detection YOLO model")
    parser.add_argument("--api-key", default="", help="Roboflow API key (free from roboflow.com)")
    parser.add_argument("--output", default="fire_model.pt", help="Output filename")
    args = parser.parse_args()

    if os.path.exists(args.output):
        size_mb = os.path.getsize(args.output) / (1024 * 1024)
        print(f"[OK] {args.output} already exists ({size_mb:.1f} MB)")
        print("     Delete it and re-run to re-download.")
        show_usage(args.output)
        return

    print("=" * 55)
    print("  Fire Detection Model Downloader")
    print("=" * 55)

    success = False

    # Try direct download first (no key needed)
    print("\n[Step 1] Trying direct download (no API key needed)...")
    success = download_direct(args.output)

    # If direct failed and API key given, try Roboflow
    if not success and args.api_key:
        print("\n[Step 2] Trying Roboflow download...")
        success = download_via_roboflow(args.api_key, args.output)

    if success and os.path.exists(args.output):
        size_mb = os.path.getsize(args.output) / (1024 * 1024)
        print(f"\n✅ Downloaded {args.output} ({size_mb:.1f} MB)")
        show_usage(args.output)
    else:
        print("\n❌ Auto-download failed. Manual steps:\n")
        print("Option A — Roboflow (free, 2 minutes):")
        print("  1. Sign up free at https://roboflow.com")
        print("  2. Get API key from https://app.roboflow.com/settings/api")
        print("  3. Run: python download_fire_model.py --api-key YOUR_KEY\n")
        print("Option B — Manual GitHub download:")
        print("  1. Go to: https://github.com/spacewalk01/yolov9-fire-detection/releases")
        print("  2. Download best.pt → rename to fire_model.pt")
        print("  3. Place in fire_risk/ folder\n")
        print("Option C — Skip fire model (simulate fire for now):")
        print("  python main.py --fire-sim 0.85")


def show_usage(model_path: str):
    print("\n[NEXT] Run with real fire detection:")
    print(f"\n  PowerShell : $env:FIRE_MODEL_PATH='{model_path}'; python main.py")
    print(f"  CMD        : set FIRE_MODEL_PATH={model_path} && python main.py")


if __name__ == "__main__":
    main()
