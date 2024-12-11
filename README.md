# mpdfront
MPD front end written in Python, with the goal of being able to use a keyboard for complete control.
Using all keys will more easily translate to use with a remote control.
This is meant to be the head on headless MPD in a home theater setup where the user can see the information on a big screen.

The app will attempt to get album art from the media file first, then look for a file named cover.{jpg,png} in the music directory.

## Required libraries:

- [musicpd](https://pypi.python.org/pypi/python-musicpd) MPD client library
- [PyGObject](http://pygobject.readthedocs.io/en/latest/index.html) using:
    - Gtk
    - Gdk
    - GdkPixbuf
    - Pango
    - GObject
    - GLib
- [Mutagen](https://mutagen.readthedocs.io/en/latest/) Audio file tags library
- [Pillow](http://pillow.readthedocs.io/en/latest/) Image library

## Current Status

Working fairly well. 
Ported to GTK4. 
Still a few bugs and TODOs left.

## Usage

```
usage: mpdfront [-h] [-c CONFIG]

MPD Frontend

optional arguments:
  -h, --help           show this help message and exit
  -v, --verbose        Turn on verbose output. (default: False)
  -H, --host HOST      Remote host name or IP address. (default: None)
  -p, --port PORT      Remote TCP port number. (default: None)
  -s, --css CSS        CSS file for the Gtk App. (default: None)
  -c, --config CONFIG  Config file. (default: ~/.config/mpdfront/mpdfront.cfg)
```
A config file is required, whether it is passed as an argument or in the default location: ```~/.config/mpdfront/mpdfront.cfg```.
The config file is in ini format.

### Config File Sample
```
[main]
fullscreen=no
width=1920
height=1080
host=localhost
port=6600
style=style.css
music_dir=/music_dir
sound_card=0
sound_device=0
logger_config=logging.yml
resize=no
decorations=no

[keys]
playpause=p
stop=u
cue=l
rewind=k
next=o
previous=i
info=w
outputs=e
options=r
cardselect=t
browser=1
playlist=2
toggle_main=3
toggle_bottom=4
delete=d
moveup=a
movedown=s
```

### Config File Details
#### main section
- fullscreen, width, height: fullscreen overrides width and height if set to "yes". Otherwise the app is set to width x height.
- host: the MPD host
- port: the MPD port, normally 6600
- style: path to CSS file
- music_dir: root music directory, normally set to the same as ```music_directory``` in mpd.conf
- sound_card, sound_device: sound output device identifiers. ALSA device hw:2,1 would have sound_card=2, sound_device=1
- logger_config: path to YML config for Python logging.
- resize: yes/no for setting the window to be resizable
- decorations: yes/no for setting window decorations, *ie. title bar, window frame* 

#### keys section
- playpause: key to toggle play/pause
- stop: key to stop playback
- cue: jumps ahead in the song
- rewind: jumps back in the song
- next: next track in playlist
- previous: to the beginning of the current song, or to the previoud track in the playlist
- info: shows the song info dialog
- outputs: shows the outputs dialog
- options: shows the options dialog
- browser: set focus on the browser
- playlist: sets focus on the playlist
- toggle_main: rotates widgets to full and split screen
- toggle_bottom: rotates bottom widgets to full and split screen
- delete: delete track in playlist
- moveup: move track up in playklist
- movedown: move track down in playlist
