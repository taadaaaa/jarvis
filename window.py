"""Jarvis Command Center window: a WKWebView rendering ui/index.html.

The dashboard is plain HTML/CSS/JS. Python drives it by calling the JS
API (J.setState, J.addUser, ...); the page talks back through the
'jarvis' script message handler (talk button, quick commands).

Public API matches the old AppKit window: show / set_state / add_user /
add_reply / add_note (+ add_tool, set_info). Thread-safe.
"""

import json
import os
import threading
import time

import objc
from AppKit import (
    NSApp,
    NSApplicationDidBecomeActiveNotification,
    NSBackingStoreBuffered,
    NSMakeRect,
    NSNotificationCenter,
    NSObject,
    NSURL,
    NSViewHeightSizable,
    NSViewWidthSizable,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from PyObjCTools import AppHelper
from WebKit import WKUserContentController, WKWebView, WKWebViewConfiguration

W, H = 1240, 760
UI_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "index.html")


class ChatWindow(NSObject):
    @objc.python_method
    def setup(self, on_talk, on_command=None):
        """Build the window. Call once from the main thread.

        on_talk: toggle listening. on_command(cmd, target): 'interrupt',
        'clear', 'handsfree', 'brain' (target = model/provider name).
        """
        self._on_talk = on_talk
        self._on_command = on_command or (lambda cmd, target=None: None)

        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable
            | NSWindowStyleMaskResizable
        )
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, W, H), style, NSBackingStoreBuffered, False
        )
        self.window.setTitle_("Jarvis Command Center")
        self.window.setReleasedWhenClosed_(False)  # closing just hides it
        self.window.setMinSize_((980, 620))
        self.window.center()

        controller = WKUserContentController.alloc().init()
        controller.addScriptMessageHandler_name_(self, "jarvis")
        config = WKWebViewConfiguration.alloc().init()
        config.setUserContentController_(controller)
        self.webview = WKWebView.alloc().initWithFrame_configuration_(
            self.window.contentView().bounds(), config
        )
        self.webview.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        url = NSURL.fileURLWithPath_(UI_PATH)
        self.webview.loadFileURL_allowingReadAccessToURL_(
            url, url.URLByDeletingLastPathComponent()
        )
        self.window.contentView().addSubview_(self.webview)

        # Re-show the window whenever the app is opened / activated again.
        NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self, "appActivated:", NSApplicationDidBecomeActiveNotification, None
        )
        return self

    # --- JS -> Python -----------------------------------------------------

    def userContentController_didReceiveScriptMessage_(self, controller, message):
        body = message.body() or {}
        cmd = body.get("cmd")
        if cmd == "toggle":
            self._on_talk()
        elif cmd:
            self._on_command(cmd, body.get("target"))

    def appActivated_(self, note):
        self.show()

    # --- Python -> JS (thread-safe) ----------------------------------------

    @objc.python_method
    def _js(self, code):
        AppHelper.callAfter(
            self.webview.evaluateJavaScript_completionHandler_, code, None
        )

    @objc.python_method
    def show(self):
        AppHelper.callAfter(self._show)

    @objc.python_method
    def _show(self):
        self.window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    @objc.python_method
    def set_state(self, state: str):
        self._js(f"J.setState({json.dumps(state)})")

    @objc.python_method
    def add_user(self, text: str):
        self._js(f"J.addUser({json.dumps(text)})")

    @objc.python_method
    def add_reply(self, sentence: str):
        self._js(f"J.addReply({json.dumps(sentence)})")

    @objc.python_method
    def add_tool(self, text: str):
        self._js(f"J.addTool({json.dumps(text)})")

    @objc.python_method
    def add_note(self, text: str):
        self._js(f"J.addNote({json.dumps(text)})")

    @objc.python_method
    def set_info(self, info: dict):
        self._js(f"J.setInfo({json.dumps(info)})")

    @objc.python_method
    def set_handsfree(self, on: bool):
        self._js(f"J.setHandsfree({json.dumps(bool(on))})")

    @objc.python_method
    def start_stats(self):
        """Push CPU/RAM/disk stats to the dashboard every few seconds."""
        try:
            import psutil
        except ImportError:
            return

        def loop():
            while True:
                stats = {
                    "cpu": psutil.cpu_percent(interval=1),
                    "ram": psutil.virtual_memory().percent,
                    "disk": psutil.disk_usage("/").percent,
                }
                self._js(f"J.setStats({json.dumps(stats)})")
                time.sleep(3)

        threading.Thread(target=loop, daemon=True).start()
