# KeyTap Overlay

A small Windows desktop app that shows a transparent keyboard and lights keys while they are pressed. Layouts and appearance settings are editable; the app uses only Python's standard library at runtime.

## Run from source

1. Install Python 3 for Windows with Tkinter enabled.
2. Keep the project folders together as downloaded.
3. Double-click `main.pyw`, or open a terminal here and run `py main.pyw`.
4. Click the small gear button on the overlay, or right-click it, to select a PC or Laptop layout, turn compact mode on or off, open Settings, or quit.

The first launch copies editable layouts and settings into `%APPDATA%\KeyTap-Overlay`. This keeps personal changes separate from the bundled defaults and works when the app is packaged as an executable. Existing Keyboard Overlay preferences are carried over.

## Settings

Open **Settings…** from the gear menu. The window has a live key preview and continuous sliders; changes appear on the overlay as you adjust them and are only saved when you choose **Save settings**. Choose **Cancel** to restore the saved appearance.

You can adjust overall transparency, key label and outline colors, optional key fill, pressed-key highlight color, and any font family installed on the computer.

## Layouts and laptop keys

The bundled presets include US ANSI/ISO, French AZERTY, German QWERTZ, and laptop versions. Laptop profiles show an Fn marker. Many laptops do not send Fn as a separate Windows key event, so the marker may not light. Its position is controlled by `fn_after` in the layout definition.

The **US QWERTY (Laptop, Win+P lights F1)** profile maps that shortcut to F1. Other key combinations can be added in the layout's `chords` section. Windows scan codes identify physical positions; active input-language labels can be used for character keys.

Users can edit `%APPDATA%\KeyTap-Overlay\keyboard_layouts.json` from the gear menu. `rows` describes the main keys, `right` describes right-side clusters, and each key is `[label, scan_code, width]`. Copy a similar preset, change its name and rows, save, and restart.

## Project structure

```text
main.pyw                         Application entry point
keyboard_overlay/app.py          Overlay UI and event display
keyboard_overlay/keyboard_hook.py Windows keyboard event listener
keyboard_overlay/layouts.py      Layout loading and user data
keyboard_overlay/settings.py     Settings window and persistence
data/keyboard_layouts.json       Built-in keyboard presets
.github/workflows/release.yml    Tagged GitHub release build
build_exe.bat                    Local Windows build
```

## Build the Windows executable

On Windows, double-click `build_exe.bat`. It installs the pinned packaging tool into the project-local `.build-tools` folder, builds a single executable, and creates a zip containing the executable, README, and license:

```text
dist/KeyTap-Overlay.exe
dist/KeyTap-Overlay-0.2.0-Windows.zip
```

The one-file, windowed build lets users put `KeyTap-Overlay.exe` on their Desktop and double-click it without opening a console. The bundled layout data is included in the executable, while editable layouts and settings stay in AppData. See the [PyInstaller documentation](https://pyinstaller.org/en/stable/usage.html).

## Publish releases and push updates

The GitHub Actions workflow in `.github/workflows/release.yml` builds and publishes a release whenever a `v` version tag is pushed. The app is named **KeyTap Overlay**. Since other keyboard-related projects use “KeyTap,” `keytap-overlay` is the clearer repository name. To publish an update:

1. Update `VERSION`, for example to `0.2.1`.
2. Commit and push the changes to GitHub.
3. Create and push the matching tag: `git tag v0.2.1`, then `git push origin v0.2.1`.
4. GitHub Actions builds the `.exe` and zip, then attaches both to the GitHub Release.

Users download each new release and replace the old executable. The app does not yet check for or install updates automatically. Releases are based on version tags and can include downloadable files; see [GitHub's release guide](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases) and [`gh release create`](https://cli.github.com/manual/gh_release_create).

## Notes

The keyboard hook observes key-down and key-up events locally. It does not save or transmit typed text. Fn behavior and physical key geometry vary by model, so users can contribute custom layouts instead of requiring a device-model catalog.
