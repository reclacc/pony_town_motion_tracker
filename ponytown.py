import cv2
import mss
import time
import numpy as np
import pyautogui
from dataclasses import dataclass
from ctypes import windll, Structure, c_long, byref
from pynput import keyboard
import os
from datetime import datetime
import win32gui
import win32process
import psutil

class POINT(Structure):
    _fields_ = [("x", c_long), ("y", c_long)]

@dataclass
class Position:
    x: int
    y: int

class MovementDetector:
    def __init__(self, debug_mode=False):
        self.sct = mss.mss()
        self.fgbg = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
        self.last_movement_time = time.time()
        self.last_position_check = time.time()
        self.reset_position_interval = 3
        self.movement_threshold = 500
        self.size = 400
        self.x_threshold = 20
        self.y_threshold = 15
        self.is_running = False
        self.is_paused = True
        self.debug_mode = debug_mode
        self.program_pid = os.getpid()
        
        # ОТЛАДКАААА
        if self.debug_mode:
            self.debug_dir = 'debug_images'
            os.makedirs(self.debug_dir, exist_ok=True)
        
        # клавиши чтоб стопать и всё вообще делать
        self.listener = keyboard.Listener(
            on_press=self.on_key_press)
        self.listener.start()
        
    def on_key_press(self, key):
        try:
            if key.char == 'r':  # пауза/возобновление
                self.is_paused = not self.is_paused
                print('Program ' + ('paused' if self.is_paused else 'resumed'))
            elif key.char == 'q':  # выход
                self.is_running = False
                print('Program stopping...')
                return False
            if self.is_program_window_active() and key.char == 'd':
                self.toggle_debug_mode()
        except AttributeError:
            pass

    def toggle_debug_mode(self):
        self.debug_mode = not self.debug_mode
        print('Debug mode ' + ('enabled' if self.debug_mode else 'disabled'))
        if self.debug_mode:
            os.makedirs(self.debug_dir, exist_ok=True)

    def get_cursor_position(self):
        pt = POINT()
        windll.user32.GetCursorPos(byref(pt))
        return Position(pt.x, pt.y)
    
    def capture_screen_region(self, center_pos: Position):
        half_size = self.size // 2
        monitor = {
            "top": center_pos.y - half_size,
            "left": center_pos.x - half_size,
            "width": self.size,
            "height": self.size
        }
        screenshot = self.sct.grab(monitor)
        return cv2.cvtColor(np.array(screenshot), cv2.COLOR_BGRA2BGR)

    def save_debug_image(self, image, prefix):
        if self.debug_mode:
            timestamp = datetime.now().strftime('%H%M%S_%f')
            filename = f"{self.debug_dir}/{prefix}_{timestamp}.png"
            cv2.imwrite(filename, image)

    def detect_movement(self, frame):
        # для отладки сохранение картинок
        self.save_debug_image(frame, 'original')
        
        # блюр для уменьшения шума, 
        blurred = cv2.GaussianBlur(frame, (21, 21), 0)
        
        # вычитание фона
        fgmask = self.fgbg.apply(blurred)
        self.save_debug_image(fgmask, 'fgmask')
        
        # контуры движущихся гадов
        contours, _ = cv2.findContours(fgmask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        max_area = 0
        movement_center = None
        
        # копия фрейма для дебага
        if self.debug_mode:
            debug_frame = frame.copy()
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > self.movement_threshold and area > max_area:
                max_area = area
                M = cv2.moments(contour)
                if M["m00"] != 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    movement_center = Position(cx, cy)
                    
                    if self.debug_mode:
                        # отрисовка контуров и центров
                        cv2.drawContours(debug_frame, [contour], -1, (0, 255, 0), 2)
                        cv2.circle(debug_frame, (cx, cy), 5, (0, 0, 255), -1)
        
        if self.debug_mode and movement_center:
            self.save_debug_image(debug_frame, 'detection')
        
        return movement_center

    def determine_direction(self, current_pos: Position, movement_pos: Position):
        half_size = self.size // 2
        relative_x = current_pos.x - (movement_pos.x + current_pos.x - half_size)
        relative_y = current_pos.y - (movement_pos.y + current_pos.y - half_size)
        
        x_threshold = self.x_threshold
        y_threshold = self.y_threshold
        
        if relative_y < -y_threshold:
            if relative_x > x_threshold:
                return 'num1'
            elif relative_x < -x_threshold:
                return 'num3'
            else:
                return 'num2'
        elif relative_y > y_threshold:
            if relative_x > x_threshold:
                return 'num7'
            elif relative_x < -x_threshold:
                return 'num9'
            else:
                return 'num8'
        else:
            if relative_x > x_threshold:
                return 'num4'
            elif relative_x < -x_threshold:
                return 'num6'
            else:
                return 'num5'

    def is_program_window_active(self):
        try:
            hwnd = win32gui.GetForegroundWindow()
            _, active_pid = win32process.GetWindowThreadProcessId(hwnd)
            active_process = psutil.Process(active_pid)
            if active_process.name().lower() == 'cmd.exe':
                for child in active_process.children(recursive=True):
                    if child.pid == self.program_pid:
                        return True
            
            return active_pid == self.program_pid
            
        except Exception as e:
            print(f"Error checking active window: {e}")
            return False

    def run(self):
        print("Program controls:")
        print("R - Pause/Resume")
        print("D - Toggle debug mode")
        print("Q - Quit")
        print("\nProgram is paused. Press 'R' to start...")
        
        self.is_running = True
        while self.is_running:
            try:
                if not self.is_paused:
                    current_pos = self.get_cursor_position()
                    frame = self.capture_screen_region(current_pos)
                    
                    current_time = time.time()
                    if current_time - self.last_position_check >= self.reset_position_interval:
                        pyautogui.press('num5')
                        self.last_position_check = current_time
                    
                    movement_pos = self.detect_movement(frame)
                    
                    if movement_pos:
                        direction = self.determine_direction(current_pos, movement_pos)
                        pyautogui.press(direction)
                        self.last_movement_time = current_time
                        self.last_position_check = current_time
                
                time.sleep(0.03)
                
            except Exception as e:
                print(f"Error occurred: {e}")
                if self.debug_mode:
                    raise
                
        self.listener.stop()

if __name__ == "__main__":
    detector = MovementDetector(debug_mode=False)
    detector.run()