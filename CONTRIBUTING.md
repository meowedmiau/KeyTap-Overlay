# Contributing to KeyTap Overlay

Keyboard layouts belong in `data/keyboard_layouts.json`. Add a named profile with its keyboard group (`PC` or `Laptop`), main `rows`, and optional right-side `right` clusters. Keep scan codes in hexadecimal and include the language and physical shape in the profile name. For laptop profiles, set `fn_after` to the position where the Fn marker belongs. Add a `chords` mapping only when a device reports a shortcut in place of a standard key.

Appearance settings belong in `keyboard_overlay/settings.py`; the overlay UI belongs in `keyboard_overlay/app.py`; Windows key listening belongs in `keyboard_overlay/keyboard_hook.py`. Keep user preferences and user-edited layouts in AppData rather than changing the bundled defaults at runtime.

Layout contributions should mention the keyboard language and whether the shape is ANSI or ISO.
