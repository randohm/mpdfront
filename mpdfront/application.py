import time, os
import logging
import queue
import gi
from .ui import MpdFrontWindow
from . import mpd
from .constants import Constants

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GObject, Pango, GLib, Gio

log = logging.getLogger(__name__)

class MpdFrontApp(Gtk.Application):
    css_provider = None
    mpd_client = None
    mpd_idle_client = None
    last_update_time = 0  ## Epoch time of last display update
    last_update_offset = 0  ## Time offset into a song at the last display update

    def __init__(self, config=None, css_file=None, *args, **kwargs):
        if not config:
            err_msg = "config cannot be None"
            log.error(err_msg)
            raise ValueError(err_msg)
        super().__init__(*args, **kwargs)
        self.config = config
        self.css_file = css_file
        self.card_id = int(config.get("main", "sound_card"))
        self.device_id = int(config.get("main", "sound_device"))
        self.host = config.get("main", "host")
        self.port = int(config.get("main", "port"))
        self.idle_queue = queue.Queue()

        self.connect('activate', self.on_activate)
        self.connect('shutdown', self.on_quit)

        try:
            self.mpd_cmd = mpd.Client(self.host, self.port)
            self.mpd_idle = mpd.IdleClientThread(host=self.host, port=self.port, queue=self.idle_queue)
        except Exception as e:
            log.error("could not connect to mpd: %s" % e)
            raise e

        self.mpd_stats = self.mpd_cmd.stats()
        log.debug("mpd stats: %s" % self.mpd_stats)
        self.mpd_outputs = self.mpd_cmd.outputs()
        log.debug("mpd outputs: %s" % self.mpd_outputs)

        # initialize cache
        self.get_albumartists()
        self.get_artists()
        self.get_albums()
        self.get_genres()
        self.get_files_list()

        self.thread_comms_timeout_id = GLib.timeout_add(Constants.check_thread_comms_interval, self.thread_comms_handler)
        self.thread_comms_timeout_id = GLib.timeout_add(Constants.playback_update_interval_play, self.refresh_playback)

    def on_activate(self, app):
        self.window = MpdFrontWindow(application=self, config=self.config)
        if self.css_file and os.path.isfile(self.css_file):
            log.debug("reading css file: %s" % self.css_file)
            self.css_provider = Gtk.CssProvider.new()
            try:
                self.css_provider.load_from_path(self.css_file)
                display = Gtk.Widget.get_display(self.window)
                Gtk.StyleContext.add_provider_for_display(display, self.css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            except Exception as e:
                log.error("could not load CSS: %s" % e)
                raise e
        self.window.present()
        self.window.set_dividers()

    def on_quit(self, app):
        self.quit()

    def get_artists(self):
        """
        Gets the list of artists from mpd, enters artists into db_cache if needed
        Returns:
            list of artist names
        """
        if not len(DataCache.cache['Artists']):
            recv = self.mpd_cmd.list("artist")
            for i in recv:
                if i == "":
                    continue
                DataCache.cache['Artists'][i] = {}
        return DataCache.cache['Artists'].keys()

    def get_albumartists(self):
        """
        Gets the list of albumartists from mpd, enters albumartists into db_cache if needed
        Returns:
            list of artist names
        """
        if not len(DataCache.cache['Album Artists']):
            recv = self.mpd_cmd.list("albumartist")
            for i in recv:
                if i == "":
                    continue
                DataCache.cache['Album Artists'][i] = {}
        return DataCache.cache['Album Artists'].keys()

    def get_albums(self):
        """
        Gets the list of albums from mpd, enters albums into db_cache if needed
        Returns:
            list of album names
        """
        if not len(DataCache.cache['Albums']):
            recv = self.mpd_cmd.list("album")
            for i in recv:
                if i == "":
                    continue
                DataCache.cache['Albums'][i] = {}
        return DataCache.cache['Albums'].keys()

    def get_albums_by_artist(self, artist:str=None):
        """
        Gets the list of albums by an artist from mpd, enters albums into db_cache if needed
        Args:
            artist: name of artist whose albums to return 
        Returns:
            list of album names by an artist
        """
        if not artist:
            log.debug("value for artist is None")
            return None
        if not artist in DataCache.cache['Artists']:
            DataCache.cache['Artists'][artist] = {}
        if not len(DataCache.cache['Artists'][artist]):
            recv = self.mpd_cmd.list("album", artist)
            for i in recv:
                if i == "":
                    continue
                DataCache.cache['Artists'][artist][i] = []
        return DataCache.cache['Artists'][artist]

    def get_albums_by_albumartist(self, artist:str=None):
        """
        Gets the list of albums by an albumartist from mpd, enters albums into db_cache if needed
        Args:
            artist: name of artist whose albums to return 
        Returns:
            list of album names by an albumartist
        """
        if not artist:
            log.debug("value for artist is None")
            return None
        if not artist in DataCache.cache['Album Artists']:
            DataCache.cache['Album Artists'][artist] = {}

        if not len(DataCache.cache['Album Artists'][artist]):
            recv = self.mpd_cmd.list("album", "albumartist", artist)
            for i in recv:
                if i == "":
                    continue
                DataCache.cache['Album Artists'][artist][i] = []
        return DataCache.cache['Album Artists'][artist]

    def get_songs_by_album_by_artist(self, album:str=None, artist:str=None):
        """
        Finds songs by album and artist.
        Args:
            album: name of the album
            artist: name of the artist
        Returns:
            list of dictionaries containing song data
        """
        if not len(DataCache.cache['Artists'][artist][album]):
            recv = self.mpd_cmd.find("artist", artist, "album", album)
            for i in recv:
                if i == "":
                    continue
                DataCache.cache['Artists'][artist][album].append(i)
        return DataCache.cache['Artists'][artist][album]

    def get_songs_by_album_by_genre(self, album:str=None, genre:str=None):
        """
        Finds songs by album and artist.
        Args:
            album: name of the album
            genre: name of the genre
        Returns:
            list of dictionaries containing song data
        """
        if not len(DataCache.cache['Genres'][genre][album]):
            recv = self.mpd_cmd.find("genre", genre, "album", album)
            for i in recv:
                if i == "":
                    continue
                DataCache.cache['Genres'][genre][album].append(i)
        return DataCache.cache['Genres'][genre][album]

    def get_songs_by_album_by_albumartist(self, album:str=None, artist:str=None):
        """
        Finds songs by album and albumartist.
        Args:
            album: name of the album
            artist: name of the albumartist
        Returns:
            list of dictionaries containing song data
        """
        if not len(DataCache.cache['Album Artists'][artist][album]):
            recv = self.mpd_cmd.find("albumartist", artist, "album", album)
            for i in recv:
                if i == "":
                    continue
                DataCache.cache['Album Artists'][artist][album].append(i)
        return DataCache.cache['Album Artists'][artist][album]

    def get_songs_by_album(self, album:str=None):
        """
        Finds songs by album.
        Args:
            album: name of the album
        Returns:
            list of dictionaries containing song data
        """
        if not len(DataCache.cache['Albums'][album]):
            DataCache.cache['Albums'][album] = []
            recv = self.mpd_cmd.find("album", album)
            for i in recv:
                if i == "":
                    continue
                DataCache.cache['Albums'][album].append(i)
        return DataCache.cache['Albums'][album]

    def get_genres(self):
        """
        Gets the list of genres from mpd, enters artists into db_cache if needed
        Returns:
            list of genres
        """
        if not len(DataCache.cache['Genres']):
            recv = self.mpd_cmd.list("genre")
            for i in recv:
                if i == "":
                    continue
                DataCache.cache['Genres'][i] = {}
        return DataCache.cache['Genres'].keys()

    def get_albums_by_genre(self, genre:str=None):
        """
        Gets the list of albums by genre from mpd, enters albums into db_cache if needed

        Args:
            genre: genre of albums to get

        Returns:
            list of album names by an genre
        """
        if not len(DataCache.cache['Genres'][genre]):
            recv = self.mpd_cmd.list("album", "genre", genre)
            for i in recv:
                if i == "":
                    continue
                DataCache.cache['Genres'][genre][i] = []
        return DataCache.cache['Genres'][genre]

    def refresh_playback(self):
        """
        Updates playlist and playback if needed.
        Updates time info and progress bar.
        """
        mpd_status = self.mpd_cmd.status()
        current_song = self.mpd_cmd.currentsong()
        self.window.playback_display.update(mpd_status, current_song, self.config.get("main", "music_dir"))
        return True

    def get_files_list(self, path=""):
        files = self.mpd_cmd.lsinfo(path)
        rows = []
        for f in files:
            if 'directory' in f:
                dirname = os.path.basename(f['directory'])
                rows.append(
                    {'type': 'directory', 'value': dirname, 'data': {'name': dirname, 'dir': f['directory']}})
            elif 'file' in f:
                filename = os.path.basename(f['file'])
                finfo = None
                finfo = self.mpd_cmd.lsinfo(f['file'])[0]
                if not finfo:
                    finfo = {'file': f['file']}
                rows.append({'type': 'file', 'value': filename, 'data': finfo})
        return rows

    def thread_comms_handler(self):
        msg = None
        try:
            if not self.idle_queue.empty():
                msg = self.idle_queue.get_nowait()
                log.debug("message from thread: %s" % msg)
        except Exception as e:
            return True

        if msg and isinstance(msg, dict) and 'type' in msg.keys():
            log.debug("processing queued message type: %s" % msg['type'])
            if msg['type'] == Constants.message_type_change:
                if msg['item'] == Constants.message_item_playlist:
                    self.window.playlist_list.update(msg['playlist'], msg['current'])
                if msg['item'] == Constants.message_item_player:
                    self.window.playback_display.update(msg['status'], msg['current'], self.config.get("main", "music_dir"))
        return True

class DataCache():
    cache = {
        'Album Artists': {},
        'Artists': {},
        'Albums': {},
        'Files': {},
        'Genres': {},
        'Songs': {},
    }

    @staticmethod
    def clear():
        for k in DataCache.cache.keys():
            DataCache.cache[k] = {}
