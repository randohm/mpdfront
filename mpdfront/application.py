import sys, time, os
import logging
import queue
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GObject, Pango, GLib, Gio

from .constants import Constants
from .ui import MpdFrontWindow
from . import mpd

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
formatter = logging.Formatter(Constants.log_format)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
log.addHandler(handler)


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
        self.card_id = int(self.config.get("main", "sound_card"))
        self.device_id = int(self.config.get("main", "sound_device"))
        self.com_queue = queue.Queue()

        self.connect('activate', self.on_activate)
        self.connect('shutdown', self.on_quit)

        try:
            self.mpd_cmd = mpd.CommandsClient(config.get("main", "host"), int(config.get("main", "port")))
            self.mpd_idle = mpd.IdleClient(config.get("main", "host"), int(config.get("main", "port")), queue=self.com_queue)
        except Exception as e:
            log.error("could not connect to mpd: %s" % e)
            raise e

        self.mpd_stats = self.mpd_cmd.stats()
        log.debug("mpd stats: %s" % self.mpd_stats)
        self.mpd_outputs = self.mpd_cmd.outputs()
        log.debug("mpd outputs: %s" % self.mpd_outputs)

        #self.refresh_playback_timeout_id = GLib.timeout_add(500, self.refresh_playback)

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
        #log.debug("refreshing playback")

        if self.mpd_status['state'] == "stop":
            self.window.current_time_label.set_text("Stopped")
            self.window.song_progress.set_value(0)
        elif self.mpd_status['state'] == "pause":
            self.window.current_time_label.set_text(pp_time(int(float(self.mpd_status['elapsed']))) + " / " + pp_time(
                int(float(self.mpd_status['duration']))) + " Paused")
        elif self.mpd_status['state'] == "play":
            ## Perform a full refresh after 5 secs
            since_last_update = time.time() - self.last_update_time
            if since_last_update >= 5:
                log.debug("full refresh")
                self.window.update_playback()
                self.last_update_time = time.time()
                self.last_update_offset = int(float(self.mpd_status['elapsed']))
            else:
                ## Increment time and progress bar
                current_offset = self.last_update_offset + int(since_last_update)
                self.window.song_progress.set_value(current_offset)
                self.window.current_time_label.set_text(
                    pp_time(current_offset) + " / " + pp_time(int(float(self.mpd_status['duration']))) + " Playing")
        else:
            log.info("unknown state: %s" % self.mpd_status['state'])
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
