from PySide6.QtWidgets import (QApplication, QMainWindow, QPushButton,
                              QCheckBox, QVBoxLayout, QWidget)
from PySide6.QtCore import Qt, Signal
import pyperclip
import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write
import threading
import queue
import time
import os
from whisper_client import WhisperClient
import pynput.keyboard as keyboard
from custom_hotkey_listener import HotkeyListener
from pystray import Icon, MenuItem, Menu
from PIL import Image
import platform
import sys


class AudioRecorder(QMainWindow):
    def __init__(self, model_name="medium.en", shortcut="alt+shift+r", notify_clipboard_saving=True):
        super().__init__()
        self.system_platform = platform.system()
        self.output_folder = "output"
        self.setWindowTitle("WhisperClip")
        self.resize(200, 100)
        
        self.is_recording = False
        self.recordings = []
        self.transcription_queue = queue.Queue()
        self.transcriber = WhisperClient(model_name=model_name)
        self.keep_transcribing = True
        self.shortcut = shortcut
        self.notify_clipboard_saving = notify_clipboard_saving
        
        # Add thread management
        self.model_loading_thread = None
        self.model_ready = threading.Event()

        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Record button
        self.record_button = QPushButton("🎙")
        self.record_button.setStyleSheet("font-size: 24px; background-color: white;")
        self.record_button.clicked.connect(self.toggle_recording)
        layout.addWidget(self.record_button, stretch=1)

        # Clipboard checkbox
        self.save_to_clipboard = True
        self.clipboard_checkbox = QCheckBox("Save to Clipboard")
        self.clipboard_checkbox.setChecked(True)
        self.clipboard_checkbox.stateChanged.connect(self.on_clipboard_check)
        layout.addWidget(self.clipboard_checkbox)

        self.transcription_thread = threading.Thread(target=self.process_transcriptions)
        self.transcription_thread.start()

        # Set up the global shortcut and system tray icon
        self.setup_global_shortcut()
        self.setup_system_tray()

    def on_clipboard_check(self, state):
        self.save_to_clipboard = state == Qt.Checked

    def load_model_async(self):
        self.transcriber.load_model()
        self.model_ready.set()

    def toggle_recording(self):
        if self.is_recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        self.is_recording = True
        self.record_button.setStyleSheet("font-size: 24px; background-color: red;")
        
        # Start model loading in parallel
        self.model_ready.clear()
        self.model_loading_thread = threading.Thread(target=self.load_model_async)
        self.model_loading_thread.start()
        
        # Start recording immediately
        self.record_thread = threading.Thread(target=self.record_audio)
        self.record_thread.start()

    def stop_recording(self):
        self.is_recording = False
        self.record_button.setStyleSheet("font-size: 24px; background-color: white;")
        sd.stop()
        self.record_thread.join()
        
        if self.recordings:
            audio_data = np.concatenate(self.recordings)
            audio_data = (audio_data * 32767).astype(np.int16)
            os.makedirs(self.output_folder, exist_ok=True)
            filename = f"{self.output_folder}/audio_{int(time.time())}.wav"
            write(filename, 44100, audio_data)
            self.recordings = []
            self.transcription_queue.put((filename, self.model_loading_thread))
        else:
            print("No audio data recorded. Please check your audio input device.")
            # If no audio was recorded, wait for model loading and unload it
            if self.model_loading_thread and self.model_loading_thread.is_alive():
                self.model_loading_thread.join()
                self.transcriber.unload_model()

    def play_notification_sound(self):
        sound_file = './assets/saved-on-clipboard-sound.wav'

        if self.system_platform == 'Windows':
            import winsound
            winsound.PlaySound(sound_file, winsound.SND_FILENAME)
        elif self.system_platform == 'Darwin':  # MacOS
            os.system(f'afplay {sound_file}')
        elif self.system_platform == 'Linux':   # Linux
            os.system(f"paplay {sound_file}")
        else:
            print(f'Unsupported platform. Please open an issue to request support for your operating system. System: '
                  f'{self.system_platform}')

    def process_transcriptions(self):
        while self.keep_transcribing:
            try:
                filename, loading_thread = self.transcription_queue.get(timeout=1)
                
                # Wait for model to be ready if it's still loading
                if loading_thread and loading_thread.is_alive():
                    self.model_ready.wait()  # Wait for model loading to complete
                
                transcription = self.transcriber.transcribe(filename)
                print(f"Transcription for {filename}:", transcription)
                self.transcription_queue.task_done()
                
                if self.save_to_clipboard:
                    pyperclip.copy(transcription)
                    if self.notify_clipboard_saving:
                        self.play_notification_sound()
                
                # Unload model after transcription is complete
                self.transcriber.unload_model()
                self.model_ready.clear()
                
            except queue.Empty:
                continue

    def closeEvent(self, event):
        self.hide()  # Hide the window instead of closing
        event.ignore()

    def record_audio(self):
        with sd.InputStream(callback=self.audio_callback, channels=1):
            while self.is_recording:
                sd.sleep(1000)

    def audio_callback(self, indata, frames, time, status):
        self.recordings.append(indata.copy())

    def setup_global_shortcut(self):
        # Use the shortcut passed during initialization
        # custom implementation for linux system
        listener = HotkeyListener(self.shortcut, self.toggle_recording)
        keyboard_listener = keyboard.Listener(
            on_press=listener.on_press,
            on_release=listener.on_release
        )
        keyboard_listener.start()

    def setup_system_tray(self):
        # Load the icon image from a file
        icon_image = Image.open('./assets/whisper_clip.png')

        # Define the menu items
        menu = Menu(
            MenuItem('Toggle Recording (' + self.shortcut + ')', self.toggle_recording),
            MenuItem('Show Window', self.show_window, default=True, visible=False),
            MenuItem('Exit', self.exit_application)
        )

        # Create and run the system tray icon
        self.icon = Icon('WhisperClip', icon_image, 'WhisperClip', menu)
        self.icon.run_detached()

    def show_window(self):
        # Show the window again
        self.show()

    def exit_application(self):
        self.keep_transcribing = False
        self.transcription_thread.join()
        self.icon.stop()
        QApplication.quit()
