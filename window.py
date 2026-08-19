"""Jarvis chat window (native AppKit via pyobjc).

Shows the conversation transcript, a status line, and a talk button.
All public methods are safe to call from any thread - UI mutations are
funneled onto the main thread with AppHelper.callAfter.
"""

from AppKit import (
    NSApp,
    NSApplicationDidBecomeActiveNotification,
    NSAttributedString,
    NSBackingStoreBuffered,
    NSButton,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSMakeRange,
    NSMakeRect,
    NSNotificationCenter,
    NSObject,
    NSScrollView,
    NSTextField,
    NSTextView,
    NSViewHeightSizable,
    NSViewMaxYMargin,
    NSViewMinYMargin,
    NSViewWidthSizable,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
import objc
from PyObjCTools import AppHelper

_STATES = {
    "idle": ("🎙️  Idle — press the button or ⌥ Space, then speak", "Start Listening"),
    "listening": ("🔴  Listening… press again when you're done", "Stop & Send"),
    "thinking": ("🧠  Thinking…", "Interrupt"),
    "speaking": ("🔊  Speaking…", "Interrupt"),
}

W, H = 480, 600
PAD = 16


class ChatWindow(NSObject):
    @objc.python_method
    def setup(self, on_talk):
        """Build the window. Call once from the main thread."""
        self._on_talk = on_talk
        self._reply_open = False

        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable
            | NSWindowStyleMaskResizable
        )
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, W, H), style, NSBackingStoreBuffered, False
        )
        self.window.setTitle_("Jarvis")
        self.window.setReleasedWhenClosed_(False)  # closing just hides it
        self.window.center()
        content = self.window.contentView()

        # Status line (pinned to the top)
        self.status = NSTextField.labelWithString_("")
        self.status.setFrame_(NSMakeRect(PAD, H - 38, W - 2 * PAD, 22))
        self.status.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin)
        self.status.setFont_(NSFont.systemFontOfSize_(13))
        content.addSubview_(self.status)

        # Transcript (fills the middle)
        scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(PAD, 64, W - 2 * PAD, H - 64 - 48)
        )
        scroll.setHasVerticalScroller_(True)
        scroll.setBorderType_(0)
        scroll.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        self.textview = NSTextView.alloc().initWithFrame_(
            NSMakeRect(0, 0, W - 2 * PAD, H - 64 - 48)
        )
        self.textview.setEditable_(False)
        self.textview.setRichText_(True)
        self.textview.setVerticallyResizable_(True)
        self.textview.setHorizontallyResizable_(False)
        self.textview.setAutoresizingMask_(NSViewWidthSizable)
        self.textview.textContainer().setWidthTracksTextView_(True)
        self.textview.setTextContainerInset_((6, 8))
        scroll.setDocumentView_(self.textview)
        content.addSubview_(scroll)

        # Talk button (pinned to the bottom)
        self.button = NSButton.alloc().initWithFrame_(
            NSMakeRect(PAD, 12, W - 2 * PAD, 36)
        )
        self.button.setAutoresizingMask_(NSViewWidthSizable | NSViewMaxYMargin)
        self.button.setBezelStyle_(1)  # rounded
        self.button.setTarget_(self)
        self.button.setAction_("talkClicked:")
        self.button.setKeyEquivalent_("\r")  # Return triggers it
        content.addSubview_(self.button)

        self.set_state("idle")

        # Re-show the window whenever the app is opened / activated again.
        NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self, "appActivated:", NSApplicationDidBecomeActiveNotification, None
        )
        return self

    # --- Actions / notifications (main thread) --------------------------

    def talkClicked_(self, sender):
        self._on_talk()

    def appActivated_(self, note):
        self.show()

    # --- Public API (thread-safe) ----------------------------------------

    @objc.python_method
    def show(self):
        AppHelper.callAfter(self._show)

    @objc.python_method
    def set_state(self, state: str):
        AppHelper.callAfter(self._set_state, state)

    @objc.python_method
    def add_user(self, text: str):
        """Add a 'You' entry to the transcript."""
        self._reply_open = False
        AppHelper.callAfter(self._append_header, "You", NSColor.systemBlueColor())
        AppHelper.callAfter(self._append_text, text)

    @objc.python_method
    def add_reply(self, sentence: str):
        """Add/continue a 'Jarvis' entry (called once per streamed sentence)."""
        if not self._reply_open:
            self._reply_open = True
            AppHelper.callAfter(
                self._append_header, "Jarvis", NSColor.systemPurpleColor()
            )
            AppHelper.callAfter(self._append_text, sentence)
        else:
            AppHelper.callAfter(self._append_text, " " + sentence)

    @objc.python_method
    def add_note(self, text: str):
        """Dim system note in the transcript (errors, tool use, ...)."""
        self._reply_open = False
        AppHelper.callAfter(
            self._append_attr,
            f"\n{text}\n",
            NSFont.systemFontOfSize_(11),
            NSColor.secondaryLabelColor(),
        )

    # --- Main-thread internals -------------------------------------------

    @objc.python_method
    def _show(self):
        self.window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    @objc.python_method
    def _set_state(self, state):
        label, button_title = _STATES[state]
        self.status.setStringValue_(label)
        self.button.setTitle_(button_title)

    @objc.python_method
    def _append_header(self, speaker, color):
        self._append_attr(
            f"\n{speaker}\n", NSFont.boldSystemFontOfSize_(12), color
        )

    @objc.python_method
    def _append_text(self, text):
        self._append_attr(
            text, NSFont.systemFontOfSize_(14), NSColor.labelColor()
        )

    @objc.python_method
    def _append_attr(self, text, font, color):
        s = NSAttributedString.alloc().initWithString_attributes_(
            text, {NSFontAttributeName: font, NSForegroundColorAttributeName: color}
        )
        self.textview.textStorage().appendAttributedString_(s)
        length = self.textview.string().length()
        self.textview.scrollRangeToVisible_(NSMakeRange(length, 0))
