# KeyTap Overlay

KeyTap Overlay is a small Windows app that shows a transparent keyboard and highlights keys as you press them.

## Download

Get the Windows app from [Releases](https://github.com/meowedmiau/KeyTap-Overlay/releases). Download `KeyTap-Overlay.exe` and double-click it to open the overlay.

## Updates

KeyTap checks for a newer release when it starts. If one is available, you can choose **Download and install**. KeyTap closes, replaces its app file, and reopens with the new version. You can also choose **Check for updates** from the gear menu. The app needs an internet connection to check GitHub, and it needs permission to write to the folder where the `.exe` is stored. Older copies without the update checker need to be updated manually from the Releases page once.

## Use the overlay

- Drag the overlay to move it.
- Click the gear button or right-click the overlay to open its menu.
- Choose a PC or laptop keyboard layout.
- Turn compact mode on to hide the navigation keys and number pad, or off to show them.
- Open **Settings** to change transparency, key colors, and font. Save your changes or cancel to discard them.
- Press the selected lock key (Shift by default) to let mouse clicks pass through the overlay. Press it again to unlock the overlay.

## Keyboard layouts

KeyTap includes US, French AZERTY, and German QWERTZ layouts in PC and laptop versions. Layouts can vary between laptop models. Some laptops do not send the Fn key to Windows, so it may appear in the layout but not light up when pressed.

## Run from source

If you downloaded the source code, install Python 3 for Windows with Tkinter, keep the project folders together, and run `main.pyw` or enter this command from the project folder:

```bat
py main.pyw
```

## Privacy

KeyTap watches key-down and key-up events to light up keys on screen. It does not save or send the text you type. Update checks contact GitHub to look for a newer release; no keyboard input is included in that request.
