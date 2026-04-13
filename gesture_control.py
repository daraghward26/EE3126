#  Gesture_control uses MediaPipe Gesture Recognizer to identify gestures

import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import threading
import time
import os
import commands

MODEL_PATH = os.path.join(os.path.dirname(__file__), "gesture_recognizer.task")
COOLDOWN_SECONDS = 30

def _load_triggers():
    all_cmds = commands._load_all()
    raw = all_cmds.get("gesture_triggers", {})
    #Filter null mapping
    return {k: v for k, v in raw.items() if v is not None}

def run(state, state_lock):

    if not os.path.exists(MODEL_PATH):
        print(
            "\ngesture_recognizer.task was not found in project folder.\n"
        )
        return

    triggers = _load_triggers()

    print("Gesture Control Mode")
    print("\n Gesture mappings:")
    for gesture, cmd in triggers.items():
        print(f" {gesture:<20} = {cmd}")
    print(f"\n Cooldown: {COOLDOWN_SECONDS}s between gestures.")
    print("Press Q in the camera window to return to main menu.\n")

    #Shared state between the main loop and the recognizer callback
    detected_gesture = [None]       #latest gesture detected
    active_command = threading.Event()
    last_fired_time = [0.0]
    last_fired_gesture = [None]

    def on_result(result, output_image, timestamp_ms): #MediaPipe setup
        if result.gestures:
            top = result.gestures[0][0]
            if top.score >= 0.75:        # confidence threshold
                detected_gesture[0] = top.category_name
            else:
                detected_gesture[0] = None
        else:
            detected_gesture[0] = None

    base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.GestureRecognizerOptions(
        base_options=base_options,
        running_mode= vision.RunningMode.LIVE_STREAM,
        result_callback=on_result,
        num_hands=1,
    )
    recognizer = vision.GestureRecognizer.create_from_options(options)

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    timestamp = 0

    def execute(cmd_name):
        active_command.set()
        try:
            commands.run_command(cmd_name, state, state_lock)
        finally:
            active_command.clear()

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            timestamp += 1
            recognizer.recognize_async(mp_image, timestamp)

            gesture = detected_gesture[0]
            now = time.time()

            #Overlay : gesture current
            display = gesture if gesture else "None"
            color = (0, 255, 0) if gesture in triggers else (100, 100, 100)
            cv2.putText(frame, f"Gesture: {display}", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

            # Overlay :cooldown setting
            if active_command.is_set():
                cv2.putText(frame, "Running command", (20, 80),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
            else:
                elapsed  = now - last_fired_time[0]
                remaining = max(0.0, COOLDOWN_SECONDS - elapsed)
                if remaining > 0:
                    cv2.putText(frame, f"Cooldown: {remaining:.0f}s", (20, 80),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
                else:
                    cv2.putText(frame, "Ready", (20, 80),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            # Overlay show mapped command on screen
            if gesture and gesture in triggers:
                cv2.putText(frame, f" = {triggers[gesture]}", (20, 120),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

            cv2.imshow("Gesture Control (Click Q to quit)", frame)

            #If gesture condition met/identified fire
            if (gesture
                    and gesture in triggers
                    and not active_command.is_set()
                    and (now - last_fired_time[0]) >= COOLDOWN_SECONDS):

                cmd_name = triggers[gesture]
                print(f"\n Gesture detected: {gesture} = {cmd_name}")
                last_fired_time[0]    = now
                last_fired_gesture[0] = gesture
                threading.Thread(
                    target=execute,
                    args=(cmd_name,),
                    daemon=True
                ).start()

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        cap.release()
        cv2.destroyAllWindows()
        recognizer.close()
        print("\n Returned to main menu.\n")
