# KeyTap Overlay

A small Windows app that shows a keyboard overlay and highlights keys as you press them. Choose a laptop or desktop layout, switch compact mode on or off, and customize the colors, transparency, and font.

## Run the app

When a Windows release is available, download `KeyTap-Overlay.exe` from the Releases page and double-click it. No Python installation is needed.

To run from source, install Python 3 for Windows with Tkinter, then double-click `main.pyw` or run:

```bat
py main.pyw
```

Click the gear button on the overlay to open the menu. From there, choose a keyboard layout, toggle compact mode, open Settings, or quit the app. You can also right-click the overlay to open the menu.

## Customize the appearance

Open **Settings** from the gear menu. Adjust the transparency, key text and outline colors, optional key fill, pressed-key color, and font. Use the preview to see changes as you make them. Choose **Save settings** to keep them or **Cancel** to restore the saved appearance.

## Keyboard layouts

KeyTap includes US ANSI and ISO, French AZERTY, and German QWERTZ layouts, with laptop profiles for supported layouts. Laptop profiles include an Fn marker, though many laptops do not report Fn as a separate key to Windows.

The US QWERTY laptop profile maps `Win+P` to F1 for laptops where F1 is not reported separately. Other key combinations can be added to the `chords` section of a layout.

To edit layouts, open `%APPDATA%\KeyTap-Overlay\keyboard_layouts.json` from the gear menu. Layouts use `rows` for the main keys and `right` for right-side key groups. Each key entry contains a label, scan code, and width. Save your changes and restart KeyTap Overlay to load them.

## Build the Windows app

On Windows, double-click `build_exe.bat`. It builds the executable and a zip containing the app, README, and license:

```text
dist/KeyTap-Overlay.exe
dist/KeyTap-Overlay-0.2.0-Windows.zip
```

The build uses PyInstaller. Layouts and settings are stored in `%APPDATA%\KeyTap-Overlay`, so they stay separate from the executable.

## Project files

```text
main.pyw                         App entry point
keyboard_overlay/app.py          Overlay window and menu
keyboard_overlay/keyboard_hook.py Keyboard input listener
keyboard_overlay/layouts.py       Layout loading and user data
keyboard_overlay/settings.py      Settings window and storage
data/keyboard_layouts.json        Built-in keyboard layouts
.github/workflows/release.yml     GitHub release workflow
build_exe.bat                     Windows build script
```

## Releases and updates

Pushing a version tag such as `v0.2.1` starts the GitHub Actions workflow. It builds the Windows executable and zip and attaches them to a GitHub release.

To publish an update:

1. Change the version in `VERSION`.
2. Commit and push your changes.
3. Create and push a matching tag:

   ```bat
   git tag v0.2.1
   git push origin v0.2.1
   ```

Users can download the new release and replace their existing executable. KeyTap Overlay does not currently install updates automatically.

## Privacy

KeyTap Overlay watches key-down and key-up events to highlight keys on screen. It does not save or send the text you type. Some laptops do not report the Fn key to Windows, and keyboard layouts can vary by model. You can edit a layout or contribute one for a different keyboard.

## Contributing

Custom layouts and improvements are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution instructions. KeyTap Overlay is licensed under the [MIT License](LICENSE).
