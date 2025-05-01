from dotenv import load_dotenv
load_dotenv()
from PySide6.QtWidgets import QApplication
from audio_recorder import AudioRecorder
import json
import sys
import signal
import psutil


def handle_sigterm(signum, frame):
    """Handle SIGTERM signal by quitting application"""
    QApplication.quit()


def main():
    app = QApplication(sys.argv)
    
    # Register signal handler for clean shutdown
    signal.signal(signal.SIGTERM, handle_sigterm)

    # Load configurations from the config file
    with open('config.json', 'r') as config_file:
        config = json.load(config_file)

    # Set default values for missing keys (if you want to change it, you must change the config.json file, not here)
    default_config = {
        'model_name': 'medium',
        'shortcut': 'alt+shift+r',
        'notify_clipboard_saving': True
    }
    config = {**default_config, **config}

    window = AudioRecorder(**config)
    window.show()
    
    # Ensure process terminates completely
    ret = app.exec()
    process = psutil.Process()
    for child in process.children(recursive=True):
        child.kill()
    sys.exit(ret)


if __name__ == "__main__":
    main()
