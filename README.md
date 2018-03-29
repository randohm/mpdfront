# mpdfront
MPD front end, with the goal of being able to use a keyboard for complete control.
Using all keys will more easily translate to use with a remote control.
The idea is that this will be the head on headless MPD in a home theater setup where the user can see the information up on the big screen.

The app will attempt to get album art from the media file first, then look for cover.{jpg,png}, then attempt to fetch from Last.fm. 
API keys are required to fetch from Last.fm


## Required libraries:

- [musicpd](https://pypi.python.org/pypi/python-musicpd) MPD client library
- [PyGObject](http://pygobject.readthedocs.io/en/latest/index.html) using:
    - Gtk
    - Gdk
    - GdkPixbuf
    - Pango
    - GObject
- [Mutagen](https://mutagen.readthedocs.io/en/latest/) Audio file tags library
- [pylast](https://github.com/pylast/pylast) Last.fm API library

## Current Status

Working fairly well. Still a few bugs and TODOs left.
