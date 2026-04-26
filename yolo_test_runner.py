import argparse
import sys
import os
import cv2
import requests
import time

# Add fire_risk to path so we can import detector
sys.path.append(os.path.join(os.path.dirname(__file__), "fire_risk"))
from detector import run_detection

def main():
    parser = argparse.ArgumentParser(description="YOLO ML Pipeline Test Runner")
    parser.add_argument("--video", required=True, help="Path to test MP4 video")
    parser.add_argument("--room", default="101", help="Room ID")
    parser.add_argument("--floor", default="1", help="Floor ID")
    parser.add_argument("--backend", default="http://localhost:8001", help="Staff backend URL")
    args = parser.parse_args()

    print(f"Starting YOLO test runner on {args.video} for room {args.room} (Floor {args.floor})")
    
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"Error: Could not open video {args.video}")
        sys.exit(1)

    frame_count = 0
    cooldown = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            frame_count += 1
            
            # Detect
            detection = run_detection(frame)
            fire_conf = detection.get("fire_conf", 0.0)
            
            # Normalize output (Forced MEDIUM)
            output = []
            if fire_conf > 0:
                output.append({"label": "fire", "confidence": 0.80})
                
            if output:
                print(f"[FRAME {frame_count}] Fire detected (forced MEDIUM)")
            
            # Trigger Logic (always fire if there is some detection)
            if fire_conf > 0 and time.time() > cooldown:
                payload = {
                    "type": "fire",
                    "room_id": args.room,
                    "floor": args.floor,
                    "risk_level": "MEDIUM",
                    "confidence": 0.80,
                    "source": "yolo_test"
                }
                
                try:
                    res = requests.post(f"{args.backend}/alerts", json=payload)
                    if res.status_code in (200, 201):
                        print("→ Alert Sent ✅")
                        cooldown = time.time() + 10  # 10s cooldown to avoid spamming
                    else:
                        print(f"→ Failed to send alert ❌ (Status {res.status_code}: {res.text})")
                except Exception as e:
                    print(f"→ Backend connection error ❌: {e}")

            # display for demo purposes
            # cv2.imshow("YOLO Test Runner", frame)
            # if cv2.waitKey(1) & 0xFF == ord('q'):
            #     break
                
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        cap.release()
        # cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
