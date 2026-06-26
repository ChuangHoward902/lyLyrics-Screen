# lyLyrics screen

An Electron + Python desktop app that reads Spotify playback, looks up synced lyrics, renders a Spotify-style lyric animation, and sends frames directly to a Thermalright USB LCD.

## Setup

1. Install Node dependencies:

   ```bash
   npm install
   ```

2. Install the Python bridge dependencies:

   ```bash
   python -m pip install -r requirements-lcd.txt
   ```

3. Create a Spotify app in the Spotify Developer Dashboard.
4. Add this redirect URI:

   `http://127.0.0.1:17321/callback`

5. Run the app:

   ```bash
   npm start
   ```

   Or double-click `start-lyric-screen.vbs` for a hidden launcher with no console window.

## Build

Create the Windows installer:

```bash
npm run dist
```

The installer is written to `dist/lyLyrics screen-0.1.0-x64.exe`.

The packaged app still uses the local Python runtime for direct LCD output, so install the bridge dependencies on the target PC:

```bash
python -m pip install -r requirements-lcd.txt
```

## What it does

- Connects to Spotify with PKCE OAuth
- Reads the currently playing track
- Looks up synced lyrics from LRCLIB
- Renders centered lyrics for the detected LCD profile
- Sends frames to the `87AD:70DB` Thermalright LCD over USB bulk

## Notes

- The current bridge targets the `USBDISPLAY` device with `VID 87AD` and `PID 70DB`.
- If another app is already holding the LCD, the bridge will log access denied and keep retrying.
- If you see access denied even with no other RGB/LCD app open, try launching the app as Administrator.
- Use `start-lyric-screen.vbs` instead of the `.bat` if you want to avoid the console window.
