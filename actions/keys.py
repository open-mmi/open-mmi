#import threading
from evdev import UInput, ecodes as e

# Singleton persistent virtual keyboard with required key capabilities
_caps = {e.EV_KEY: [
    e.KEY_PLAYPAUSE, e.KEY_NEXTSONG, e.KEY_PREVIOUSSONG, e.KEY_STOPCD,
    e.KEY_MUTE, e.KEY_VOLUMEUP, e.KEY_VOLUMEDOWN, e.KEY_LEFT, e.KEY_RIGHT
]}
#_ui = None
_ui = UInput(_caps, name="canbusd-input")
#_lock = threading.Lock()

def _get_ui():
    return _ui
 #   global _ui
  #  with _lock:
   #     if _ui is None:
    #        _ui = UInput(_caps, name="canbusd-media-keys")
   #     return _ui

def _press(code):
    ui = _get_ui()
    ui.write(e.EV_KEY, code, 1)
    ui.write(e.EV_KEY, code, 0)
    ui.syn()

def play_pause():     _press(e.KEY_PLAYPAUSE)
def next_track():     _press(e.KEY_NEXTSONG)
def prev_track():     _press(e.KEY_PREVIOUSSONG)
def stop():           _press(e.KEY_STOPCD)
def mute_toggle():    _press(e.KEY_MUTE)
def volume_up():      _press(e.KEY_VOLUMEUP)
def volume_down():    _press(e.KEY_VOLUMEDOWN)
def arrow_left():     _press(e.KEY_LEFT)
def arrow_right():    _press(e.KEY_RIGHT)