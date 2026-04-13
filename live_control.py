import cv2
import mediapipe as mp
import serial
import time


class HandServoControl:

    def __init__(self, port='COM5', baud_rate=250000):
        self.port = port
        self.baud_rate = baud_rate

        # Initialize camera, opening webcam, setting width and height to 640 x 480 pixels
        self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # Initialize MediaPipe Hands - detect both hands
        self.hands = mp.solutions.hands.Hands(
            static_image_mode=False, #dont treat each frame seperate
            max_num_hands=2,
            min_detection_confidence=0.7, #70% confidence needed to detect
            min_tracking_confidence=0.5 #50% confidence needed to keep tracking
        )

        self.SCREEN_SPLIT = 0.5  #Vertical line at 50% of screen width down centre

        #Zone thresholds dividing screen into zones
        self.TOP_THRESHOLD = 0.2
        self.BOTTOM_THRESHOLD = 0.8
        self.LEFT_THRESHOLD = 0.2
        self.RIGHT_THRESHOLD = 0.8

        # Movement control settings for right hand (X/Y/Servo)
        self.last_servo_state = None
        self.last_y_zone = "CENTER"
        self.last_x_zone = "CENTER"
        self.last_y_command_time = time.time()
        self.last_x_command_time = time.time()

        #Movement control settings for left hand (Z/E)
        self.last_z_zone = "CENTER"
        self.last_e_zone = "CENTER"
        self.last_z_command_time = time.time()
        self.last_e_command_time = time.time()

        #State tracking for T0 extruder
        self.last_t0_zone = "CENTER"
        self.last_t0_command_time = time.time()

        # Left hand open/closed toggle
        self.left_hand_closed = False

        #Right hand Y axis parameters
        self.Y_MOVE_DISTANCE = 25
        self.Y_SPEED = 6000
        self.Y_COMMAND_INTERVAL = 0.3  #Minimum seconds between commands

        #Right hand X-axis parameters
        self.X_MOVE_DISTANCE = 0.5  # mm
        self.X_SPEED = 100
        self.X_COMMAND_INTERVAL = 0.3

        #Right hand T0 extruder parameters
        self.T0_MOVE_DISTANCE = 0.25
        self.T0_SPEED = 100
        self.T0_COMMAND_INTERVAL = 0.3

        #Left hand Z-axis movement parameters
        self.Z_MOVE_DISTANCE = 2.5  # mm
        self.Z_SPEED = 1000
        self.Z_COMMAND_INTERVAL = 0.7

        #Left hand E-axis (extruder)
        self.E_MOVE_DISTANCE = 0.5
        self.E_SPEED = 100
        self.E_COMMAND_INTERVAL = 0.2

        self.arduino = self._connect_arduino()

    def _connect_arduino(self): #Arduino serial connection
        try:
            arduino = serial.Serial(self.port, self.baud_rate, timeout=1)
            time.sleep(2)  #Wait for the arduino to reset
            arduino.reset_input_buffer()
            arduino.reset_output_buffer() #clear old buffer data
            print(f"Connected to {self.port}")
            return arduino
        except Exception as e:
            print(f"Running in demo mode: {e}") #if no arduino connected
            return None

    def _calibrate_robot(self): #inital calibration
        calibration_commands = [
            "G1 X2 Y2 Z2 F1000",
            "G1 X0 Y0 Z0 F1000",
            "T0",
            "G1 E1 F100",
            "G1 E0 F100",
            "T1",
            "G1 E1 F100",
            "G1 E0 F100",
            "M280 P0 S0",
            "M280 P0 S90",
            "G91"  #enter relative mode
        ]

        if self.arduino: #checking arduino connection
            print("Calibrating robot")
            for cmd in calibration_commands: #loop through calibration commands
                try:
                    self.arduino.write(f"{cmd}\n".encode())
                    self.arduino.flush() #sends data straight away
                    print(f"{cmd}")
                    time.sleep(0.5)
                except Exception as e:
                    print(f"Calibration error: {e}")
                    return False #stops if error occurs
            print("Calibration complete (relative mode active)\n")
            return True
        else: #enters demo mode if no arduino connected
            print("Skipping calibration (demo mode)\n")
            return False

    def _is_hand_open(self, landmarks): #compares fingertip and knuckle positions to determine if hand is open or closed. if fingertip y value is > or < than knuckle.
        index_extended = landmarks[8].y < landmarks[6].y - 0.03
        middle_extended = landmarks[12].y < landmarks[10].y - 0.03
        return index_extended and middle_extended

    def _send_servo_command(self, is_open): #sends servo command
        cmd = "M280 P0 S0\n" if is_open else "M280 P0 S90\n"
        if self.arduino:
            try:
                self.arduino.write(cmd.encode())
                self.arduino.flush()
            except Exception as e:
                print(f"Serial error: {e}")
        print(f"SERVO: {cmd.strip()}")

    def _get_vertical_zone(self, hand_y): #Returns the vertical zone that hand is in
        if hand_y < self.TOP_THRESHOLD:
            return "TOP"
        elif hand_y > self.BOTTOM_THRESHOLD:
            return "BOTTOM"
        return "CENTER"

    def _get_horizontal_zone(self, hand_relative): #returns the horizontal zone that the hand is in
        if hand_relative < self.LEFT_THRESHOLD:
            return "LEFT"
        elif hand_relative > self.RIGHT_THRESHOLD:
            return "RIGHT"
        return "CENTER"

    def _send_y_command(self, zone): #sends y command movement for this zone
        current_time = time.time() #prevents spamming, waits 0.3s time
        if current_time - self.last_y_command_time < self.Y_COMMAND_INTERVAL:
            return

        if zone == "TOP":
            cmd = f"G1 Y-{self.Y_MOVE_DISTANCE} F{self.Y_SPEED}"
        elif zone == "BOTTOM":
            cmd = f"G1 Y{self.Y_MOVE_DISTANCE} F{self.Y_SPEED}"
        else:
            return #do nothing the hand is in center of screen

        if self.arduino:
            try:
                self.arduino.write(f"{cmd}\n".encode())
                self.arduino.flush()
            except Exception as e:
                print(f"Serial error: {e}")

        print(f"Y-AXIS: {cmd}")
        self.last_y_command_time = current_time

    def _send_x_command(self, zone):
        current_time = time.time()
        if current_time - self.last_x_command_time < self.X_COMMAND_INTERVAL:
            return

        if zone == "LEFT":
            cmd = f"G1 X{self.X_MOVE_DISTANCE} F{self.X_SPEED}"
        elif zone == "RIGHT":
            cmd = f"G1 X-{self.X_MOVE_DISTANCE} F{self.X_SPEED}"
        else:
            return

        if self.arduino:
            try:
                self.arduino.write(f"{cmd}\n".encode())
                self.arduino.flush()
            except Exception as e:
                print(f"Serial error: {e}")

        print(f"X-AXIS: {cmd}")
        self.last_x_command_time = current_time

    def _send_t0_command(self, zone):
        current_time = time.time()
        if current_time - self.last_t0_command_time < self.T0_COMMAND_INTERVAL:
            return

        if zone == "LEFT":
            e_cmd = f"G1 E{self.T0_MOVE_DISTANCE} F{self.T0_SPEED}"
        elif zone == "RIGHT":
            e_cmd = f"G1 E-{self.T0_MOVE_DISTANCE} F{self.T0_SPEED}"
        else:
            return

        if self.arduino:
            try:
                self.arduino.write("T0\n".encode())
                self.arduino.flush()
                time.sleep(0.1)
                self.arduino.write(f"{e_cmd}\n".encode())
                self.arduino.flush()
            except Exception as e:
                print(f"Serial error: {e}")

        print(f"T0-AXIS: T0 = {e_cmd}")
        self.last_t0_command_time = current_time

    def _send_z_command(self, zone):
        current_time = time.time()
        if current_time - self.last_z_command_time < self.Z_COMMAND_INTERVAL:
            return

        if zone == "TOP":
            cmd = f"G1 Z{self.Z_MOVE_DISTANCE} F{self.Z_SPEED}"
        elif zone == "BOTTOM":
            cmd = f"G1 Z-{self.Z_MOVE_DISTANCE} F{self.Z_SPEED}"
        else:
            return

        if self.arduino:
            try:
                self.arduino.write(f"{cmd}\n".encode())
                self.arduino.flush()
            except Exception as e:
                print(f"Serial error: {e}")

        print(f"Z-AXIS: {cmd}")
        self.last_z_command_time = current_time

    def _send_e_command(self, zone):
        current_time = time.time()
        if current_time - self.last_e_command_time < self.E_COMMAND_INTERVAL:
            return

        if zone == "LEFT":
            e_cmd = f"G1 E{self.E_MOVE_DISTANCE} F{self.E_SPEED}"
        elif zone == "RIGHT":
            e_cmd = f"G1 E-{self.E_MOVE_DISTANCE} F{self.E_SPEED}"
        else:
            return

        if self.arduino:
            try:
                self.arduino.write("T1\n".encode())
                self.arduino.flush()
                time.sleep(0.1)
                self.arduino.write(f"{e_cmd}\n".encode())
                self.arduino.flush()
            except Exception as e:
                print(f"Serial error: {e}")

        print(f"E-AXIS: T1 = {e_cmd}")
        self.last_e_command_time = current_time

    def run(self):
        print("DUAL HAND CONTROL - LEFT: Z/E/Toggle | RIGHT: X/Y/Servo")

        self._calibrate_robot()

        print("SCREEN LAYOUT:")
        print("  Left half = Left hand controls Z-axis and extruder (T1)")
        print("  Right half = Right hand controls X/Y-axis and servo")
        print("\nLeft hand (left half):")
        print("  Z-AXIS:  Top    = G1 Z-2.5 F1000 | Bottom = G1 Z2.5 F1000")
        print("  E-AXIS:  Left   = T1 + G1 E0.5 F100 | Right = T1 + G1 E-0.5 F100")
        print("  TOGGLE:  Open/closed state switches right hand controls")
        print("\nRight hand (right half):")
        print("  Y-AXIS:  Top    =  G1 Y-25 F6000 | Bottom = G1 Y25 F6000")
        print("  X-ZONE (left hand closed): Left = G1 X0.5 F100 | Right = G1 X-0.5 F100")
        print("  X-ZONE (left hand open):   Left = T0 + G1 E0.25 F100 | Right = T0 + G1 E-0.25 F100")
        print("  SERVO:   Open   = M280 P0 S0 | Closed = M280 P0 S90")
        print("\nPress 'q' to quit\n")

        while True: #grabs one webcam frame
            ret, frame = self.cap.read()
            if not ret: #error if no picture
                break

            frame = cv2.flip(frame, 1) #flips image mirror image
            height, width, _ = frame.shape #gets screen size

            results = self.hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

            split_x = int(self.SCREEN_SPLIT * width) #middle line at 320 pixels

            cv2.line(frame, (split_x, 0), (split_x, height), (255, 255, 255), 3)  #vertical split line

            #Left half zone boundaries (divides to top, middle and bottom zones)
            z_top_line = int(self.TOP_THRESHOLD * height)
            z_bottom_line = int(self.BOTTOM_THRESHOLD * height)
            cv2.line(frame, (0, z_top_line), (split_x, z_top_line), (0, 255, 255), 2)
            cv2.line(frame, (0, z_bottom_line), (split_x, z_bottom_line), (0, 255, 255), 2)

            left_half_width = split_x
            e_left_line = int(self.LEFT_THRESHOLD * left_half_width)
            e_right_line = int(self.RIGHT_THRESHOLD * left_half_width)
            cv2.line(frame, (e_left_line, 0), (e_left_line, height), (255, 128, 0), 2)
            cv2.line(frame, (e_right_line, 0), (e_right_line, height), (255, 128, 0), 2)

            # Left half labels
            cv2.putText(frame, "LEFT HAND", (split_x // 2 - 60, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(frame, "Z-", (split_x - 50, z_top_line - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cv2.putText(frame, "Z+", (split_x - 50, z_bottom_line + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cv2.putText(frame, "E+", (e_left_line - 30, height // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 128, 0), 2)
            cv2.putText(frame, "E-", (e_right_line + 10, height // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 128, 0), 2)

            #Right half zone boundaries
            y_top_line = int(self.TOP_THRESHOLD * height)
            y_bottom_line = int(self.BOTTOM_THRESHOLD * height)
            cv2.line(frame, (split_x, y_top_line), (width, y_top_line), (0, 255, 255), 2)
            cv2.line(frame, (split_x, y_bottom_line), (width, y_bottom_line), (0, 255, 255), 2)

            right_half_width = width - split_x
            x_left_line = split_x + int(self.LEFT_THRESHOLD * right_half_width)
            x_right_line = split_x + int(self.RIGHT_THRESHOLD * right_half_width)
            cv2.line(frame, (x_left_line, 0), (x_left_line, height), (255, 0, 255), 2)
            cv2.line(frame, (x_right_line, 0), (x_right_line, height), (255, 0, 255), 2)

            #Right half labels
            cv2.putText(frame, "RIGHT HAND", (split_x + right_half_width // 2 - 70, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(frame, "Y-", (width - 50, y_top_line - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cv2.putText(frame, "Y+", (width - 50, y_bottom_line + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

            #Dynamic changing zones
            if self.left_hand_closed:
                cv2.putText(frame, "X+", (x_left_line - 40, height // 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)
                cv2.putText(frame, "X-", (x_right_line + 10, height // 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)
            else:
                cv2.putText(frame, "T0+", (x_left_line - 50, height // 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 255, 255), 2)
                cv2.putText(frame, "T0-", (x_right_line + 10, height // 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 255, 255), 2)

            #label seperate,  detected hands based on landmarks
            left_hand_data = None
            right_hand_data = None

            if results.multi_hand_landmarks and results.multi_handedness:
                for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
                    hand_label = handedness.classification[0].label
                    wrist = hand_landmarks.landmark[0]

                    if hand_label == "Left":
                        left_hand_data = {
                            'landmarks': hand_landmarks,
                            'x': wrist.x,
                            'y': wrist.y
                        }
                    else:
                        right_hand_data = {
                            'landmarks': hand_landmarks,
                            'x': wrist.x,
                            'y': wrist.y
                        }

            #Overlay left hand
            if left_hand_data and left_hand_data['x'] < self.SCREEN_SPLIT:
                hand = left_hand_data['landmarks']
                hand_x = left_hand_data['x']
                hand_y = left_hand_data['y']

                mp.solutions.drawing_utils.draw_landmarks(
                    frame, hand, mp.solutions.hands.HAND_CONNECTIONS
                )

                hand_pixel_x = int(hand_x * width) #circle at wrist
                hand_pixel_y = int(hand_y * height)
                cv2.circle(frame, (hand_pixel_x, hand_pixel_y), 15, (0, 255, 255), -1)

                #Update the toggle state
                self.left_hand_closed = not self._is_hand_open(hand.landmark)
                toggle_state = "CLOSED (X-AXIS)" if self.left_hand_closed else "OPEN (T0-AXIS)"
                toggle_color = (0, 0, 255) if self.left_hand_closed else (0, 255, 0)
                cv2.putText(frame, f"Toggle: {toggle_state}", (20, height - 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, toggle_color, 2)

                #Z
                current_z_zone = self._get_vertical_zone(hand_y)
                if current_z_zone != "CENTER":
                    self._send_z_command(current_z_zone)
                self.last_z_zone = current_z_zone

                z_color = (0, 255, 255) if current_z_zone != "CENTER" else (0, 255, 0)
                cv2.putText(frame, f"Z: {current_z_zone}", (20, 70),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, z_color, 2)

                #E
                hand_x_relative = hand_x / self.SCREEN_SPLIT
                current_e_zone = self._get_horizontal_zone(hand_x_relative)
                if current_e_zone != "CENTER":
                    self._send_e_command(current_e_zone)
                self.last_e_zone = current_e_zone

                e_color = (255, 128, 0) if current_e_zone != "CENTER" else (0, 255, 0)
                cv2.putText(frame, f"E: {current_e_zone}", (20, 110),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, e_color, 2)

                #Cooldown
                time_since_z = time.time() - self.last_z_command_time
                time_since_e = time.time() - self.last_e_command_time

                if time_since_z < self.Z_COMMAND_INTERVAL:
                    cv2.putText(frame, f"Z CD: {self.Z_COMMAND_INTERVAL - time_since_z:.1f}s",
                                (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 165, 0), 2)

                if time_since_e < self.E_COMMAND_INTERVAL:
                    cv2.putText(frame, f"E CD: {self.E_COMMAND_INTERVAL - time_since_e:.1f}s",
                                (20, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 165, 0), 2)

            #Overlay right hand
            if right_hand_data and right_hand_data['x'] >= self.SCREEN_SPLIT:
                hand = right_hand_data['landmarks']
                hand_x = right_hand_data['x']
                hand_y = right_hand_data['y']

                mp.solutions.drawing_utils.draw_landmarks(
                    frame, hand, mp.solutions.hands.HAND_CONNECTIONS
                )

                hand_pixel_x = int(hand_x * width)
                hand_pixel_y = int(hand_y * height)
                cv2.circle(frame, (hand_pixel_x, hand_pixel_y), 15, (255, 0, 255), -1)

                # Servo control
                is_open = self._is_hand_open(hand.landmark)
                servo_state = "OPEN" if is_open else "CLOSED"
                if servo_state != self.last_servo_state:
                    self._send_servo_command(is_open)
                    self.last_servo_state = servo_state

                servo_color = (0, 255, 0) if is_open else (0, 0, 255)
                cv2.putText(frame, f"Servo: {servo_state}", (split_x + 20, 70),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, servo_color, 2)

                #Y
                current_y_zone = self._get_vertical_zone(hand_y)
                if current_y_zone != "CENTER":
                    self._send_y_command(current_y_zone)
                self.last_y_zone = current_y_zone

                y_color = (0, 255, 255) if current_y_zone != "CENTER" else (0, 255, 0)
                cv2.putText(frame, f"Y: {current_y_zone}", (split_x + 20, 110),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, y_color, 2)

                # X
                hand_x_relative = (hand_x - self.SCREEN_SPLIT) / (1.0 - self.SCREEN_SPLIT)
                current_x_zone = self._get_horizontal_zone(hand_x_relative)

                if current_x_zone != "CENTER":
                    if self.left_hand_closed:
                        self._send_x_command(current_x_zone)
                        self.last_x_zone = current_x_zone
                    else:
                        self._send_t0_command(current_x_zone)
                        self.last_t0_zone = current_x_zone

                if self.left_hand_closed:
                    x_color = (255, 0, 255) if current_x_zone != "CENTER" else (0, 255, 0)
                    cv2.putText(frame, f"X: {current_x_zone}", (split_x + 20, 150),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, x_color, 2)
                else:
                    t0_color = (100, 255, 255) if current_x_zone != "CENTER" else (0, 255, 0)
                    cv2.putText(frame, f"T0: {current_x_zone}", (split_x + 20, 150),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, t0_color, 2)

                #Cooldown indicators
                time_since_y = time.time() - self.last_y_command_time
                time_since_x = time.time() - self.last_x_command_time
                time_since_t0 = time.time() - self.last_t0_command_time

                if time_since_y < self.Y_COMMAND_INTERVAL:
                    cv2.putText(frame, f"Y CD: {self.Y_COMMAND_INTERVAL - time_since_y:.1f}s",
                                (split_x + 20, 190), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 165, 0), 2)

                if self.left_hand_closed and time_since_x < self.X_COMMAND_INTERVAL:
                    cv2.putText(frame, f"X CD: {self.X_COMMAND_INTERVAL - time_since_x:.1f}s",
                                (split_x + 20, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 165, 0), 2)

                if not self.left_hand_closed and time_since_t0 < self.T0_COMMAND_INTERVAL:
                    cv2.putText(frame, f"T0 CD: {self.T0_COMMAND_INTERVAL - time_since_t0:.1f}s",
                                (split_x + 20, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 165, 0), 2)

            #Connection status
            status = f"Connected: {self.port}" if self.arduino else "Demo Mode"
            cv2.putText(frame, status, (width // 2 - 55, 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            cv2.imshow("Dual Hand Control (Q to quit)", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        self.cap.release()
        cv2.destroyAllWindows()
        if self.arduino:
            self.arduino.close()
        print("Program ended")

if __name__ == "__main__":
    controller = HandServoControl(port='COM5', baud_rate=250000)
    controller.run()