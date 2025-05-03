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
from pathlib import Path # Use pathlib for easier path handling
from whisper_client import WhisperClient
import platform
import sys


# Define standard paths based on typical Linux installation
APP_NAME = "whisper-clip-linux"
# Use user's cache directory for temporary audio files
CACHE_DIR = Path(os.path.expanduser('~')) / ".cache" / APP_NAME
# Define the installation path for shared assets
ASSETS_DIR = Path("/usr/share") / APP_NAME / "assets"


class AudioRecorder(QMainWindow):
    def __init__(self, model_name="medium.en", shortcut="alt+shift+r", notify_clipboard_saving=True):
        super().__init__()
        self.system_platform = platform.system()
        # Use the cache directory for output
        self.output_folder = CACHE_DIR
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
        self.transcription_thread.daemon = True
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
        self.model_loading_thread.daemon = True
        self.model_loading_thread.start()

        # Start recording immediately
        self.record_thread = threading.Thread(target=self.record_audio)
        self.record_thread.daemon = True
        self.record_thread.start()

    def stop_recording(self):
        self.is_recording = False
        self.record_button.setStyleSheet("font-size: 24px; background-color: white;")
        sd.stop()
        if self.record_thread: # Ensure thread exists before joining
             self.record_thread.join()

        if self.recordings:
            audio_data = np.concatenate(self.recordings)
            audio_data = (audio_data * 32767).astype(np.int16)
            # Ensure the cache directory exists
            self.output_folder.mkdir(parents=True, exist_ok=True)
            # Use Path object for filename construction
            filename = self.output_folder / f"audio_{int(time.time())}.wav"
            try:
                write(filename, 44100, audio_data)
                self.recordings = []
                self.transcription_queue.put((str(filename), self.model_loading_thread)) # Pass filename as string
            except Exception as e:
                print(f"Error saving audio file to {filename}: {e}", file=sys.stderr)
                # Handle error appropriately, maybe notify user
                # Ensure model is unloaded if saving fails
                if self.model_loading_thread and self.model_loading_thread.is_alive():
                    self.model_loading_thread.join()
                    self.transcriber.unload_model()

        else:
            print("No audio data recorded. Please check your audio input device.")
            # If no audio was recorded, wait for model loading and unload it
            if self.model_loading_thread and self.model_loading_thread.is_alive():
                self.model_loading_thread.join()
                self.transcriber.unload_model()

    def play_notification_sound(self):
        # Use absolute path from ASSETS_DIR
        sound_file = ASSETS_DIR / 'saved-on-clipboard-sound.wav'

        if not sound_file.exists():
             print(f"Notification sound not found: {sound_file}", file=sys.stderr)
             return

        sound_file_str = str(sound_file) # Convert Path to string for commands

        if self.system_platform == 'Windows':
            import winsound
            winsound.PlaySound(sound_file_str, winsound.SND_FILENAME)
        elif self.system_platform == 'Darwin':  # MacOS
            os.system(f'afplay "{sound_file_str}"') # Quote path for safety
        elif self.system_platform == 'Linux':   # Linux
            # Check for paplay first, fallback to aplay
            if os.system("command -v paplay > /dev/null") == 0:
                os.system(f'paplay "{sound_file_str}"')
            elif os.system("command -v aplay > /dev/null") == 0:
                 os.system(f'aplay "{sound_file_str}"')
            else:
                 print("Could not find paplay or aplay to play notification sound.", file=sys.stderr)
        else:
            print(f'Unsupported platform for sound notification. System: {self.system_platform}', file=sys.stderr)


    def process_transcriptions(self):
        while self.keep_transcribing:
            try:
                filename_str, loading_thread = self.transcription_queue.get(timeout=1)

                # Wait for model to be ready if it's still loading
                if loading_thread and loading_thread.is_alive():
                    self.model_ready.wait()  # Wait for model loading to complete

                transcription = self.transcriber.transcribe(filename_str)
                print(f"Transcription for {filename_str}:", transcription)
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
            except Exception as e: # Catch potential errors during transcription/cleanup
                 print(f"Error during transcription processing: {e}", file=sys.stderr)
                 # Ensure model is unloaded even if error occurs
                 if hasattr(self.transcriber, 'model') and self.transcriber.model is not None:
                      self.transcriber.unload_model()
                 self.model_ready.clear()


    def closeEvent(self, event):
        # Minimize to tray instead of closing
        if self.tray_icon.isVisible():
            self.hide()
            event.ignore()
        else:
            self.cleanup()
            self.exit_application()

    def record_audio(self):
        try:
            with sd.InputStream(callback=self.audio_callback, channels=1, samplerate=44100): # Explicit samplerate
                while self.is_recording:
                    sd.sleep(100) # Shorter sleep interval
        except sd.PortAudioError as e:
            print(f"Audio input error: {e}", file=sys.stderr)
            # Handle error, maybe disable recording button and notify user
            self.is_recording = False # Stop recording state
            self.record_button.setStyleSheet("font-size: 24px; background-color: gray;") # Indicate error state
            self.record_button.setEnabled(False)


    def audio_callback(self, indata, frames, time, status):
        if status:
            print(f"Audio callback status: {status}", file=sys.stderr)
        self.recordings.append(indata.copy())

    def setup_global_shortcut(self):
        # Create Qt shortcut
        key_sequence = QKeySequence(self.shortcut)
        self.shortcut = QShortcut(key_sequence, self)
        self.shortcut.activated.connect(self.toggle_recording)

    def setup_system_tray(self):
        self.tray_icon = QSystemTrayIcon(self)

        # Load icon using absolute path from ASSETS_DIR
        icon_path = ASSETS_DIR / 'whisper_clip.png'
        if icon_path.exists():
            self.tray_icon.setIcon(QIcon(str(icon_path)))
        else:
            print(f"Icon file not found at: {icon_path}", file=sys.stderr)
            # Fallback to default window icon if available
            default_icon = QApplication.windowIcon()
            if not default_icon.isNull():
                 self.tray_icon.setIcon(default_icon)
            # else: provide a very basic fallback or no icon

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
        print("Cleaning up resources...")
        # Stop any active recording
        if self.is_recording:
            print("Stopping active recording...")
            self.stop_recording()

        # Release audio resources
        print("Stopping sounddevice...")
        sd.stop()

        # Clean up threads
        print("Stopping transcription thread...")
        self.keep_transcribing = False
        if hasattr(self, 'transcription_thread') and self.transcription_thread.is_alive():
            self.transcription_thread.join(timeout=2) # Increased timeout
            if self.transcription_thread.is_alive():
                 print("Warning: Transcription thread did not exit cleanly.", file=sys.stderr)


        if hasattr(self, 'model_loading_thread') and self.model_loading_thread and self.model_loading_thread.is_alive():
             print("Waiting for model loading thread...")
             self.model_loading_thread.join(timeout=2)
             if self.model_loading_thread.is_alive():
                  print("Warning: Model loading thread did not exit cleanly.", file=sys.stderr)


        if hasattr(self, 'record_thread') and self.record_thread and self.record_thread.is_alive():
             print("Waiting for recording thread...")
             self.record_thread.join(timeout=2)
             if self.record_thread.is_alive():
                  print("Warning: Recording thread did not exit cleanly.", file=sys.stderr)


        # Unload model if loaded
        print("Unloading Whisper model...")
        if hasattr(self.transcriber, 'unload_model'):
            self.transcriber.unload_model()

        # Clear any pending transcriptions
        print("Clearing transcription queue...")
        while not self.transcription_queue.empty():
            try:
                filename_str, _ = self.transcription_queue.get_nowait()
                # Optionally remove the temporary audio file during cleanup too
                try:
                    if os.path.exists(filename_str):
                         os.remove(filename_str)
                except OSError as e:
                    print(f"Error removing temporary file {filename_str} during cleanup: {e}", file=sys.stderr)

            except queue.Empty:
                break
            except Exception as e:
                 print(f"Error clearing queue item: {e}", file=sys.stderr)
        print("Cleanup finished.")


    def exit_application(self):
        self.cleanup()
        if hasattr(self, 'tray_icon'):
            self.tray_icon.hide()
        QApplication.quit()
