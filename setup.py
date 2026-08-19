"""py2app build config for Jarvis.app.

Alias mode (-A) makes the bundle symlink back to this folder, so code
edits apply on next launch without rebuilding. Used by build_app.sh.
"""

from setuptools import setup

setup(
    app=["app.py"],
    name="Jarvis",
    options={
        "py2app": {
            "argv_emulation": False,
            "iconfile": "jarvis.icns",
            "plist": {
                "CFBundleName": "Jarvis",
                "CFBundleDisplayName": "Jarvis",
                "CFBundleIdentifier": "local.matt.jarvis",
                "CFBundleShortVersionString": "1.0",
                "NSMicrophoneUsageDescription": (
                    "Jarvis listens to you (or system audio) so it can respond."
                ),
            },
        }
    },
    setup_requires=["py2app"],
)
