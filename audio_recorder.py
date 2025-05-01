from PySide6.QtWidgets import (QApplication, QMainWindow, QPushButton,
                              QCheckBox, QVBoxLayout, QWidget, QSystemTrayIcon, QMenu)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QIcon, QShortcut, QKeySequence
import pyperclip
import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write
import threading
import queue
import time
import os
from whisper_client import WhisperClient
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
        self.record_thread = None

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
        # Minimize to tray instead of closing
        if self.tray_icon.isVisible():
            self.hide()
            event.ignore()
        else:
            self.cleanup()
            self.exit_application()

    def record_audio(self):
        with sd.InputStream(callback=self.audio_callback, channels=1):
            while self.is_recording:
                sd.sleep(1000)

    def audio_callback(self, indata, frames, time, status):
        self.recordings.append(indata.copy())

    def setup_global_shortcut(self):
        # Create Qt shortcut
        key_sequence = QKeySequence(self.shortcut)
        self.shortcut = QShortcut(key_sequence, self)
        self.shortcut.activated.connect(self.toggle_recording)

    def setup_system_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        
        # Load icon with absolute path
        icon_path = os.path.join(os.path.dirname(__file__), 'assets/whisper_clip.png')
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            print(f"Icon file not found at: {icon_path}")
            self.tray_icon.setIcon(QApplication.windowIcon())
        
        # Create tray menu
        tray_menu = QMenu()
        
        self.toggle_window_action = QAction("Show/Hide", self)
        self.toggle_window_action.triggered.connect(self.toggle_window_visibility)
        tray_menu.addAction(self.toggle_window_action)
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.exit_application)
        tray_menu.addAction(exit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        
        # Connect tray icon click to show window
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        
        # Enable minimize to tray
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinimizeButtonHint)
        
    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:  # Double click
            self.toggle_window_visibility()

    def toggle_window_visibility(self):
        if self.isVisible():
            self.hide()
            self.toggle_window_action.setText("Show")
        else:
            self.show()
            self.toggle_window_action.setText("Hide")

    def cleanup(self):
        """Release all resources and clean up temporary files"""
        # Stop any active recording
        if self.is_recording:
            self.stop_recording()
        
        # Release audio resources
        sd.stop()
        
        # Clean up threads
        self.keep_transcribing = False
        if hasattr(self, 'transcription_thread') and self.transcription_thread.is_alive():
            self.transcription_thread.join(timeout=1)
        
        if hasattr(self, 'model_loading_thread') and self.model_loading_thread and self.model_loading_thread.is_alive():
            self.model_loading_thread.join(timeout=1)
        
        if hasattr(self, 'record_thread') and self.record_thread and self.record_thread.is_alive():
            self.record_thread.join(timeout=1)
        
        # Unload model if loaded
        if hasattr(self.transcriber, 'unload_model'):
            self.transcriber.unload_model()
        
        # Clear any pending transcriptions
        while not self.transcription_queue.empty():
            try:
                self.transcription_queue.get_nowait()
            except queue.Empty:
                break

    def exit_application(self):
        self.cleanup()
        if hasattr(self, 'tray_icon'):
            self.tray_icon.hide()
        QApplication.quit()
