#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Music Player Daemon Frontend. Adds a head to headless MPD.
"""

import sys, re, time, os, cgi, io
import argparse
import logging
import threading
import configparser
import requests
import imghdr
import PIL
from PIL import Image
import musicpd
import pylast
import mutagen
from mutagen.id3 import ID3, APIC
from mutagen.flac import FLAC
from mutagen.dsf import DSF
from mutagen.mp4 import MP4
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GObject, Pango, GLib



## Global logger
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s %(levelname)s %(threadName)s(%(thread)d)::%(funcName)s(%(lineno)d): %(message)s")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
log.addHandler(handler)

## symbols for playback control button labels
symbol_previous = chr(9612)+chr(9664)
symbol_rewind = chr(9664)+chr(9664)
symbol_stop = chr(9608)
symbol_play= chr(9613)+chr(9654)
symbol_pause = chr(9613)+chr(9613)
symbol_cue = chr(9654)+chr(9654)
symbol_next = chr(9654)+" "+chr(9612)

## window and app defaults
default_window_width = 1920
default_window_height = 1080
default_mpd_host = "localhost"
default_mpd_port = 6600
default_css_file = "style.css"
default_root_dir = "/"
default_card_id = 0
default_device_id = 0
default_config_file = os.environ['HOME']+"/.mpdfront.cfg"



def listbox_cmp(row1, row2, data, notify_destroy):
    """
    Compare function for Gtk.ListBox sorting. Does a simple string cmp on the rows' text
    Args:
        Standard args for Gtk.ListBox sort compare function.
    """
    return row1.get_child().get_text() > row2.get_child().get_text()



def listbox_cmp_filtered(row1, row2, data, notify_destroy):
    """
    Compare function for Gtk.ListBox sorting. Modifies the text before comparison.
    Removes from text: /^The /
    Args:
        Standard args for Gtk.ListBox sort compare function.
    """
    row1_value = re.sub(r'^The ', '', row1.get_child().get_text(), re.IGNORECASE)
    row2_value = re.sub(r'^The ', '', row2.get_child().get_text(), re.IGNORECASE)

    return row1_value > row2_value



def listbox_cmp_by_track(row1, row2, data, notify_destroy):
    """
    Compare function for Gtk.ListBox sorting. Modifies the text before comparison.
    Removes from text: /^The /
    Args:
        Standard args for Gtk.ListBox sort compare function.
    """
    row1_value = int(row1.get_child().data['track'])
    row2_value = int(row2.get_child().data['track'])

    return row1_value > row2_value



def pp_time(secs):
    """
    Pretty-print time convenience function. Takes a count of seconds and formats to MM:SS.

    Args:
        secs: int of number of seconds

    Returns:
        string with the time in the format of MM:SS
    """
    return "%d:%02d" % (int(int(secs)/60), int(secs)%60)



class SongInfoDialog(Gtk.MessageDialog):
    """
    Shows a MessageDialog with song tags and information.
    Click OK to exit.
    """
    def __init__(self, parent, song):
        """
        Build markup text to display, display markup text
        """
        Gtk.MessageDialog.__init__(self, parent, Gtk.DialogFlags.MODAL, Gtk.MessageType.INFO, Gtk.ButtonsType.OK)
        song_text = ""
        if 'title' in song:
            song_text += "<span weight='ultrabold' size='xx-large'>%s</span>\n" % cgi.escape(song['title'])
        if 'artist' in song:
            song_text += "Artist: <span weight='bold' size='x-large'>%s</span>\n" % cgi.escape(song['artist'])
        if 'album' in song:
            song_text += "Album: <span weight='bold' size='large'>%s</span>\n" % cgi.escape(song['album'])
        if 'time' in song:
            song_text += "Time: %s\n" % cgi.escape(pp_time(song['time']))
        if 'track' in song:
            song_text += "Track: %s\n" % cgi.escape(song['track'])
        if 'date' in song:
            song_text += "Date: %s\n" % cgi.escape(song['date'])
        if 'genre' in song:
            song_text += "Genre: %s\n" % cgi.escape(song['genre'])

        if song_text == "":
            song_text = "File: %s" % cgi.escape(song['file'])
        else:
            song_text += "File: <small>%s</small>" % cgi.escape(song['file'])

        self.set_name("song-info")
        self.set_markup(song_text)
        self.get_content_area().set_size_request(300, 300)
        style_context = self.get_style_context()
        style_context.add_provider(parent.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.show_all()



class OutputsDialog(Gtk.Dialog):
    """
    Display dialog with list of outputs as individual CheckButtons.
    Button click events are handled by a callback function passed to __init__.
    """
    def __init__(self, parent, button_pressed_callback):
        """
        Args:
            parent: parent window
            button_pressed_callback: callback function handling checkbutton click events. callback accepts 1 arg with the output ID.
        """
        Gtk.Dialog.__init__(self, "Select Outputs", parent, Gtk.DialogFlags.MODAL, ("Close", 0))
        self.set_name("outputs-dialog")
        self.get_content_area().set_size_request(300, 200)
        for o in parent.mpd_outputs:
            log.debug("output: %s" % o)
            button = Gtk.CheckButton.new_with_label(o['outputname'])
            button.set_active(int(o['outputenabled']))
            self.get_content_area().add(button)
            button.connect("clicked", button_pressed_callback, o['outputid'])
        self.show_all()



class OptionsDialog(Gtk.Dialog):
    """
    Displays dialog of options. Each option is an individual CheckButton.
    Button click events are handled by a callback function passed to __init__.
    """
    def __init__(self, parent, button_pressed_callback):
        """
        Args:
            parent: parent window
            button_pressed_callback: callback function handling checkbutton click events. callback accepts 1 arg with the option name.
        """
        Gtk.Dialog.__init__(self, "Set Options", parent, Gtk.DialogFlags.MODAL, ("Close", 0))
        self.set_name("options-dialog")
        self.get_content_area().set_size_request(300, 200)

        self.consume_button = Gtk.CheckButton.new_with_label("Consume")
        self.consume_button.set_active(int(parent.mpd_status['consume']))
        self.consume_button.connect("clicked", button_pressed_callback, "consume")
        self.get_content_area().add(self.consume_button)

        self.shuffle_button = Gtk.CheckButton.new_with_label("Shuffle")
        self.shuffle_button.set_active(int(parent.mpd_status['random']))
        self.shuffle_button.connect("clicked", button_pressed_callback, "random")
        self.get_content_area().add(self.shuffle_button)

        self.repeat_button = Gtk.CheckButton.new_with_label("Repeat")
        self.repeat_button.set_active(int(parent.mpd_status['repeat']))
        self.repeat_button.connect("clicked", button_pressed_callback, "repeat")
        self.get_content_area().add(self.repeat_button)

        self.single_button = Gtk.CheckButton.new_with_label("Single")
        self.single_button.set_active(int(parent.mpd_status['single']))
        self.single_button.connect("clicked", button_pressed_callback, "single")
        self.get_content_area().add(self.single_button)

        self.show_all()



class MetadataLabel(Gtk.Label):
    """
    Gtk.Label with 2 accessible variables: data and type.
    """
    def set_metadata(self, data):
        """
        Set the metadata for the label

        Args:
            data: can be anything
        """
        self.data = data

    def set_metatype(self, t):
        """
        Set the metatype for the label

        Args:
            t: can be anything
        """
        self.type = t



class IndexedListBox(Gtk.ListBox):
    """
    Gtk.ListBox with an index variable. This allows ListBoxes to track their position in list of ListBoxes.
    """
    def set_index(self, index):
        """
        Sets the index of the ListBox

        Args:
            index:  int, the ListBox's position in the parent's list
        """
        self.index = index



class ColumnBrowser(Gtk.Box):
    """
    Column browser for a tree data structure. Inherits from GtkBox.
    Creates columns with a list of GtkScrolledWindows containing a GtkListBox.
    """
    def __init__(self, selected_callback, keypress_callback, cols=2, spacing=0, hexpand=True, vexpand=True):
        """
        Constructor for the column browser.

        Args:
            selected_callback: callback function for handling row-selected events
            keypress_callback: callback function for handling key-press-event events
            cols: int for number of colums
            hexpand: boolean for whether to set horizontal expansion
            vexpand: boolean for whether to set vertical expansion
        """
        Gtk.Box.__init__(self)
        self.set_spacing(spacing)
        if cols < 1:
            raise Exception("Number of columns must be greater than 1")
        self.columns = []
        for i in range(0, cols):
            scroll = Gtk.ScrolledWindow()
            listbox = IndexedListBox()
            if hexpand != None:
                listbox.set_hexpand(hexpand)
            if vexpand != None:
                listbox.set_vexpand(vexpand)
            listbox.set_index(i)
            listbox.connect("row-selected", selected_callback)
            scroll.add(listbox)
            self.add(scroll)
            self.columns.append(listbox)

        self.connect("key-press-event", keypress_callback)


    def get_selected_rows(self):
        """
        Gets the child objects of all selected rows. 
        Inserting them into a list in order from least to highest column index.

        Returns:
            list of selected rows' child objects.
        """
        ret = []
        for c in self.columns:
            row = c.get_selected_row()
            if row:
                #metatype = row.type
                #value = row.get_text()
                child = row.get_child()
                ret.append({ 'type': child.type, 'value': child.get_text(), 'data': child.data  })
        return ret



    def set_column_data(self, col_index, data, clear_rest=True):
        """
        Populates a column at col_index.
        Args:
            col_index:  int, column index
            data:  dictionary
            clear_rest: boolean, True: clear all columns to the left as well. default: True
        """
        if clear_rest:
            for i in range(col_index, len(self.columns)):
                children = self.columns[i].get_children()
                if children:
                    for c in children:
                        self.columns[i].remove(c)
                        c.destroy()

        for i in data:
            #log.debug("data: %s" % i)
            label = MetadataLabel(i['value'])
            label.set_metatype(i['type'])
            label.set_metadata(i['data'])
            label.set_halign(Gtk.Align.START)
            self.columns[col_index].add(label)
        self.columns[col_index].show_all()



class MPCFront(Gtk.Window):
    """
    MPCFront(end). Adds a head to headless MPD. Meant to run locally with 
    full keyboard control that will translate remote controls.

    Caches artist/album/track information in dictionary db_cache.
    db_cache structure
        db_cache['Artist'][artist][album]        = list of dicts of song metadata
        db_cache['Album Artists'][artist][album] = ditto
        db_cache['Albums'][album]                = ditto
    """

    run_idle = True                 ## Allows the idle thread to run
    #update_song_time = True        ## Allows song time to be updated
    last_audiofile = ""             ## Tracks albumart for display
    resize_event_on = False         ## Flag for albumart to resize
    browser_full = False            ## Tracks if the browser is fullscreen
    browser_hidden = False          ## Tracks if the browser is hidden
    last_width = 0                  ## Tracks width of window when window changes size
    last_height = 0                 ## Tracks height of window when window changes size
    do_update_playlist = False      ## Set when mpd has a playlist change event
    do_update_playback = False      ## Set when mpd has a player change event
    do_update_database = False      ## Set when mpd has a database change event
    current_playback_offset = 0     ## Offset into current song
    last_update_time = 0            ## Epoch time of last display update
    last_update_offset = 0          ## Time offset into a song at the last display update
    proc_file_fmt = "/proc/asound/card%s/pcm%sp/sub%s/hw_params"    ## proc file with DAC information
    art_cache = {}                  ## Cache for album art, etc.
    playlist_last_selected = None   ## Points to last selected song in playlist
    focus_on = "broswer"            ## Either 'playlist' or 'browser'
    current_albumart_pixbuf = None  ## GdkPixbuf storing the current album art


    ## Sleep times
    sleep_play = 500
    sleep_pause = 1000
    sleep_stop = 1000


    ## Dialogs
    playlist_confirm_dialog = None
    edit_playlist_dialog = None
    song_info_dialog = None
    outputs_dialog = None
    options_dialog = None


    def __init__(self, config):
        """
        MPCFront constructor. Connects to MPD. Create main window and contained components.

        Args:
            host: string, hostname/IP of the MPD server
            port: int, TCP port of the MPD server
        """
        Gtk.Window.__init__(self, title="MPD - %s:%s" % (config.get("main", "host"), config.get("main", "port")))
        GObject.threads_init()
        Gdk.threads_init()
        Gdk.threads_enter()

        self.set_decorated(False)
        self.set_size_request(int(config.get("main", "width")), int(config.get("main", "height")))

        self.config = config
        self.mpd_host = self.config.get("main", "host")
        self.mpd_port = int(self.config.get("main", "port"))
        self.music_root_dir = self.config.get("main", "music_dir")
        self.card_id = self.config.get("main", "sound_card")
        self.device_id = self.config.get("main", "sound_device")

        if not self.mpd_connect():
            log.fatal("Could not connect to MPD")
            raise RuntimeError("Could not connect to MPD")

        self.mpd_stats = self.mpd.stats()
        log.debug("mpd stats: %s" % self.mpd_stats)
        self.mpd_outputs = self.mpd.outputs()
        log.debug("mpd outputs: %s" % self.mpd_outputs)

        self.init_db_cache()

        ## Set CSS
        css_style = None
        log.debug("reading css file: %s" % self.config.get("main", "style"))
        try:
            fh = open(self.config.get("main", "style"), 'rb')
            css_style = fh.read()
            fh.close()
        except Exception as e:
            log.error("could not read CSS file: %s" % e)
            raise
        self.css = Gtk.CssProvider()
        self.css.load_from_data(css_style)
        self.style_context = self.get_style_context()
        self.style_context.add_provider_for_screen(Gdk.Screen.get_default(), self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


        ## mainpaned is the toplevel layout container
        self.mainpaned = Gtk.VPaned()
        #self.mainpaned.set_wide_handle(True)
        self.add(self.mainpaned)

        ## Setup browser columns
        self.browser_box = ColumnBrowser(self.broswer_row_selected, self.browser_key_pressed, 4, 0, True, True)
        self.browser_box.set_name("browser")
        self.mainpaned.add1(self.browser_box)
        rows = [
            { 'type': 'category', 'value': 'Album Artists', 'data': None },
            { 'type': 'category', 'value': 'Artists', 'data': None },
            { 'type': 'category', 'value': 'Albums', 'data': None },
            { 'type': 'category', 'value': 'Files', 'data': None },
            { 'type': 'category', 'value': 'Genres', 'data': None },
            { 'type': 'category', 'value': 'Songs', 'data': None }
        ]
        self.browser_box.set_column_data(0, rows)

        ## Setup bottom half
        self.bottompaned = Gtk.HPaned()
        self.mainpaned.add2(self.bottompaned)
        self.init_playback_display()

        ## Setup playlist
        self.playlist_list = Gtk.ListBox()
        #self.playlist_list.set_hexpand(True)
        #self.playlist_list.set_vexpand(True)
        self.playlist_scroll = Gtk.ScrolledWindow()
        self.playlist_scroll.set_hexpand(True)
        self.playlist_scroll.add(self.playlist_list)
        self.bottompaned.add2(self.playlist_scroll)

        ## Set event handlers
        self.connect("delete-event", Gtk.main_quit)
        self.connect("destroy", Gtk.main_quit)
        self.connect("destroy-event", Gtk.main_quit)
        self.connect("key-press-event", self.key_pressed)
        self.connect("check-resize", self.window_resized)
        self.previous_button.connect("clicked", self.previous_clicked)
        self.rewind_button.connect("clicked", self.rewind_clicked)
        self.stop_button.connect("clicked", self.stop_clicked)
        self.play_button.connect("clicked", self.play_clicked)
        self.cue_button.connect("clicked", self.cue_clicked)
        self.next_button.connect("clicked", self.next_clicked)
        self.playlist_list.connect("key-press-event", self.playlist_key_pressed)

        self.update_playback()
        self.update_playlist()

        self.spawn_idle_thread()
        self.playback_timeout_id = GObject.timeout_add(self.sleep_play, self.playback_timeout)

        #self.set_resizable(True)
        self.present()
        self.grab_focus()

        if re.match(r'yes$', self.config.get("main", "fullscreen"), re.IGNORECASE):
            self.fullscreen()

        self.get_albumartists()
        self.get_artists()
        self.get_albums()
        self.get_genres()
        self.get_files_list()

        self.playlist_last_selected = 0
        self.playlist_list.select_row(self.playlist_list.get_row_at_index(self.playlist_last_selected))
        self.browser_box.columns[0].select_row(self.browser_box.columns[0].get_row_at_index(0))



    def init_playback_display(self):
        """
        Setup playback grid
        """
        self.playback_grid = Gtk.Grid()
        self.playback_grid.set_name("playback-pane")
        self.bottompaned.add1(self.playback_grid)

        self.playback_info_box = Gtk.VBox()
        self.playback_grid.attach(self.playback_info_box, 0, 0, 1, 1)

        self.current_title_label = Gtk.Label(" ")
        self.current_title_label.set_name("current-title")
        self.current_title_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.current_title_label.set_halign(Gtk.Align.START)
        self.current_title_label.set_valign(Gtk.Align.START)
        #self.current_title_label.set_line_wrap(True)
        self.current_title_label.set_hexpand(True)
        self.current_artist_label = Gtk.Label(" ")
        self.current_artist_label.set_name("current-artist")
        self.current_artist_label.set_halign(Gtk.Align.START)
        self.current_artist_label.set_valign(Gtk.Align.START)
        self.current_artist_label.set_ellipsize(Pango.EllipsizeMode.END)
        #self.current_artist_label.set_line_wrap(True)
        self.current_album_label = Gtk.Label(" ")
        self.current_album_label.set_name("current-album")
        self.current_album_label.set_halign(Gtk.Align.START)
        self.current_album_label.set_valign(Gtk.Align.START)
        self.current_album_label.set_ellipsize(Pango.EllipsizeMode.END)
        #self.current_album_label.set_line_wrap(True)
        self.stats1_label = Gtk.Label(" ")
        self.stats1_label.set_name("stats1")
        self.stats1_label.set_halign(Gtk.Align.START)
        self.stats1_label.set_valign(Gtk.Align.END)
        self.stats2_label = Gtk.Label(" ")
        self.stats2_label.set_name("stats2")
        self.stats2_label.set_halign(Gtk.Align.START)
        self.stats2_label.set_valign(Gtk.Align.END)
        self.current_time_label = Gtk.Label(" ")
        self.current_time_label.set_name("current-time")
        self.current_time_label.set_halign(Gtk.Align.START)
        self.current_time_label.set_valign(Gtk.Align.END)

        ## Add labels to playback grid
        self.playback_info_box.pack_start(self.current_title_label, False, True, 0)
        self.playback_info_box.pack_start(self.current_artist_label, False, True, 0)
        self.playback_info_box.pack_start(self.current_album_label, False, True, 0)
        self.playback_info_box.pack_end(self.current_time_label, False, True, 0)
        self.playback_info_box.pack_end(self.stats2_label, False, True, 0)
        self.playback_info_box.pack_end(self.stats1_label, False, True, 0)

        ## Setup playback button box
        self.playback_button_box = Gtk.Box()
        self.playback_grid.attach(self.playback_button_box,  0, 3, 2, 1)
        self.previous_button = Gtk.Button(symbol_previous)
        self.rewind_button = Gtk.Button(symbol_rewind)
        self.stop_button = Gtk.Button(symbol_stop)
        self.play_button = Gtk.Button(symbol_play)
        self.cue_button = Gtk.Button(symbol_cue)
        self.next_button = Gtk.Button(symbol_next)
        self.playback_button_box.pack_start(self.previous_button, True, True, 3)
        self.playback_button_box.pack_start(self.rewind_button, True, True, 3)
        self.playback_button_box.pack_start(self.stop_button, True, True, 3)
        self.playback_button_box.pack_start(self.play_button, True, True, 3)
        self.playback_button_box.pack_start(self.cue_button, True, True, 3)
        self.playback_button_box.pack_start(self.next_button, True, True, 3)

        ## Song progress bar
        self.song_progress = Gtk.LevelBar()
        self.song_progress.set_size_request(-1, 20)
        self.song_progress.set_name("progressbar")
        self.playback_grid.attach(self.song_progress,        0, 2, 2, 1)

        ## Current album art
        self.current_albumart = Gtk.Image()
        self.current_albumart.set_valign(Gtk.Align.START)
        self.current_albumart.set_vexpand(True)
        #self.current_albumart.set_hexpand(True)
        self.playback_grid.attach(self.current_albumart, 1, 0, 1, 1)



##  BEGIN EVENT HANDLERS

    def window_resized(self, widget):
        """
        Handler for window resize event
        """
        #log.debug("Window resize event")
        w = self.get_allocated_width()
        h = self.get_allocated_height()
        if self.last_width != w or self.last_height != h:
            self.last_width = w
            self.last_height = h
            self.resize_event_on = True
            self.resize_widgets()
            self.set_current_albumart()
            self.resize_event_on = False

##  Keyboard event handlers
    def key_pressed(self, widget, event):
        """
        Keypress handler for toplevel widget. Responds to global keys for playback control.
        """

        ctrl = (event.state & Gdk.ModifierType.CONTROL_MASK)
        shift = (event.state & Gdk.ModifierType.SHIFT_MASK)
        mod1 = (event.state & Gdk.ModifierType.MOD1_MASK)   ## Alt
        mod2 = (event.state & Gdk.ModifierType.MOD2_MASK)   ## Cmd
        mod3 = (event.state & Gdk.ModifierType.MOD3_MASK)

        try:
            if (ctrl or mod2) and event.keyval in (ord('q'), ord('Q')):
                Gtk.main_quit()
            elif event.keyval == ord(self.config.get("keys", "playpause")):
                #log.debug("PLAY/PAUSE")
                self.play_or_pause()
            elif event.keyval == ord(self.config.get("keys", "stop")):
                #log.debug("STOP")
                self.mpd.stop()
            elif event.keyval == ord(self.config.get("keys", "previous")):
                #log.debug("PREVIOUS")
                self.mpd.previous()
            elif event.keyval == ord(self.config.get("keys", "next")):
                #log.debug("NEXT")
                self.mpd.next()
            elif event.keyval == ord(self.config.get("keys", "rewind")):
                #log.debug("REWIND")
                self.mpd.seekcur("-5")
            elif event.keyval == ord(self.config.get("keys", "cue")):
                #log.debug("CUE")
                self.mpd.seekcur("+5")

            elif event.keyval == ord(self.config.get("keys", "outputs")):
                self.outputs_dialog = OutputsDialog(self, self.outputs_changed)
                response = self.outputs_dialog.run()
                self.outputs_dialog.destroy()

            elif event.keyval == ord(self.config.get("keys", "options")):
                self.options_dialog = OptionsDialog(self, self.options_changed)
                response = self.options_dialog.run()
                self.options_dialog.destroy()

            elif event.keyval == ord(self.config.get("keys", "browser")):
                ## Focus on the last selected row in the browser
                self.focus_on = "broswer"
                selected_items = self.browser_box.get_selected_rows()
                if not len(selected_items):
                    self.browser_box.columns[0].select_row(self.browser_box.columns[0].get_row_at_index(0))
                    selected_items = self.browser_box.get_selected_rows()
                focus_col = self.browser_box.columns[len(selected_items)-1]
                focus_row = focus_col.get_selected_row()
                focus_row.grab_focus()

            elif event.keyval == ord(self.config.get("keys", "playlist")):
                ## Focus on the selected row in the playlist
                self.focus_on = "playlist"
                selected_row = self.playlist_list.get_selected_row()
                if not selected_row:
                    selected_row = self.playlist_list.get_row_at_index(0)
                    self.playlist_list.select_row(selected_row)
                selected_row.grab_focus()

            elif event.keyval == ord(self.config.get("keys", "full_browser")):
                ## Hide bottom pane/fullscreen browser
                if self.mainpaned.get_position() == self.last_height-1:
                    self.mainpaned.set_position(int(self.last_height/2))
                    self.resize_event_on = True
                    self.set_current_albumart()
                    self.resize_event_on = False
                else:
                    self.mainpaned.set_position(self.last_height)

            elif event.keyval == ord(self.config.get("keys", "full_bottom")):
                ## Hide top pane
                if self.mainpaned.get_position() == 0:
                    self.mainpaned.set_position(int(self.last_height/2))
                else:
                    self.mainpaned.set_position(0)
                self.resize_event_on = True
                self.set_current_albumart()
                self.resize_event_on = False

            elif event.keyval == ord(self.config.get("keys", "full_playback")):
                ## Hide playlist
                if self.bottompaned.get_position() == self.last_width-1:
                    self.bottompaned.set_position(int(self.last_width/2))
                else:
                    self.bottompaned.set_position(self.last_width)
                self.resize_event_on = True
                self.set_current_albumart()
                self.resize_event_on = False

            elif event.keyval == ord(self.config.get("keys", "full_playlist")):
                ## Hide top pane
                if self.bottompaned.get_position() == 0:
                    self.bottompaned.set_position(int(self.last_width/2))
                    self.resize_event_on = True
                    self.set_current_albumart()
                    self.resize_event_on = False
                else:
                    self.bottompaned.set_position(0)


            #elif event.keyval == Gdk.KEY_Right:
            #    log.debug("RIGHT")
            #elif event.keyval == Gdk.KEY_Left:
            ##    log.debug("LEFT")
            #elif event.keyval == Gdk.KEY_Up:
            #    log.debug("UP")
            #elif event.keyval == Gdk.KEY_Down:
            #    log.debug("DOWN")
            #else:
            #    log.debug("key press: %s" % event.keyval)

        except (musicpd.ConnectionError, BrokenPipeError) as e:
            log.info("previous mpd command failed: %s" % e)
            self.mpd_connect()

        except Exception as e:
            log.error("Unknown exception: %s" % e)

    def browser_key_pressed(self, widget, event):
        """
        Event handler for browser box key presses
        """
        if event.keyval == Gdk.KEY_Return:
            #log.debug("browser key: ENTER")
            self.add_to_playlist()

        elif event.keyval == ord(self.config.get("keys", "info")):
            self.browser_info_popup()


    def playlist_key_pressed(self, widget, event):
        """
        Event handler for playlist box key presses
        """
        if event.keyval == Gdk.KEY_Return:
            #log.debug("playlist key: ENTER")
            self.edit_playlist()

        elif event.keyval == ord(self.config.get("keys", "info")):
            self.playlist_info_popup()

##  Click handlers

    def previous_clicked(self, button):
        """
        Click handler for previous button
        """
        #log.debug("PREVIOUS")
        try:
            self.mpd.previous()
        except (musicpd.ConnectionError, BrokenPipeError) as e:
            log.info("previous failed: %s" % e)
            self.mpd_connect()
            self.mpd.previous()

    def rewind_clicked(self, button):
        """
        Click handler for rewind button
        """
        #log.debug("REWIND")
        try:
            self.mpd.seekcur("-5")
        except (musicpd.ConnectionError, BrokenPipeError) as e:
            log.info("rewind failed: %s" % e)
            self.mpd_connect()
            self.mpd.seekcur("-5")

    def stop_clicked(self, button):
        """
        Click handler for stop button
        """
        #log.debug("STOP")
        try:
            self.mpd.stop()
        except (musicpd.ConnectionError, BrokenPipeError) as e:
            log.info("stop failed: %s" % e)
            self.mpd_connect()
            self.mpd.stop()

    def play_clicked(self, button):
        """
        Click handler for play/pause button
        """
        self.play_or_pause()

    def cue_clicked(self, button):
        """
        Click handler for cue button
        """
        #log.debug("CUE")
        try:
            self.mpd.seekcur("+5")
        except (musicpd.ConnectionError, BrokenPipeError) as e:
            log.info("cue failed: %s" % e)
            self.mpd_connect()
            self.mpd.seekcur("+5")

    def next_clicked(self, button):
        """
        Click handler for next button
        """
        #log.debug("NEXT")
        try:
            self.mpd.next()
        except (musicpd.ConnectionError, BrokenPipeError) as e:
            log.info("next failed: %s" % e)
            self.mpd_connect()
            self.mpd.next()

##  Selected handlers

    def broswer_row_selected(self, listbox, row):
        """
        Handler for selection event in browser_box
        """
        if not row:
            return

        child = row.get_child()
        if child:
            metatype = child.type
            value = child.get_text()
            #log.debug("col %d, %s: %s" % (listbox.index, metatype, value))
            if metatype == "category":
                if value == "Album Artists":
                    artists = self.get_albumartists()
                    #log.debug("albumartists: %s" % artists)
                    rows = []
                    for a in artists:
                        rows.append({ 'type': 'albumartist', 'value': a, 'data': None })
                    self.browser_box.set_column_data(listbox.index+1, rows)
                    self.browser_box.columns[listbox.index+1].set_sort_func(listbox_cmp_filtered, None, False)

                elif value == "Artists":
                    artists = self.get_artists()
                    #log.debug("artists: %s" % artists)
                    rows = []
                    for a in artists:
                        rows.append({ 'type': 'artist', 'value': a, 'data': None })
                    self.browser_box.set_column_data(listbox.index+1, rows)
                    self.browser_box.columns[listbox.index+1].set_sort_func(listbox_cmp_filtered, None, False)

                elif value == "Albums":
                    albums = self.get_albums()
                    rows = []
                    for a in albums:
                        rows.append({ 'type': 'album', 'value': a, 'data': None })
                    self.browser_box.set_column_data(listbox.index+1, rows)
                    self.browser_box.columns[listbox.index+1].set_sort_func(listbox_cmp_filtered, None, False)

                elif value == "Genres":
                    genres = self.get_genres()
                    rows = []
                    for g in genres:
                        rows.append({'type': 'genre', 'value': g, 'data': None})
                    self.browser_box.set_column_data(listbox.index+1, rows)
                    self.browser_box.columns[listbox.index+1].set_sort_func(listbox_cmp, None, False)

                elif value == "Files":
                    files = self.get_files_list()
                    #log.debug("files: %s" % files)
                    rows = []
                    for f in files:
                        subf = self.get_files_list(f['data']['dir'])
                        for f2 in subf:
                            rows.append({ 'type': f2['type'], 'value': f['value']+"/"+f2['value'], 'data': f2['data'], })
                    self.browser_box.set_column_data(listbox.index+1, rows)
                    self.browser_box.columns[listbox.index+1].set_sort_func(listbox_cmp, None, False)

                else:
                    self.browser_box.set_column_data(listbox.index+1, [])

            elif metatype == "albumartist":
                albums = self.get_albums_by_albumartist(value)
                #log.debug("albums: %s" % albums)
                rows = []
                for a in albums:
                    rows.append({ 'type': 'album', 'value': a, 'data': None })
                self.browser_box.set_column_data(listbox.index+1, rows)
                self.browser_box.columns[listbox.index+1].set_sort_func(listbox_cmp, None, False)
    
            elif metatype == "artist":
                albums = self.get_albums_by_artist(value)
                #log.debug("albums: %s" % albums)
                rows = []
                for a in albums:
                    rows.append({ 'type': 'album', 'value': a, 'data': None })
                self.browser_box.set_column_data(listbox.index+1, rows)
                self.browser_box.columns[listbox.index+1].set_sort_func(listbox_cmp, None, False)

            elif metatype == "genre":
                albums = self.get_albums_by_genre(value)
                #log.debug("albums: %s" % albums)
                rows = []
                for a in albums:
                    rows.append({ 'type': 'album', 'value': a, 'data': None })
                self.browser_box.set_column_data(listbox.index+1, rows)
                self.browser_box.columns[listbox.index+1].set_sort_func(listbox_cmp, None, False)
    
            elif metatype == "album":
                selected_items = self.browser_box.get_selected_rows()
                #log.debug("selected items: %s" % selected_items)
                last_type = selected_items[listbox.index-1]['type']
                last_value = selected_items[listbox.index-1]['value']
                #log.debug("%s %s" % (value, last_value))
                songs = None
                if last_type == "albumartist":
                    songs = self.get_songs_by_album_by_albumartist(value, last_value)

                elif last_type == "artist":
                    songs = self.get_songs_by_album_by_artist(value, last_value)

                elif last_type == "category":
                    songs = self.get_songs_by_album(value)

                elif last_type == "genre":
                    songs = self.get_songs_by_album_by_genre(value, last_value)

                rows = []
                if songs:
                    for s in songs:
                        #log.debug(s)
                        track = re.sub(r'/.*', '',  s['track'])
                        rows.append({ 'type': 'song', 'value': track+" "+ s['title'], 'data': s })
                self.browser_box.set_column_data(listbox.index+1, rows)
                #self.browser_box.columns[listbox.index+1].set_sort_func(listbox_cmp_by_track, None, False)
    
            elif metatype == "directory":
                files = self.get_files_list(child.data['dir'])
                rows = []
                for f in files:
                    #log.debug("directory: %s" % f)
                    rows.append(f)
                self.browser_box.set_column_data(listbox.index+1, rows)
                self.browser_box.columns[listbox.index+1].set_sort_func(listbox_cmp, None, False)

##  END EVENT HANDLERS



    def mpd_connect(self):
        """
        Connect to MPD. Requires mpd_host and mpd_port.

        Returns:
            boolean, True if connected, False if not
        """
        try:
            self.mpd = musicpd.MPDClient()
            self.mpd.connect(self.mpd_host, self.mpd_port)
            log.debug("connected to %s:%d" % (self.mpd_host, self.mpd_port))
        except Exception as e:
            log.fatal("Could not connect to mpd %s:%d: %s" % (self.mpd_host, self.mpd_port, e))
            return False
        return True



    def init_db_cache(self):
        """
        Initialize db_cache. Deletes all previously stored information.
        """
        self.db_cache = {
            'Album Artists': {},
            'Artists': {},
            'Albums': {},
            'Files': {},
            'Genres': {},
            'Songs': {},
        }



    def play_or_pause(self):
        """
        Check the player status, play if stopped, pause otherwise.
        """
        if self.mpd_status['state'] == "stop":
            #log.debug("PLAY")
            try:
                self.mpd.play()
            except (musicpd.ConnectionError, BrokenPipeError) as e:
                log.info("play failed: %s" % e)
                self.mpd_connect()
                self.mpd.play()
        else:
            #log.debug("PAUSE")
            try:
                self.mpd.pause()
            except (musicpd.ConnectionError, BrokenPipeError) as e:
                log.info("pause failed: %s" % e)
                self.mpd_connect()
                self.mpd.pause()



    def get_albumart(self, audiofile):
        """
        Extract album art from a file, or look for a cover in its directory.
        Tries to fetch art from Last.fm if all else fails.

        Args:
            audiofile: string, path of the file containing the audio data

        Returns:
            raw image data
        """
        img_data = None

        ## Try to find album art in the media file
        try:
            if re.search(r'\.flac$', self.mpd_currentsong['file'], re.IGNORECASE):
                a = FLAC(audiofile)
                if len(a.pictures):
                    img_data = a.pictures[0].data
            elif re.search(r'\.m4a$', self.mpd_currentsong['file'], re.IGNORECASE):
                a = MP4(audiofile)
                if 'covr' in a.tags:
                    if len(a.tags['covr']):
                        img_data = a.tags['covr'][0]
            else:
                a = mutagen.File(audiofile)
                for k in a.keys():
                    if re.match(r'APIC:', k):
                        img_data = a[k].data
                        break
        except Exception as e:
            log.error("could not open audio file: %s" % e)

        ## Look for album art on the directory of the media file
        if not img_data:
            cover_path = ""
            song_dir =  self.music_root_dir+"/"+os.path.dirname(self.mpd_currentsong['file'])
            for f in os.listdir(song_dir):
                if re.match(r'cover\.(jpg|png|jpeg)', f, re.IGNORECASE):
                    cover_path = song_dir+"/"+f
                    break
            log.debug("looking for cover file: %s" % cover_path)
            if os.path.isfile(cover_path):
                try:
                    cf = open(cover_path, 'rb')
                    img_data = cf.read()
                    cf.close()
                except Exception as e:
                    log.error("error reading cover file: %s" % e)

        ## Look up the album art in Last.fm if configured
        if not img_data:
            ## Check cache for album art before querying lastfm
            if self.mpd_currentsong['artist'] in self.art_cache and self.mpd_currentsong['album'] in self.art_cache[self.mpd_currentsong['artist']] and 'image_data' in self.art_cache[self.mpd_currentsong['artist']][self.mpd_currentsong['album']]:
                log.debug("lastfm lookup already cached")
                img_data = self.art_cache[self.mpd_currentsong['artist']][self.mpd_currentsong['album']]['image_data']

            elif self.config.get("lastfm", "api_key") and self.config.get("lastfm", "api_secret"):
                image_url = ""
                try:
                    lastfm = pylast.LastFMNetwork(api_key=self.config.get("lastfm", "api_key"), api_secret=self.config.get("lastfm", "api_secret"))
                    album = lastfm.get_album(self.mpd_currentsong['artist'], self.mpd_currentsong['album'])
                    image_url = album.get_cover_image()
                    log.debug("lastfm cover url: %s" % image_url)
                    if image_url:
                        if self.mpd_currentsong['artist'] not in self.art_cache:
                            self.art_cache[self.mpd_currentsong['artist']] = {}
                        self.art_cache[self.mpd_currentsong['artist']][self.mpd_currentsong['album']] = {}
                        self.art_cache[self.mpd_currentsong['artist']][self.mpd_currentsong['album']]['image_url'] = image_url
                        r = requests.get(image_url)
                        img_data = r.content
                        self.art_cache[self.mpd_currentsong['artist']][self.mpd_currentsong['album']]['image_data'] = img_data

                        if re.match(r'yes$', self.config.get("lastfm", "save_cover"), re.IGNORECASE):
                            log.debug("saving album art for: %s / %s" % (self.mpd_currentsong['artist'], self.mpd_currentsong['album']))
                            self.save_albumart(img_data, audiofile)
                except Exception as e:
                    log.error("error fetch cover file from lastfm: %s" % e)

        return img_data



    def save_albumart(self, img_data, song_path):
        """
        Determines the filetype, then writes the file out into the same diredtory as song_path.

        Args:
            img_data: bytes containing the encoded image
            song_path: path to the media file
        """
        ftype = imghdr.what(None, img_data)
        log.debug("image type: %s" % ftype)
        if ftype == "jpeg":
            ftype = "jpg"

        cover_file = os.path.dirname(song_path)+"/cover."+ftype
        if os.path.exists(cover_file):
            log.info("not saving file, already exixsts: %s" % cover_file)
            return
        log.debug("saving album art to: %s" % cover_file)
        try:
            aaf= open(cover_file, "wb")
            aaf.write(img_data)
            aaf.close()
        except Exception as e:
            log.error("could not save album art: %s" % e)

        

    def set_current_albumart(self):
        """
        Load and display image of current song if it has changed since the last time this function was run, or on the first run.
        Loads image data into a PIL.Image object, then into a GdkPixbuf object, then into a Gtk.Image object for display.
        """
        if not self.mpd_currentsong or not 'file' in self.mpd_currentsong.keys():
            return

        audiofile = self.music_root_dir+"/"+self.mpd_currentsong['file']

        if self.last_audiofile != audiofile:
            log.debug("new cover file, updating")
            img_data = self.get_albumart(audiofile)
            if img_data:
                img = Image.open(io.BytesIO(img_data))
                img_bytes = GLib.Bytes.new(img.tobytes())
                log.debug("image size: %d x %d" % img.size)
                w, h = img.size
                self.current_albumart_pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(img_bytes, GdkPixbuf.Colorspace.RGB, False, 8, w, h, w*3)
            else:
                self.current_albumart.clear()
                self.last_audiofile = audiofile
                return

        if self.last_audiofile != audiofile or self.resize_event_on:
            window_height = self.get_allocated_height()
            paned_position = self.mainpaned.get_position()
            from_bottom = self.playback_button_box.get_allocated_height() + self.song_progress.get_allocated_height()
            log.debug("wh: %d, pp: %d, ftb: %d" % (window_height, paned_position, from_bottom))
            if from_bottom < 20:
                from_bottom = 76
            image_height = window_height - from_bottom - paned_position

            window_width = self.get_allocated_width()
            paned_position = self.bottompaned.get_position()
            image_width = int((window_width - (window_width - paned_position))/2)

            image_height = min(image_width, image_height)
            if image_height <1:
                image_height = 100

            ## Assume all albumart should be more or less square
            log.debug("Setting image to %d x %d, window height: %d" % (image_height, image_height, window_height))
            if self.current_albumart_pixbuf:
                pixbuf = self.current_albumart_pixbuf.scale_simple(image_height, image_height, GdkPixbuf.InterpType.BILINEAR)
                self.current_albumart.set_from_pixbuf(pixbuf)
            else:
                log.info("could not get pixbuf")
                self.current_albumart.clear()
        self.last_audiofile = audiofile



    def resize_widgets(self):
        """
        Resizes widgets on window resize
        """
        window_width = self.get_allocated_width()
        window_height = self.get_allocated_height()
        half_width = int(window_width/2)
        half_height = int(window_height/2)
        self.mainpaned.set_position(half_height)
        self.bottompaned.set_position(half_width)



    def update_playback(self, mpd=None):
        """
        Updates playback display. 
        Fetches the current status and song from MPD. Sets the text on each label.
        """
        if not mpd:
            mpd = self.mpd
        ## Fetch current status and song from MPD.
        try:
            self.mpd_status = mpd.status()
            self.mpd_currentsong = mpd.currentsong()
            log.debug("status: %s" % self.mpd_status)
            log.debug("currentsong: %s" % self.mpd_currentsong)
        except (musicpd.ConnectionError, BrokenPipeError) as e:
            log.info("Attempting reconnect: %s" % e)
            self.mpd_connect()
            self.mpd_status = mpd.status()
            self.mpd_currentsong = mpd.currentsong()

        ## Set labels with song information. Set to empty if there is no current song.
        if self.mpd_currentsong:
            self.last_update_time = time.time()
            if 'artist' in self.mpd_currentsong and 'title' in self.mpd_currentsong and 'album' in self.mpd_currentsong:
                self.current_title_label.set_text(self.mpd_currentsong['title'])
                self.current_artist_label.set_text(self.mpd_currentsong['artist'])
                self.current_artist_label.set_ellipsize(Pango.EllipsizeMode.END)
                self.current_artist_label.set_line_wrap(False)
                self.current_album_label.set_text(self.mpd_currentsong['album'])
            else:
                filename = os.path.basename(self.mpd_currentsong['file'])
                self.current_title_label.set_text(" ")
                self.current_artist_label.set_text(filename)
                self.current_artist_label.set_ellipsize(Pango.EllipsizeMode.NONE)
                self.current_artist_label.set_line_wrap(True)
                self.current_album_label.set_text(" ")
        else:
            self.current_title_label.set_text(" ")
            self.current_artist_label.set_text(" ")
            self.current_album_label.set_text(" ")

        ## Get stream rates, format
        freq = bits = bitrate = chs = ""
        if 'audio' in self.mpd_status.keys():
            freq, bits, chs = re.split(r':', self.mpd_status['audio'], 2)
        if 'bitrate' in self.mpd_status.keys():
            bitrate = self.mpd_status['bitrate']

        ## Format and set stream/dac information. Set to empty if there is no info to display
        format_text = dac_text = ""
        if freq and bits and chs and bitrate:
            if bits == "dsd":
                format_text = "%2.1f MHz DSD" % (float(bitrate)/1000)
            elif bits == "f":
                format_text = "%3.1f kHz float PCM" % (float(freq)/1000)
            else:
                format_text = "%3.1f kHz %s bit PCM" % (float(freq)/1000, bits)

            ## Get and format DAC rate, format
            dac_freq = dac_bits = ""
            proc_file = self.proc_file_fmt % (self.card_id, self.device_id, "0")
            #log.debug("proc file: %s" % proc_file)
            if os.path.exists(proc_file):
                lines = ()
                try:
                    fh = open(proc_file)
                    lines = fh.readlines()
                    fh.close()
                except Exception as e:
                    log.error("opening up proc file: %s" % e)
                for line in lines:
                    line = line.rstrip()
                    #log.debug("procfile line: %s" % line)
                    if re.match(r'rate:', line):
                        (junk1, dac_freq, junk2) = re.split(r' ', line, 2)
                    elif re.match(r'format:', line):
                        (junk1, dac_bits) = re.split(r': ', line, 1)
                    elif re.match(r'closed', line):
                        break
                if dac_freq and dac_bits:
                    num_bits = 0
                    if dac_bits in ("S32_LE"):
                        num_bits = 32
                    elif dac_bits in ("S24_LE"):
                        num_bits = 24
                    elif dac_bits in ("S16_LE"):
                        num_bits = 16
                    dac_text = "%3.1f kHz %d bit" % (float(dac_freq)/1000, num_bits)


            self.stats1_label.set_markup("<small><b>src:</b></small> "+format_text+" @ "+bitrate+" kbps")
            self.stats2_label.set_markup("<small><b>dac:</b></small> "+dac_text)
        else:
            self.stats1_label.set_text(" ")
            self.stats2_label.set_text(" ")

        ## Format and set time information and state
        if 'time' in self.mpd_status.keys():
            print_state = "Playing"
            if self.mpd_status['state'] == "pause":
                print_state = "Paused"
            self.mpd_status['curr_t'], self.mpd_status['end_t'] = self.mpd_status['time'].split(r':', 1)
            self.last_update_offset = int(self.mpd_status['curr_t'])
            self.song_progress.set_max_value(int(self.mpd_currentsong['time']))
            self.song_progress.set_value(self.last_update_offset)
            self.current_time_label.set_text(pp_time(self.last_update_offset)+" / "+pp_time(self.mpd_status['end_t'])+" "+print_state)
        elif self.mpd_status['state'] == "stop":
            self.song_progress.set_value(0)
            self.current_time_label.set_text("Stopped")
            self.last_update_offset = 0


        self.set_current_albumart()



    def get_playlist(self, mpd=None):
        """
        Query for playlist. Clean up data before returning.

        Returns:
            list of filenames
        """
        if not mpd:
            mpd = self.mpd
        try:
            plist = mpd.playlistinfo()
            #log.debug("playlist: %s" % plist)
        except (musicpd.ConnectionError, BrokenPipeError) as e:
            log.error("could not fetch playlist: %s" % e)
            self.mpd_connect()
            return None
        return plist
        playlist = []
        for song in plist:
            #log.debug("file_info: %s" % song)
            playlist.append(song)
        return playlist



    def update_playlist(self, mpd=None):
        """
        Updates playlist display. Makes MPD call for the playlist. 
        Clears the current playlist. Adds song titles to the listbox.
        """
        if not mpd:
            mpd = self.mpd
        playlist = self.get_playlist(mpd)
        #log.debug("playlist: %s" % playlist)

        ## Empty list if aleady populated
        children = self.playlist_list.get_children()
        if children:
            for c in children:
                self.playlist_list.remove(c)
                c.destroy()

        if not playlist:
            return

        ## Add songs to the list
        for song in playlist:
            label_text = ""
            if 'track' in song and 'time' in song and 'title' in song:
                label_text = re.sub(r'/.*', '', cgi.escape(song['track']))+" ("+cgi.escape(pp_time(song['time']))+") <b>"+cgi.escape(song['title'])+"</b>"
            else:
                label_text = os.path.basename(song['file'])
            label = MetadataLabel()
            label.set_markup(label_text)
            label.set_metatype('song')
            label.set_metadata(song)
            label.set_halign(Gtk.Align.START)
            self.playlist_list.add(label)

        if self.playlist_last_selected != None:
            self.playlist_list.select_row(self.playlist_list.get_row_at_index(self.playlist_last_selected))

        if self.focus_on == "playlist" and self.playlist_list.get_row_at_index(self.playlist_last_selected):
            self.playlist_list.get_row_at_index(self.playlist_last_selected).grab_focus()

        self.playlist_list.get_row_at_index(int(self.mpd_currentsong['pos'])).set_name("current")
        self.playlist_list.show_all()



    def idle_thread(self):
        """
        Function that runs in the idle thread created by spawn_idle_thread().
        Listens for changes from MPD, using the idle command.
        Sets objects variables for updates based on response to idle()
        """
        mpd = musicpd.MPDClient()
        try:
            mpd.connect(self.mpd_host, self.mpd_port)
        except (musicpd.ConnectionError, BrokenPipeError) as e:
            log.critical("idle thread could not connect to MPD: %s" % e)
            return None

        while self.run_idle:
            try:
                mpd.send_idle()
                changes = mpd.fetch_idle()
            except (musicpd.ConnectionError, BrokenPipeError) as e:
                log.error("idle failed: %s" % e)
                self.mpd_connect()
                continue
            except Exception as e:
                log.error("idle failed: %s" % e)
            log.debug("changes: %s" % changes)
            for c in changes:
                if c == "playlist":
                    self.do_update_playlist = True
                elif c == "player":
                    self.do_update_playback = True
                elif c == "database":
                    self.do_update_database = True
                elif c == "outputs":
                    None
                elif c == "mixer":
                    None
                else:
                    log.info("Unhandled change: %s" % c)
            #GObject.source_remove(self.playback_timeout_id)
            GObject.timeout_add(0, self.playback_timeout, True)
            


    def spawn_idle_thread(self):
        """
        Creates and starts the idle thread that listens for change events from MPD.
        """
        try:
            idle_thread = threading.Thread(target=self.idle_thread, args=(), name="idle_update")
            idle_thread.daemon = True
            idle_thread.start()
        except Exception as e:
            log.fatal("Could not spawn idle thread: %s" % e)
            return None
        return True



    def get_artists(self, mpd=None):
        """
        Gets the list of artists from mpd, enters artists into db_cache if needed

        Args:
            mpd: Optional musicpd.MPDClient object. If not supplied, the object's mpd object will be used.

        Returns:
            list of artist names
        """
        if not mpd:
            mpd = self.mpd

        if not len(self.db_cache['Artists']):
            try:
                recv = mpd.list("artist")
                #log.debug("artists: %s" % recv)
            except (musicpd.ConnectionError, BrokenPipeError) as e:
                log.fatal("get artists failed: %s" % e)
                self.mpd_connect()
                return None

            for i in recv:
                if i == "":
                    continue
                #log.debug("Adding to cache artist: %s" % i)
                self.db_cache['Artists'][i] = {}

        return self.db_cache['Artists'].keys()



    def get_albumartists(self, mpd=None):
        """
        Gets the list of albumartists from mpd, enters albumartists into db_cache if needed

        Args:
            mpd: Optional musicpd.MPDClient object. If not supplied, the object's mpd object will be used.

        Returns:
            list of artist names
        """
        if not mpd:
            mpd = self.mpd

        if not len(self.db_cache['Album Artists']):
            try:
                recv = mpd.list("albumartist")
                #log.debug("albumartists: %s" % recv)
            except (musicpd.ConnectionError, BrokenPipeError) as e:
                log.fatal("get albumartists failed: %s" % e)
                self.mpd_connect()
                return None

            for i in recv:
                if i == "":
                    continue
                #log.debug("Adding to cache albumartist: %s" % i)
                self.db_cache['Album Artists'][i] = {}

        return self.db_cache['Album Artists'].keys()



    def get_albums(self, mpd=None):
        """
        Gets the list of albums from mpd, enters albums into db_cache if needed

        Args:
            mpd: Optional musicpd.MPDClient object. If not supplied, the object's mpd object will be used.

        Returns:
            list of album names
        """
        if not mpd:
            mpd = self.mpd

        if not len(self.db_cache['Albums']):
            try:
                recv = mpd.list("album")
                #log.debug("albums: %s" % recv)
            except (musicpd.ConnectionError, BrokenPipeError) as e:
                log.fatal("get albums failed: %s" % e)
                self.mpd_connect()
                return None

            for i in recv:
                if i == "":
                    continue
                #log.debug("Adding to cache album: %s" % i)
                self.db_cache['Albums'][i] = {}

        return self.db_cache['Albums'].keys()



    def get_albums_by_artist(self, artist, mpd=None):
        """
        Gets the list of albums by an artist from mpd, enters albums into db_cache if needed

        Args:
            mpd: Optional musicpd.MPDClient object. If not supplied, the object's mpd object will be used.

        Returns:
            list of album names by an artist
        """
        if not mpd:
            mpd = self.mpd
        if not artist in self.db_cache['Artists']:
            self.db_cache['Artists'][artist] = {}

        if not len(self.db_cache['Artists'][artist]):
            try:
                recv = mpd.list("album", artist)
                #log.debug("albums: %s" % recv)
            except (musicpd.ConnectionError, BrokenPipeError) as e:
                log.fatal("get albums by artist failed: %s" % e)
                self.mpd_connect()
                return None

            for i in recv:
                if i== "":
                    continue
                #log.debug("Adding to cache artist / album: %s / %s" % (artist, i))
                self.db_cache['Artists'][artist][i] = []

        return self.db_cache['Artists'][artist]



    def get_albums_by_albumartist(self, artist, mpd=None):
        """
        Gets the list of albums by an albumartist from mpd, enters albums into db_cache if needed

        Args:
            mpd: Optional musicpd.MPDClient object. If not supplied, the object's mpd object will be used.

        Returns:
            list of album names by an albumartist
        """
        if not mpd:
            mpd = self.mpd
        if not artist in self.db_cache['Album Artists']:
            self.db_cache['Album Artists'][artist] = {}

        if not len(self.db_cache['Album Artists'][artist]):
            try:
                recv = mpd.list("album", "albumartist", artist)
                #log.debug("albums: %s" % recv)
            except (musicpd.ConnectionError, BrokenPipeError) as e:
                log.fatal("get albums by albumartist failed: %s" % e)
                self.mpd_connect()
                return None

            for i in recv:
                if i== "":
                    continue
                #log.debug("Adding to cache artist / album: %s / %s" % (artist, i))
                self.db_cache['Album Artists'][artist][i] = []

        return self.db_cache['Album Artists'][artist]



    def get_songs_by_album_by_artist(self, album, artist, mpd=None):
        """
        Finds songs by album and artist.

        Args:
            album: name of the album
            artist: name of the artist
            mpd: Optional musicpd.MPDClient object. If not supplied, the object's mpd object will be used.

        Returns:
            list of dictionaries containing song data
        """
        if not mpd:
            mpd = self.mpd

        if not len(self.db_cache['Artists'][artist][album]):
            try:
                recv = self.mpd.find("artist", artist, "album", album)
                #log.debug("songs: %s" % recv)
            except (musicpd.ConnectionError, BrokenPipeError) as e:
                log.fatal("get songs by album by artist failed: %s" % e)
                self.mpd_connect()
                return None

            for i in recv:
                if i== "":
                    continue
                #log.debug("Adding to cache artist / album / song: %s / %s / %s" % (artist, album, i))
                self.db_cache['Artists'][artist][album].append(i)

        return self.db_cache['Artists'][artist][album]



    def get_songs_by_album_by_genre(self, album, genre, mpd=None):
        """
        Finds songs by album and artist.

        Args:
            album: name of the album
            genre: name of the genre
            mpd: Optional musicpd.MPDClient object. If not supplied, the object's mpd object will be used.

        Returns:
            list of dictionaries containing song data
        """
        if not mpd:
            mpd = self.mpd

        if not len(self.db_cache['Genres'][genre][album]):
            try:
                recv = self.mpd.find("genre", genre, "album", album)
                #log.debug("songs: %s" % recv)
            except (musicpd.ConnectionError, BrokenPipeError) as e:
                log.fatal("get songs by album by genre failed: %s" % e)
                self.mpd_connect()
                return None

            for i in recv:
                if i== "":
                    continue
                #log.debug("Adding to cache genre / album / song: %s / %s / %s" % (genre, album, i))
                self.db_cache['Genres'][genre][album].append(i)

        return self.db_cache['Genres'][genre][album]



    def get_songs_by_album_by_albumartist(self, album, artist, mpd=None):
        """
        Finds songs by album and albumartist.

        Args:
            album: name of the album
            artist: name of the albumartist
            mpd: Optional musicpd.MPDClient object. If not supplied, the object's mpd object will be used.

        Returns:
            list of dictionaries containing song data
        """
        if not mpd:
            mpd = self.mpd

        if not len(self.db_cache['Album Artists'][artist][album]):
            try:
                recv = self.mpd.find("albumartist", artist, "album", album)
                #log.debug("songs: %s" % recv)
            except (musicpd.ConnectionError, BrokenPipeError) as e:
                log.fatal("get songs by album by albumartist failed: %s" % e)
                self.mpd_connect()
                return None

            for i in recv:
                if i== "":
                    continue
                #log.debug("Adding to cache albumartist / album / song: %s / %s / %s" % (artist, album, i))
                self.db_cache['Album Artists'][artist][album].append(i)

        return self.db_cache['Album Artists'][artist][album]



    def get_songs_by_album(self, album, mpd=None):
        """
        Finds songs by album.

        Args:
            album: name of the album
            mpd: Optional musicpd.MPDClient object. If not supplied, the object's mpd object will be used.

        Returns:
            list of dictionaries containing song data
        """
        if not mpd:
            mpd = self.mpd

        if not len(self.db_cache['Albums'][album]):
            self.db_cache['Albums'][album] = []
            try:
                recv = self.mpd.find("album", album)
                #log.debug("songs: %s" % recv)
            except (musicpd.ConnectionError, BrokenPipeError) as e:
                log.fatal("get songs by album failed: %s" % e)
                self.mpd_connect()
                return None

            for i in recv:
                if i== "":
                    continue
                #log.debug("Adding to cache album / song: %s / %s" % (album, i))
                self.db_cache['Albums'][album].append(i)

        return self.db_cache['Albums'][album]



    def get_genres(self, mpd=None):
        """
        Gets the list of genres from mpd, enters artists into db_cache if needed

        Args:
            mpd: Optional musicpd.MPDClient object. If not supplied, the object's mpd object will be used.

        Returns:
            list of genres
        """
        if not mpd:
            mpd = self.mpd

        if not len(self.db_cache['Genres']):
            try:
                recv = mpd.list("genre")
                #log.debug("genres: %s" % recv)
            except (musicpd.ConnectionError, BrokenPipeError) as e:
                log.fatal("get genres failed: %s" % e)
                self.mpd_connect()
                return None

            for i in recv:
                if i == "":
                    continue
                #log.debug("Adding to cache genres: %s" % i)
                self.db_cache['Genres'][i] = {}

        return self.db_cache['Genres'].keys()



    def get_albums_by_genre(self, genre, mpd=None):
        """
        Gets the list of albums by genre from mpd, enters albums into db_cache if needed

        Args:
            mpd: Optional musicpd.MPDClient object. If not supplied, the object's mpd object will be used.

        Returns:
            list of album names by an genre
        """
        if not mpd:
            mpd = self.mpd
        if not len(self.db_cache['Genres'][genre]):
            try:
                recv = self.mpd.list("album", "genre", genre)
                #log.debug("albums: %s" % recv)
            except (musicpd.ConnectionError, BrokenPipeError) as e:
                log.fatal("get album by genre: %s" % e)
                self.mpd_connect()
            for i in recv:
                if i == "":
                    continue
                #log.debug("Adding to cache genres / album: %s / %s" % (genre, i))
                self.db_cache['Genres'][genre][i] = []

        return self.db_cache['Genres'][genre]



    def add_to_playlist(self):
        """
        Displays confirmation dialog, presenting options to add, replace or cancel.
        """
        selected_items = self.browser_box.get_selected_rows()
        #log.debug("selected items: %s" % selected_items)
        if not selected_items[-1]['type'] in ("album", "song", "file"):
            return
        add_item_name = ""
        for i in range(1, len(selected_items)):
            if selected_items[i]['type'] == "song":
                add_item_name += selected_items[i]['data']['title']+" "
            else:
                add_item_name += selected_items[i]['value']+" "

        self.playlist_confirm_dialog = Gtk.Dialog("Update playlist?", self, Gtk.DialogFlags.MODAL, ("Add", 1, "Replace", 2, "Cancel", -4))
        self.playlist_confirm_dialog.get_content_area().add(Gtk.Label("Selected: "+add_item_name))
        self.playlist_confirm_dialog.get_content_area().set_size_request(300, 100)
        style_context = self.playlist_confirm_dialog.get_style_context()
        style_context.add_provider(self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.playlist_confirm_dialog.show_all()
        response = self.playlist_confirm_dialog.run()
        self.playlist_confirm_dialog.destroy()
        #log.debug("dialog response: %s" % response)

        try:
            if response == 2:
                ## Clear list before adding for "replace"
                self.mpd.clear()

            if response in (1, 2):
                if selected_items[-1]['type'] in ("song", "file"):
                    #log.debug("adding song: %s" % selected_items[-1]['data']['title'])
                    self.mpd.add(selected_items[-1]['data']['file'])
                elif selected_items[-1]['type'] == "album":
                    #log.debug("adding album: %s" % selected_items[-1]['value'])
                    if selected_items[-2]['type'] == "artist":
                        self.mpd.findadd("artist", selected_items[-2]['value'], "album", selected_items[-1]['value'])
                    elif selected_items[-2]['type'] == "albumartist":
                        self.mpd.findadd("albumartist", selected_items[-2]['value'], "album", selected_items[-1]['value'])
                    elif selected_items[-2]['type'] == "genre":
                        self.mpd.findadd("genre", selected_items[-2]['value'], "album", selected_items[-1]['value'])


        except (musicpd.ConnectionError, BrokenPipeError) as e:
            log.error("adding to playlist: %s" % e)
            self.mpd_connect()



    def edit_playlist(self):
        """
        Displays dialog with playlist edit options. Performs task based on user input.
        Play, move song up in playlist, down in playlist, delete from playlist.
        """
        index = self.playlist_list.get_selected_row().get_index()
        song = self.playlist_list.get_selected_row().get_child().data
        #log.debug("selected song: %s" % song)

        self.edit_playlist_dialog = Gtk.Dialog("Edit playlist", self, Gtk.DialogFlags.MODAL, ("Play", 4, "Up", 1, "Down", 2, "Delete", 3, "Cancel", -4))
        if 'title' in song:
            self.edit_playlist_dialog.get_content_area().add(Gtk.Label("Edit: "+song['title']))
        else:
            self.edit_playlist_dialog.get_content_area().add(Gtk.Label("Edit: "+song['file']))
        self.edit_playlist_dialog.get_content_area().set_size_request(300, 100)
        style_context = self.edit_playlist_dialog.get_style_context()
        style_context.add_provider(self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.edit_playlist_dialog.show_all();
        response = self.edit_playlist_dialog.run()
        self.edit_playlist_dialog.destroy()
        #log.debug("dialog response: %s" % response)

        try:
            if response == 1:
                #log.debug("Moving song up 1 place from %d" % index)
                if index > 0:
                    index -= 1
                    self.mpd.moveid(song['id'], index)
            elif response == 2:
                #log.debug("Moving song down 1 place from %d" % index)
                if index+1 < len(self.playlist_list.get_children()):
                    index += 1
                    self.mpd.moveid(song['id'], index)
            elif response == 3:
                #log.debug("Deleting song at %d" % index)
                self.mpd.deleteid(song['id'])
                index -= 1
                if index < 0:
                    index = 0
            elif response == 4:
                self.mpd.playid(song['id'])

        except (musicpd.ConnectionError, BrokenPipeError) as e:
            log.error("editing playlist: %s" % e)
            self.mpd_connect()
        except Exception as e:
            log.error("editing playlist: %s" % e)

        self.playlist_last_selected = index



    def playback_timeout(self, oneshot=False):
        """
        Updates playlist and playback if needed.
        Updates time info and progress bar.
        Resets timeout if oneshot == False.

        Args:
            oneshot: optional, if True, the next time will not be set.

        """
        #log.debug("TIMEOUT called")
        timeout = 0

        if self.do_update_playlist:
            self.do_update_playlist = False
            self.update_playlist()

        if self.do_update_playback:
            self.do_update_playback = False
            self.update_playback()
            timeout = self.sleep_play
        else:

            #log.debug("status at timeout: %s" % self.mpd_status['state'])
            if self.mpd_status['state'] == "stop":
                self.current_time_label.set_text("Stopped")
                self.song_progress.set_value(0)
                timeout = self.sleep_stop
            elif self.mpd_status['state'] == "pause":
                self.current_time_label.set_text(pp_time(self.last_update_offset)+" / "+pp_time(self.mpd_status['end_t'])+" Paused")
                timeout = self.sleep_pause
            elif self.mpd_status['state'] == "play":
                right_now = time.time()
                since_last_update = right_now - self.last_update_time
                ## Perform a full refresh every 5 secs
                if since_last_update >= 5:
                    #log.debug("FULL refresh")
                    self.update_playback()
                else:
                    ## Increment time and progress bar
                    current_offset = self.last_update_offset+int(since_last_update)
                    self.song_progress.set_value(current_offset)
                    self.current_time_label.set_text(pp_time(current_offset)+" / "+pp_time(self.mpd_status['end_t'])+" Playing")
                timeout = self.sleep_play
            else:
                log.info("unknown state: %s" % self.mpd_status['state'])

        if not oneshot:
            self.playback_timeout_id = GObject.timeout_add(timeout, self.playback_timeout)



    def playlist_info_popup(self):
        """
        Call SongInfoDialog to display the song data from the selected playlist row
        """
        song = self.playlist_list.get_selected_row().get_child().data
        dialog = SongInfoDialog(self, song)
        dialog.run()
        dialog.destroy()



    def browser_info_popup(self):
        """
        Call SongInfoDialog to display the song data from the selected browser row
        """
        song = self.browser_box.get_selected_rows()[-1]['data']
        dialog = SongInfoDialog(self, song)
        dialog.run()
        dialog.destroy()



    def get_files_list(self, path=""):
        """
        """
        try:
            """
            ## Make sure cache paths exist
            cache = None
            if len(path):
                path_list = re.split(r'/', path)
                log.debug("path list: %s" % path_list)
                cache = self.db_cache['Files']
                for p in path_list:
                    if p not in cache:
                        log.debug("caching file: %s" % p)
                        cache[p] = {}
                    cache = cache[p]
            log.debug("file cache: %s" % cache)

            if cache:
                rows = []
                for f in cache:
                    rows.append(f)
            """

            files = self.mpd.lsinfo(path)
            #log.debug("files from mpd: %s" % files)
            rows = []
            for f in files:
                #log.debug("files list: %s" % f)
                if 'directory' in f:
                    dirname = os.path.basename(f['directory'])
                    rows.append({'type': 'directory', 'value': dirname, 'data': {'name': dirname, 'dir': f['directory']}})
                elif 'file' in f:
                    filename = os.path.basename(f['file'])
                    finfo = None
                    if filename in cache:
                        finfo = cache[filename]
                    else:
                        finfo = self.mpd.lsinfo(f['file'])[0]
                    if not finfo:
                        finfo = { 'file': f['file']}
                    #log.debug("file info: %s %s" % (f['file'], finfo))
                    rows.append({'type': 'file', 'value': filename, 'data': finfo})
                    #cache[filename] = finfo
                    #log.debug("db cache files: %s" % self.db_cache['Files'])
            return rows

        except (musicpd.ConnectionError, BrokenPipeError) as e:
            log.error("listing files: %s" % e)
            self.mpd_connect()



    def outputs_changed(self, button, outputid):
        """
        Callback function passed to OutputsDialog.
        Expects the output ID, enables or disables the output based on the button's state.

        Args:
            button: Gtk.Button, event source
            outputid: output ID from the button

        """
        #log.debug("outputid: %s, %s" % (outputid, button.get_active()))
        try:
            if button.get_active():
                self.mpd.enableoutput(outputid)
            else:
                self.mpd.disableoutput(outputid)
            self.mpd_outputs = self.mpd.outputs()
        except (musicpd.ConnectionError, BrokenPipeError) as e:
            log.info("previous mpd command failed: %s" % e)
            self.mpd_connect()



    def options_changed(self, button, option):
        """
        Callback function passed to OptionsDialog.
        Sets/unsets options based on input.

        Args:
            button: Gtk.Button, event source
            option: name of the option to change
        """
        try:
            if option == "consume":
                self.mpd.consume(int(button.get_active()))
            elif option == "random":
                self.mpd.random(int(button.get_active()))
            elif option == "repeat":
                self.mpd.repeat(int(button.get_active()))
            elif option == "single":
                self.mpd.single(int(button.get_active()))
            else:
                log.info("unhandled option: %s" % option)
        except (musicpd.ConnectionError, BrokenPipeError) as e:
            log.info("previous mpd command failed: %s" % e)
            self.mpd_connect()






if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(description="MPD Frontend", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    arg_parser.add_argument("-c", "--config", default=default_config_file, action='store', help="Config file.")
    args = arg_parser.parse_args()

    config = configparser.ConfigParser()
    config.read(args.config)
    window = MPCFront(config)
    """
    try:
        if args.config:
            config = configparser.ConfigParser()
            config.read(args.config)
            #log.debug("config: %s" % config.sections())
            window = MPCFront(config)
        else:
            #window = MPCFront(None, args.host, args.port, args.dir, args.css, args.width, args.height, args.card, args.dev)
            print("Config file (-c) is a required argument.")
            sys.exit(1)
    except Exception as e:
        log.fatal("Application failed: %s" % e)
        sys.exit(1)
    """
    window.show_all()
    Gtk.main()
    sys.exit(0)

