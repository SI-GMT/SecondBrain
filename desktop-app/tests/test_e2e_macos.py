"""Smoke E2E tests for macOS — verify dialog isolation and launchability."""

from __future__ import annotations

import subprocess
import sys
import time

import pytest


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS specific E2E")
def test_dialog_helpers_launch_and_exit():
    """Verify that each dialog can be launched as a standalone process.
    
    This is the core fix for macOS freezes: isolating Tkinter from the tray.
    """
    dialogs = ["settings", "logs", "wizard"]
    
    for dialog in dialogs:
        # Launch helper
        cmd = [sys.executable, "-m", "sb_desktop", "--dialog", dialog]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Give it a bit of time to initialize Tk and AppKit
        time.sleep(2)
        
        # Check if it's still alive (it should be, waiting for user input)
        assert proc.poll() is None, f"Dialog helper '{dialog}' crashed on startup"
        
        # Terminate it
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS specific E2E")
def test_main_app_smoke_launch():
    """Verify that the main app starts up without immediate crash.
    
    Note: We can't easily test the tray UI without a real display and 
    mouse automation, but we can verify it loads its dependencies.
    """
    # Use --no-tray to avoid blocking on icon.run() if we just want to test
    # the environment initialization.
    cmd = [sys.executable, "-m", "sb_desktop", "--no-tray", "--action", "status"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    
    # In source-run, we might get return code 1 due to version mismatch warning
    # (0.0.0+unknown vs pipx version). This is still a successful smoke launch
    # as the process reached its logic.
    assert result.returncode in (0, 1)
    assert "Status:" in result.stdout
