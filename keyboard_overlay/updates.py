"""Check GitHub Releases and stage an accepted Windows app update."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlparse
import urllib.request

REPOSITORY = "meowedmiau/KeyTap-Overlay"
MAX_DOWNLOAD_SIZE = 100 * 1024 * 1024


def _resource_root():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def current_version():
    return (_resource_root() / "VERSION").read_text(encoding="utf-8").strip()


def _version_tuple(value):
    match = re.fullmatch(r"v?(\d+(?:\.\d+){1,3})", value.strip())
    if not match:
        raise ValueError(f"Unrecognized version number: {value}")
    return tuple(int(part) for part in match.group(1).split("."))


def check_latest_release():
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPOSITORY}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "KeyTap-Overlay"},
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        release = json.loads(response.read(1024 * 1024).decode("utf-8"))

    latest = release.get("tag_name", "")
    if _version_tuple(latest) <= _version_tuple(current_version()):
        return None

    asset = next((item for item in release.get("assets", [])
                  if item.get("name") == "KeyTap-Overlay.exe"), None)
    if not asset:
        raise RuntimeError("The latest release does not include KeyTap-Overlay.exe yet.")
    return {
        "version": latest.removeprefix("v"),
        "url": asset["browser_download_url"],
        "release_url": release.get("html_url", f"https://github.com/{REPOSITORY}/releases/latest"),
        "size": int(asset.get("size", 0)),
    }


def _download_update(release):
    if release["size"] > MAX_DOWNLOAD_SIZE:
        raise RuntimeError("The update file is larger than expected.")
    app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    update_folder = app_data / "KeyTap-Overlay" / "updates"
    update_folder.mkdir(parents=True, exist_ok=True)
    download = update_folder / "KeyTap-Overlay-update.exe"
    request = urllib.request.Request(release["url"], headers={"User-Agent": "KeyTap-Overlay"})
    with urllib.request.urlopen(request, timeout=30) as response, download.open("wb") as output:
        final_host = urlparse(response.geturl()).hostname or ""
        if final_host not in {"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"}:
            raise RuntimeError("The update download did not come from GitHub.")
        first_bytes = response.read(2)
        if first_bytes != b"MZ":
            raise RuntimeError("The downloaded update is not a Windows executable.")
        output.write(first_bytes)
        total = len(first_bytes)
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_DOWNLOAD_SIZE:
                raise RuntimeError("The update file is larger than expected.")
            output.write(chunk)
    if release["size"] and total != release["size"]:
        download.unlink(missing_ok=True)
        raise RuntimeError("The downloaded update size does not match the release file.")
    return download


def download_and_launch_update(release):
    if not getattr(sys, "frozen", False):
        return "source"
    target = Path(sys.executable).resolve()
    try:
        descriptor, test_file = tempfile.mkstemp(prefix=".keytap-write-check-", dir=target.parent)
        os.close(descriptor)
        Path(test_file).unlink()
    except OSError as exc:
        raise RuntimeError(
            "KeyTap cannot update in this folder. Move the app to a folder you can write to, "
            "such as your Desktop, then try again."
        ) from exc
    download = _download_update(release)
    app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    script = app_data / "KeyTap-Overlay" / "updates" / "apply-update.ps1"
    script.write_text(
        "param([string]$Target, [string]$Download)\n"
        "$ErrorActionPreference = 'Stop'\n"
        "$AppName = [IO.Path]::GetFileNameWithoutExtension($Target)\n"
        "do {\n"
        "  $Running = Get-Process -Name $AppName -ErrorAction SilentlyContinue | Where-Object { $_.Path -ieq $Target }\n"
        "  if ($Running) { Start-Sleep -Milliseconds 300 }\n"
        "} while ($Running)\n"
        "$Staged = $Target + '.keytap-new'\n"
        "$Backup = $Target + '.keytap-old'\n"
        "try {\n"
        "  if (Test-Path -LiteralPath $Backup) { Remove-Item -LiteralPath $Backup -Force }\n"
        "  Copy-Item -LiteralPath $Download -Destination $Staged -Force\n"
        "  Move-Item -LiteralPath $Target -Destination $Backup -Force\n"
        "  Move-Item -LiteralPath $Staged -Destination $Target -Force\n"
        "} catch {\n"
        "  if (Test-Path -LiteralPath $Backup) {\n"
        "    if (Test-Path -LiteralPath $Target) { Remove-Item -LiteralPath $Target -Force }\n"
        "    Move-Item -LiteralPath $Backup -Destination $Target -Force\n"
        "  }\n"
        "  Add-Type -AssemblyName PresentationFramework\n"
        "  [System.Windows.MessageBox]::Show('The update could not be installed. Your previous app was restored. You can download the update from the KeyTap Overlay Releases page.', 'KeyTap Overlay') | Out-Null\n"
        "  Start-Process 'https://github.com/meowedmiau/KeyTap-Overlay/releases/latest'\n"
        "  exit 1\n"
        "}\n"
        "Start-Process -FilePath $Target\n"
        "Remove-Item -LiteralPath $Backup -Force -ErrorAction SilentlyContinue\n"
        "Remove-Item -LiteralPath $Download -Force -ErrorAction SilentlyContinue\n",
        encoding="utf-8",
    )
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
         str(target), str(download)],
        creationflags=flags,
        close_fds=True,
    )
    return "installing"
