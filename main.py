from dotenv import load_dotenv
load_dotenv()
from PySide6.QtWidgets import QApplication
from audio_recorder import AudioRecorder
import json
import sys


def main():
    app = QApplication(sys.argv)

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
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
