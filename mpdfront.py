#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, re, time
import argparse
import logging
import threading
import musicpd
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from gi.repository import Gdk, GdkPixbuf



log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s %(levelname)s %(threadName)s::%(funcName)s(%(lineno)d): %(message)s")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
log.addHandler(handler)


symbol_previous = chr(9612)+chr(9664)
symbol_rewind = chr(9664)+chr(9664)
symbol_stop = chr(9608)
symbol_play= chr(9613)+chr(9654)
symbol_pause = chr(9613)+chr(9613)
symbol_cue = chr(9654)+chr(9654)
symbol_next = chr(9654)+chr(9612)



def pp_time(secs):
    """
    Pretty-print time convenience function. Takes a count of seconds and formats to MM:SS.

    Args:
        secs: int of number of seconds

    Returns:
        string with the time in the format of MM:SS
    """
    return "%d:%02d" % (int(int(secs)/60), int(secs)%60)



class MetadataLabel(Gtk.Label):
    """
    Gtk.Label with 2 accessible variables: data and t for type.
    """
    def set_metadata(self, data):
        self.data = data

    def set_metatype(self, t):
        self.type = t



class IndexedListBox(Gtk.ListBox):
    def set_index(self, index):
        self.index = index



class ColumnBrowser(Gtk.Box):
    """
    Column browser for a tree data structure. Inherits from GtkBox.
    Creates columns with a list of GtkScrolledWindow containing a GtkListBox.
    """
    def __init__(self, selected_callback, keypress_callback, cols=2, spacing=5, hexpand=True, vexpand=True):
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
            listbox.set_hexpand(hexpand)
            listbox.set_vexpand(vexpand)
            listbox.set_index(i)
            listbox.connect("row-selected", selected_callback)
            self.connect("key-press-event", keypress_callback)
            scroll.add(listbox)
            self.add(scroll)
            self.columns.append(listbox)



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



    def show_all(self):
        """
        Override super.show_all() to call all the columns' show_all() method, as well.
        """
        for i in self.columns:
            i.show_all()
        super.show_all()



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
            log.debug("data: %s" % i)
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
    """

    def __init__(self, host, port):
        """
        MPCFront constructor. Connects to MPD. Create main window and contained components.

        Args:
            host: string, hostname/IP of the MPD server
            port: int, TCP port of the MPD server
        """
        Gtk.Window.__init__(self, title="MPD - %s:%d" % (host, port))

        self.mpd_host = host
        self.mpd_port = port

        if not self.mpd_connect():
            Gtk.main_quit()

        self.mpd_stats = self.mpd.stats()
        log.debug("mpd stats: %s" % self.mpd_stats)

        self.run_idle = True            ## Allows the ilde thread to run
        self.update_song_time = False   ## Allows song time to be updated

        """
        Cache dictionary
            db_cache['Artist'][artist][album]        = list of dicts, song metadata
            db_cache['Album Artists'][artist][album] = ditto
            db_cache['Albums'][album]                = ditto
        """
        self.db_cache = {}
        self.db_cache['Album Artists'] = {}
        self.db_cache['Artists'] = {}
        self.db_cache['Albums'] = {}
        self.db_cache['Songs'] = {}
        self.db_cache['Files'] = {}

        ## topgrid is the toplevel layout container
        self.topgrid = Gtk.Grid()
        self.topgrid.set_hexpand(True)
        self.topgrid.set_vexpand(True)
        self.topgrid.set_row_spacing(5)
        self.topgrid.set_column_spacing(5)
        self.add(self.topgrid)

        ## Setup browser columns
        self.browser_box = ColumnBrowser(self.broswer_row_selected, self.browser_key_pressed, 4)
        self.topgrid.attach(self.browser_box, 0, 0, 2, 1)
        rows = []
        for i in self.db_cache.keys():
            rows.append({ 'type': 'category', 'value': i, 'data': None})
        self.browser_box.set_column_data(0, rows)

        ## Setup playback grid
        self.playback_grid = Gtk.Grid()
        self.playback_grid.set_row_spacing(5)
        self.playback_grid.set_column_spacing(5)
        self.topgrid.attach(self.playback_grid, 0, 1, 1, 1)
        self.current_artist_label = Gtk.Label("Artist")
        self.current_artist_label.set_halign(Gtk.Align.START)
        self.current_artist_label.set_line_wrap(True)
        #self.current_artist_label.set_hexpand(True)
        self.current_title_label = Gtk.Label("Title")
        self.current_title_label.set_halign(Gtk.Align.START)
        self.current_title_label.set_line_wrap(True)
        self.current_album_label = Gtk.Label("Album")
        self.current_album_label.set_halign(Gtk.Align.START)
        self.current_album_label.set_line_wrap(True)
        self.stats1_label = Gtk.Label("stats1")
        self.stats1_label.set_halign(Gtk.Align.START)
        self.stats2_label = Gtk.Label("stats2")
        self.stats2_label.set_halign(Gtk.Align.START)
        self.current_time_label = Gtk.Label("00:00")
        self.current_time_label.set_halign(Gtk.Align.START)
        self.end_time_label = Gtk.Label("00:00")
        self.end_time_label.set_halign(Gtk.Align.END)

        self.playback_grid.attach(self.current_artist_label, 0, 0, 1, 1)
        self.playback_grid.attach(self.current_title_label,  0, 1, 1, 1)
        self.playback_grid.attach(self.current_album_label,  0, 2, 1, 1)
        self.playback_grid.attach(self.stats1_label,         0, 3, 1, 1)
        self.playback_grid.attach(self.stats2_label,         0, 4, 1, 1)
        self.playback_grid.attach(self.current_time_label,   0, 5, 1, 1)
        self.playback_grid.attach(self.end_time_label,       1, 5, 1, 1)

        ## Setup playback button box
        self.playback_button_box = Gtk.Box()
        self.playback_grid.attach(self.playback_button_box, 0, 7, 2, 1)

        self.previous_button = Gtk.Button(symbol_previous)
        self.rewind_button = Gtk.Button(symbol_rewind)
        self.stop_button = Gtk.Button(symbol_stop)
        self.play_button = Gtk.Button(symbol_play)
        self.cue_button = Gtk.Button(symbol_cue)
        self.next_button = Gtk.Button(symbol_next)
        self.playback_button_box.pack_start(self.previous_button, True, True, 5)
        self.playback_button_box.pack_start(self.rewind_button, True, True, 5)
        self.playback_button_box.pack_start(self.stop_button, True, True, 5)
        self.playback_button_box.pack_start(self.play_button, True, True, 5)
        self.playback_button_box.pack_start(self.cue_button, True, True, 5)
        self.playback_button_box.pack_start(self.next_button, True, True, 5)

        self.song_progress = Gtk.Scrollbar()
        self.playback_grid.attach(self.song_progress, 0, 6, 2, 1)

        self.current_albumart = Gtk.Image()
        self.current_albumart.set_vexpand(True)
        #self.current_albumart.set_hexpand(True)
        self.playback_grid.attach(self.current_albumart, 1, 0, 1, 5)

        ## Setup playlist
        self.playlist_list = Gtk.ListBox()
        self.playlist_list.set_hexpand(True)
        self.playlist_list.set_vexpand(True)
        self.playlist_scroll = Gtk.ScrolledWindow()
        self.playlist_scroll.add(self.playlist_list)
        self.topgrid.attach(self.playlist_scroll, 1, 1, 1, 1)

        ## Dialogs
        self.playlist_confirm_dialog = None
        self.edit_playlist_dialog = None


        ## Set event handlers
        self.connect('key-press-event', self.key_pressed)
        self.connect("delete-event", Gtk.main_quit)
        self.connect("destroy-event", Gtk.main_quit)
        self.previous_button.connect("clicked", self.previous_clicked)
        self.rewind_button.connect("clicked", self.rewind_clicked)
        self.stop_button.connect("clicked", self.stop_clicked)
        self.play_button.connect("clicked", self.play_clicked)
        self.cue_button.connect("clicked", self.cue_clicked)
        self.next_button.connect("clicked", self.next_clicked)
        self.playlist_list.connect("row-selected", self.playlist_row_selected)
        #self.browser_box.connect("key-press-event", self.browser_key_pressed)

        self.update_playback()
        self.update_playlist()
        self.set_resizable(True)
        self.present()
        #self.column1.grab_focus()

        self.spawn_idle_thread()

        self.current_artist_label.modify_bg(Gtk.StateFlags.NORMAL, Gdk.Color(red=65535, blue=65535, green=65535))
        self.current_title_label.modify_bg(Gtk.StateFlags.NORMAL, Gdk.Color(red=65535, blue=65535, green=65535))
        self.current_album_label.modify_bg(Gtk.StateFlags.NORMAL, Gdk.Color(red=65535, blue=65535, green=65535))
        self.stats1_label.modify_bg(Gtk.StateFlags.NORMAL, Gdk.Color(red=65535, blue=65535, green=65535))
        self.stats2_label.modify_bg(Gtk.StateFlags.NORMAL, Gdk.Color(red=65535, blue=65535, green=65535))
        self.current_time_label.modify_bg(Gtk.StateFlags.NORMAL, Gdk.Color(red=65535, blue=65535, green=65535))
        self.end_time_label.modify_bg(Gtk.StateFlags.NORMAL, Gdk.Color(red=65535, blue=65535, green=65535))
        self.playback_button_box.modify_bg(Gtk.StateFlags.NORMAL, Gdk.Color(red=65535, blue=65535, green=65535))
        self.current_albumart.modify_bg(Gtk.StateFlags.NORMAL, Gdk.Color(red=65535, blue=65535, green=65535))



##  BEGIN EVENT HANDLERS

    def key_pressed(self, widget, event):
        """
        Keypress handler for toplevel widget
        """

        ctrl = (event.state & Gdk.ModifierType.CONTROL_MASK)
        mod1 = (event.state & Gdk.ModifierType.MOD1_MASK)
        mod2 = (event.state & Gdk.ModifierType.MOD2_MASK)

        try:
            if mod2 and event.keyval == Gdk.KEY_q:
                Gtk.main_quit()
            elif event.keyval == Gdk.KEY_p:
                log.debug("PLAY")
                self.mpd.play()
            elif event.keyval == Gdk.KEY_o:
                log.debug("PAUSE")
                self.mpd.pause()
            elif event.keyval == Gdk.KEY_i:
                log.debug("STOP")
                self.mpd.stop()
            elif event.keyval == Gdk.KEY_comma:
                log.debug("PREVIOUS")
                self.mpd.previous()
            elif event.keyval == Gdk.KEY_period:
                log.debug("NEXT")
                self.mpd.next()
            elif event.keyval == Gdk.KEY_l:
                log.debug("REWIND")
                self.mpd.seekcur("-5")
            elif event.keyval == Gdk.KEY_semicolon:
                log.debug("CUE")
                self.mpd.seekcur("+5")
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

        except musicpd.ConnectionError as e:
            log.info("previous mpd command failed: %s" % e)
            self.mpd_connect()

        except Exception as e:
            log.error("Unknown exception: %s" % e)

    def browser_key_pressed(self, widget, event):
        if event.keyval == Gdk.KEY_Return:
            log.debug("browser key: ENTER")
            self.add_to_playlist()

## Click handlers

    def previous_clicked(self, button):
        log.debug("PREVIOUS")
        try:
            self.mpd.previous()
        except musicpd.ConnectionError as e:
            log.info("previous failed: %s" % e)
            self.mpd_connect()
            self.mpd.previous()

    def rewind_clicked(self, button):
        log.debug("REWIND")
        try:
            self.mpd.seekcur("-5")
        except musicpd.ConnectionError as e:
            log.info("rewind failed: %s" % e)
            self.mpd_connect()
            self.mpd.seekcur("-5")

    def stop_clicked(self, button):
        log.debug("STOP")
        try:
            self.mpd.stop()
        except musicpd.ConnectionError as e:
            log.info("stop failed: %s" % e)
            self.mpd_connect()
            self.mpd.stop()

    def play_clicked(self, button):
        self.play_or_pause()

    def cue_clicked(self, button):
        log.debug("CUE")
        try:
            self.mpd.seekcur("+5")
        except musicpd.ConnectionError as e:
            log.info("cue failed: %s" % e)
            self.mpd_connect()
            self.mpd.seekcur("+5")

    def next_clicked(self, button):
        log.debug("NEXT")
        try:
            self.mpd.next()
        except musicpd.ConnectionError as e:
            log.info("next failed: %s" % e)
            self.mpd_connect()
            self.mpd.next()

    def playlist_row_selected(self, listbox, row):
        if not row:
            return
        value = row.get_child().get_text()
        log.debug("playlist selected: %s" % value)

    def broswer_row_selected(self, listbox, row):
        child = row.get_child()
        if child:
            metatype = child.type
            value = child.get_text()
            log.debug("col %d, %s: %s" % (listbox.index, metatype, value))
            if metatype == "category":
                if value == "Album Artists":
                    artists = self.get_albumartists()
                    log.debug("albumartists: %s" % artists)
                    rows = []
                    for a in artists:
                        rows.append({ 'type': 'albumartist', 'value': a, 'data': None })
                    self.browser_box.set_column_data(listbox.index+1, rows)

                elif value == "Artists":
                    artists = self.get_artists()
                    log.debug("artists: %s" % artists)
                    rows = []
                    for a in artists:
                        rows.append({ 'type': 'artist', 'value': a, 'data': None })
                    self.browser_box.set_column_data(listbox.index+1, rows)

            elif metatype == "albumartist":
                albums = self.get_albums_by_albumartist(value)
                log.debug("albums: %s" % albums)
                rows = []
                for a in albums:
                    rows.append({ 'type': 'album', 'value': a, 'data': None })
                self.browser_box.set_column_data(listbox.index+1, rows)
    
            elif metatype == "artist":
                albums = self.get_albums_by_artist(value)
                log.debug("albums: %s" % albums)
                rows = []
                for a in albums:
                    rows.append({ 'type': 'album', 'value': a, 'data': None })
                self.browser_box.set_column_data(listbox.index+1, rows)
    
            elif metatype == "album":
                selected_items = self.browser_box.get_selected_rows()
                log.debug("selected items: %s" % selected_items)
                last_type = selected_items[listbox.index-1]['type']
                last_value = selected_items[listbox.index-1]['value']
                log.debug("%s %s" % (value, last_value))
                songs = None
                if last_type == "albumartist":
                    songs = self.get_songs_by_album_by_albumartist(value, last_value)
    
                elif last_type == "artist":
                    songs = self.get_songs_by_album_by_artist(value, last_value)
    
                rows = []
                for s in songs:
                    log.debug(s)
                    track = re.sub(r'/.*', '',  s['track'])
                    rows.append({ 'type': 'song', 'value': track+" "+ s['title'], 'data': s })
                self.browser_box.set_column_data(listbox.index+1, rows)

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
            return None
        return True



    def play_or_pause(self):
        """
        Check the player status, play if stopped, pause otherwise.
        """
        if self.mpd_status['state'] == "stop":
            log.debug("PLAY")
            try:
                self.mpd.play()
            except musicpd.ConnectionError as e:
                log.info("play failed: %s" % e)
                self.mpd_connect()
                self.mpd.play()
        else:
            log.debug("PAUSE")
            try:
                self.mpd.pause()
            except musicpd.ConnectionError as e:
                log.info("pause failed: %s" % e)
                self.mpd_connect()
                self.mpd.pause()



    def set_current_albumart(self):
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale("cover.jpg", 200, 200, True)
        self.current_albumart.set_from_pixbuf(pixbuf)



    def update_playback(self, mpd=None):
        """
        Updates playback display
        """
        if not mpd:
            mpd = self.mpd
        try:
            self.mpd_status = mpd.status()
            self.mpd_currentsong = mpd.currentsong()
            log.debug("status: %s" % self.mpd_status)
            log.debug("currentsong: %s" % self.mpd_currentsong)
        except musicpd.ConnectionError as e:
            log.debug("Attempting reconnect: %s" % e)
            self.mpd_connect()
            self.mpd_status = mpd.status()
            self.mpd_currentsong = mpd.currentsong()


        if self.mpd_currentsong:
            self.current_artist_label.set_markup("<big><b>%s</b></big>" % self.mpd_currentsong['artist'])
            self.current_title_label.set_markup("<big>%s</big>" % self.mpd_currentsong['title'])
            self.current_album_label.set_text(self.mpd_currentsong['album'])

        if 'audio' in self.mpd_status.keys():
            self.stats1_label.set_text(self.mpd_status['audio'])

        if 'bitrate' in self.mpd_status.keys():
            self.stats2_label.set_text(self.mpd_status['bitrate'])

        if 'time' in self.mpd_status.keys():
            #self.song_progress.setMaximum(int(mpd_current['time']))
            #ui.songProgress.setValue(int(mpd_status['curr_t']))
            self.mpd_status['curr_t'], self.mpd_status['end_t'] = self.mpd_status['time'].split(r':', 1)
            self.current_time_label.set_text(pp_time(self.mpd_status['curr_t']))
            self.end_time_label.set_text(pp_time(self.mpd_status['end_t']))

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
            plist = mpd.playlist()
        except musicpd.ConnectionError as e:
            log.error("could not fetch playlist: %s" % e)
            self.mpd_connect()
            return None
        playlist = []
        for line in plist:
            file_type, filename = line.split(': ', 1)
            file_info = mpd.lsinfo(filename)
            log.debug("file_info: %s" % file_info)
            playlist.append(file_info[0])
        return playlist



    def update_playlist(self, mpd=None):
        if not mpd:
            mpd = self.mpd
        playlist = self.get_playlist(mpd)
        log.debug("playlist: %s" % playlist)
        if not playlist:
            return

        ## Empty list if aleady populated
        children = self.playlist_list.get_children()
        if children:
            for c in children:
                self.playlist_list.remove(c)
                c.destroy()

        ## Add songs to the list
        for song in playlist:
            label = MetadataLabel(song['title'])
            label.set_metatype('song')
            label.set_metadata(song)
            label.set_halign(Gtk.Align.START)
            self.playlist_list.add(label)

        self.playlist_list.show_all()


    def idle_thread(self):
        """
        Function that runs in the idle thread created by spawn_idle_thread()
        """
        mpd = musicpd.MPDClient()
        try:
            mpd.connect(self.mpd_host, self.mpd_port)
        except musicpd.ConnectionError as e:
            log.critical("idle thread could not connect to MPD: %s" % e)
            return None

        while self.run_idle:
            try:
                mpd.send_idle()
                changes = mpd.fetch_idle()
            except musicpd.ConnectionError as e:
                log.error("idle failed: %s" % e)
                self.mpd_connect()
                continue
            except Exception as e:
                log.error(e)
            self.update_song_time = False
            log.debug("changes: %s" % changes)
            for c in changes:
                if c == "playlist":
                    self.update_playlist(mpd)
                elif c == "player":
                    self.update_playback(mpd)
                else:
                    log.info("Unhandled change: %s" % changed)
            self.update_song_time = True



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
                log.debug("artists: %s" % recv)
            except musicpd.ConnectionError as e:
                log.fatal("get artists failed: %s" % e)
                self.mpd_connect()
                return None

            for i in recv:
                if i == "":
                    continue
                log.debug("Adding to cache artist: %s" % i)
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
                log.debug("albumartists: %s" % recv)
            except musicpd.ConnectionError as e:
                log.fatal("get albumartists failed: %s" % e)
                self.mpd_connect()
                return None

            for i in recv:
                if i == "":
                    continue
                log.debug("Adding to cache albumartist: %s" % i)
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
                log.debug("albums: %s" % recv)
            except musicpd.ConnectionError as e:
                log.fatal("get albums failed: %s" % e)
                self.mpd_connect()
                return None

            for i in recv:
                if i == "":
                    continue
                log.debug("Adding to cache album: %s" % i)
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
                log.debug("albums: %s" % recv)
            except musicpd.ConnectionError as e:
                log.fatal("get albums by artist failed: %s" % e)
                self.mpd_connect()
                return None

            for i in recv:
                if i== "":
                    continue
                log.debug("Adding to cache artist / album: %s / %s" % (artist, i))
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
                recv = mpd.list("album", artist)
                log.debug("albums: %s" % recv)
            except musicpd.ConnectionError as e:
                log.fatal("get albums by albumartist failed: %s" % e)
                self.mpd_connect()
                return None

            for i in recv:
                if i== "":
                    continue
                log.debug("Adding to cache artist / album: %s / %s" % (artist, i))
                self.db_cache['Album Artists'][artist][i] = []

        return self.db_cache['Album Artists'][artist]



    def get_songs_by_album_by_artist(self, album, artist, mpd=None):
        if not mpd:
            mpd = self.mpd

        if not len(self.db_cache['Artists'][artist][album]):
            try:
                recv = self.mpd.find("artist", artist, "album", album)
                log.debug("songs: %s" % recv)
            except musicpd.ConnectionError as e:
                log.fatal("get songs by album by artist failed: %s" % e)
                self.mpd_connect()
                return None

            for i in recv:
                if i== "":
                    continue
                log.debug("Adding to cache artist / album / song: %s / %s / %s" % (artist, album, i))
                self.db_cache['Artists'][artist][album].append(i)

        return self.db_cache['Artists'][artist][album]



    def get_songs_by_album_by_albumartist(self, album, artist, mpd=None):
        if not mpd:
            mpd = self.mpd

        if not len(self.db_cache['Album Artists'][artist][album]):
            try:
                recv = self.mpd.find("albumartist", artist, "album", album)
                log.debug("songs: %s" % recv)
            except musicpd.ConnectionError as e:
                log.fatal("get songs by album by albumartist failed: %s" % e)
                self.mpd_connect()
                return None

            for i in recv:
                if i== "":
                    continue
                log.debug("Adding to cache albumartist / album / song: %s / %s / %s" % (artist, album, i))
                self.db_cache['Album Artists'][artist][album].append(i)

        return self.db_cache['Album Artists'][artist][album]



    def get_songs_by_album(self, album, mpd=None):
        if not mpd:
            mpd = self.mpd

        if not len(self.db_cache['Albums'][album]):
            self.db_cache['Albums'][album] = []
            try:
                recv = self.mpd.find("album", album)
                log.debug("songs: %s" % recv)
            except musicpd.ConnectionError as e:
                log.fatal("get songs by album failed: %s" % e)
                self.mpd_connect()
                return None

            for i in recv:
                if i== "":
                    continue
                log.debug("Adding to cache album / song: %s / %s" % (album, i))
                self.db_cache['Albums'][album].append(i)

        return self.db_cache['Albums'][album]



    def add_to_playlist(self):
        """
        """
        if self.playlist_confirm_dialog != None and self.playlist_confirm_dialog.is_active() and self.playlist_confirm_dialog.has_toplevel_focus():
            return

        selected_items = self.browser_box.get_selected_rows()
        log.debug("selected items: %s" % selected_items)
        add_item_name = ""
        for i in range(1, len(selected_items)):
            add_item_name += selected_items[i]['value']+" "

        self.playlist_confirm_dialog = Gtk.Dialog("Update playlist?", self, Gtk.DialogFlags.MODAL, ("Add", 1, "Replace", 2, "Cancel", -4))
        self.playlist_confirm_dialog.get_content_area().add(Gtk.Label("Selected: "+add_item_name))
        self.playlist_confirm_dialog.get_content_area().set_size_request(300, 200)
        self.playlist_confirm_dialog.show_all()
        response = self.playlist_confirm_dialog.run()
        self.playlist_confirm_dialog.destroy()
        log.debug("dialog response: %s" % response)

        try:
            if response == 2:
                ## Clear list before adding for "replace"
                #self.mpd.clear()
                None

            if response in (1, 2):
                self.mpd.add(selected_items[-1]['data']['file'])

        except musicpd.ConnectionError as e:
            log.error("adding to playlist: %s" % e)
            self.mpd_connect()



    def edit_playlist(self):
        """
        """
        None





if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(description="MPD Frontend", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    #arg_parser.add_argument("-v", "--verbose", action='store_true', help="Turn on verbose output.")
    arg_parser.add_argument("-H", "--host", default="localhost", action='store', help="Remote host name or IP address.")
    arg_parser.add_argument("-p", "--port", default=6600, type=int, action='store', help="Remote TCP port number.")
    args = arg_parser.parse_args()

    window = MPCFront(args.host, args.port)
    window.set_size_request(1280, 720)
    window.present()
    window.show()
    window.show_all()
    Gtk.main()
    sys.exit(0)

