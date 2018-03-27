# mpdfront
MPD front end, with the goal of being able to use a keyboard for complete control.
Using all keys will more easily translate to use with a remote control.
The idea is that this will be the head on headless MPD in a home theater setup where the user can see the information up on the big screen.


## Required libraries:

- [musicpd](https://pypi.python.org/pypi/python-musicpd) MPD client library
- [PyGObject](http://pygobject.readthedocs.io/en/latest/index.html) using:
    - Gtk
    - Gdk
    - GdkPixbuf
    - Pango
    - GObject
- [Mutagen](https://mutagen.readthedocs.io/en/latest/) Audio file tags library

## Current Status

Working fairly well. Still a few bugs and TODOs left.
