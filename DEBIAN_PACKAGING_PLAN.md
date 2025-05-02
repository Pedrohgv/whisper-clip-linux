# Debian Packaging Plan for whisper-clip-linux

This document outlines the steps to create the Debian packaging structure for the `whisper-clip-linux` application. **This document was written by an LLM tasked with packaging this software into a `.deb`package.**

**1. Initialize Debian Packaging Structure:**

*   Run `dh_make --createorig -s -p whisper-clip-linux_0.1` (or similar) to create the `debian/` directory and template files. This will be done in the implementation phase.

**2. Configure `debian/control`:**

*   **Purpose:** Defines package metadata and dependencies.
*   **Content:**
    ```
    Source: whisper-clip-linux
    Maintainer: Your Name <your.email@example.com> 
    Section: utils
    Priority: optional
    Build-Depends: debhelper-compat (=13), dh-python, python3-all
    Standards-Version: 4.6.2 # Or latest appropriate version
    Homepage: <Optional: Link to project repository or website>

    Package: whisper-clip-linux
    Architecture: any
    Depends: ${misc:Depends}, python3, python3-pip, python3-venv, libportaudio2, ${python3:Depends}
    Description: Whisper Clip Linux - Record audio, transcribe with Whisper, and copy to clipboard.
     This application allows users to quickly record short audio snippets using a
     keyboard shortcut, transcribe the audio using the Faster Whisper model,
     and automatically copy the transcription to the system clipboard.
     It includes a system tray icon for easy access and configuration.
    ```
    *   *(Note: Replace placeholder Maintainer info).*

**3. Create `debian/whisper-clip-linux.desktop`:**

*   **Purpose:** Defines how the application appears in desktop menus.
*   **Content:**
    ```ini
    [Desktop Entry]
    Name=Whisper Clip Linux
    Comment=Record audio, transcribe, and copy to clipboard
    Exec=/usr/bin/whisper-clip-linux-launcher
    Icon=/usr/share/whisper-clip-linux/assets/whisper_clip.png
    Terminal=false
    Type=Application
    Categories=Utility;AudioVideo;Audio;
    Keywords=whisper;transcribe;audio;clipboard;record;
    ```

**4. Create `debian/whisper-clip-linux.gschema.xml`:**

*   **Purpose:** Defines the GSettings schema for the keyboard shortcut.
*   **Content:**
    ```xml
    <?xml version="1.0" encoding="UTF-8"?>
    <schemalist>
      <schema id="org.whisper-clip-linux.shortcuts" path="/org/whisper-clip-linux/shortcuts/">
        <key name="record-shortcut" type="s">
          <default>'<Alt><Shift>R'</default> <!-- Default from main.py config -->
          <summary>Keyboard shortcut to start/stop recording</summary>
          <description>The keyboard combination used to trigger audio recording and transcription.</description>
        </key>
      </schema>
    </schemalist>
    ```

**5. Create `debian/install`:**

*   **Purpose:** Specifies which files go where in the installed system.
*   **Content:**
    ```
    # Core application files
    main.py usr/lib/whisper-clip-linux
    audio_recorder.py usr/lib/whisper-clip-linux
    whisper_client.py usr/lib/whisper-clip-linux
    custom_hotkey_listener.py usr/lib/whisper-clip-linux
    config.json usr/lib/whisper-clip-linux
    requirements.txt usr/lib/whisper-clip-linux

    # Assets
    assets/* usr/share/whisper-clip-linux/assets

    # Desktop entry and Schema
    debian/whisper-clip-linux.desktop usr/share/applications
    debian/whisper-clip-linux.gschema.xml usr/share/glib-2.0/schemas

    # Launcher script (to be created)
    debian/whisper-clip-linux-launcher usr/bin
    ```

**6. Create `debian/whisper-clip-linux-launcher` (Launcher Script):**

*   **Purpose:** A simple script to run the Python application from the virtual environment.
*   **Content:**
    ```bash
    #!/bin/bash
    # Launcher for Whisper Clip Linux

    APP_DIR="/usr/lib/whisper-clip-linux"
    VENV_DIR="$APP_DIR/venv"

    # Activate venv and run main.py
    source "$VENV_DIR/bin/activate"
    python3 "$APP_DIR/main.py" "$@"

    exit $?
    ```
*   *(Needs execute permissions)*

**7. Create `debian/postinst` (Post-Installation Script):**

*   **Purpose:** Runs after the package files are copied. Sets up the environment.
*   **Content:**
    ```bash
    #!/bin/bash
    set -e

    APP_DIR="/usr/lib/whisper-clip-linux"
    VENV_DIR="$APP_DIR/venv"
    REQ_FILE="$APP_DIR/requirements.txt"
    SCHEMA_DIR="/usr/share/glib-2.0/schemas"

    case "$1" in
        configure)
            echo "Setting up Python virtual environment for whisper-clip-linux..."
            # Create venv if it doesn't exist
            if [ ! -d "$VENV_DIR" ]; then
                python3 -m venv "$VENV_DIR"
            fi

            echo "Installing Python dependencies..."
            # Activate venv and install requirements
            source "$VENV_DIR/bin/activate"
            pip install --no-cache-dir -r "$REQ_FILE"
            deactivate

            echo "Compiling GSettings schemas..."
            if [ -x "/usr/bin/glib-compile-schemas" ]; then
                glib-compile-schemas "$SCHEMA_DIR"
            else
                echo "Warning: glib-compile-schemas not found. Schema compilation skipped." >&2
            fi

            # Set correct permissions for the launcher
            chmod +x /usr/bin/whisper-clip-linux-launcher
        ;;

        abort-upgrade|abort-remove|abort-deconfigure)
        ;;

        *)
            echo "postinst called with unknown argument \`$1'" >&2
            exit 1
        ;;
    esac

    #DEBHELPER#

    exit 0
    ```
*   *(Needs execute permissions)*

**8. Create `debian/prerm` (Pre-Removal Script):**

*   **Purpose:** Runs before package files are removed. Cleans up.
*   **Content:**
    ```bash
    #!/bin/bash
    set -e

    APP_LIB_DIR="/usr/lib/whisper-clip-linux"
    APP_SHARE_DIR="/usr/share/whisper-clip-linux"
    DESKTOP_FILE="/usr/share/applications/whisper-clip-linux.desktop"
    SCHEMA_FILE="/usr/share/glib-2.0/schemas/whisper-clip-linux.gschema.xml"
    SCHEMA_DIR="/usr/share/glib-2.0/schemas"
    LAUNCHER="/usr/bin/whisper-clip-linux-launcher"

    case "$1" in
        remove|upgrade|deconfigure)
            echo "Removing whisper-clip-linux files..."
            rm -rf "$APP_LIB_DIR"
            rm -rf "$APP_SHARE_DIR"
            rm -f "$DESKTOP_FILE"
            rm -f "$SCHEMA_FILE"
            rm -f "$LAUNCHER"

            echo "Compiling GSettings schemas after removal..."
             if [ -x "/usr/bin/glib-compile-schemas" ]; then
                glib-compile-schemas "$SCHEMA_DIR"
            else
                echo "Warning: glib-compile-schemas not found. Schema compilation skipped." >&2
            fi
        ;;

        failed-upgrade)
        ;;

        *)
            echo "prerm called with unknown argument \`$1'" >&2
            exit 1
        ;;
    esac

    #DEBHELPER#

    exit 0
    ```
*   *(Needs execute permissions)*

**9. Update `debian/rules`:**

*   Ensure it uses `dh_python3` and handles executable permissions. The default `dh $@ --with python3` should mostly suffice.

**10. Update `debian/compat`:**

*   Ensure it contains `13`.

**11. Update `debian/changelog`:**

*   Add an initial entry for version `0.1` (or the appropriate starting version).

**Visual Overview (Mermaid):**

```mermaid
graph TD
    A[Start: Project Source] --> B(Run dh_make);
    B --> C{debian/ Directory Created};
    C --> D[Configure debian/control];
    C --> E[Create debian/whisper-clip-linux.desktop];
    C --> F[Create debian/whisper-clip-linux.gschema.xml];
    C --> G[Create debian/install];
    C --> H[Create debian/whisper-clip-linux-launcher];
    C --> I[Create debian/postinst];
    C --> J[Create debian/prerm];
    C --> K[Update debian/rules];
    C --> L[Update debian/compat];
    C --> M[Update debian/changelog];
    I --> N(Set postinst executable);
    J --> O(Set prerm executable);
    H --> P(Set launcher executable);
    D & E & F & G & H & I & J & K & L & M & N & O & P --> Q{Packaging Files Ready};
    Q --> R(Build .deb Package);