import os, time
import logging
import queue
import configparser
import threading

import gi
from . import mpd, data
from .message import QueueMessage
from .ui import MpdFrontWindow
from .constants import Constants

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GObject, Pango, GLib, Gio

log = logging.getLogger(__name__)

class MpdFrontApp(Gtk.Application):
    """
    Main application class for mpdfront.
    """
    def __init__(self, config:configparser, css_file:str=None, host:str=None, port:int=None, *args, **kwargs):
        if not config:
            err_msg = "config cannot be None"
            log.critical(err_msg)
            raise ValueError(err_msg)
        super().__init__(*args, **kwargs)
        self.config = config
        self.css_file = css_file
        self.card_id = int(config.get("main", "sound_card"))
        self.device_id = int(config.get("main", "sound_device"))
        self.idle_queue = queue.Queue()
        self.cmd_queue = queue.Queue()
        self.data_queue = queue.Queue()
        self.data_q_lock = threading.Lock()

        if host:
            self.host = host
        else:
            self.host = config.get("main", "host")
        if port:
            self.port = port
        else:
            self.port = int(config.get("main", "port"))
        try:
            self.mpd_cmd = mpd.Client(self.host, self.port)
            self.mpd_idle = mpd.IdleClientThread(host=self.host, port=self.port, queue=self.idle_queue, name="idleThread")
            self.mpd_cmd_thread = mpd.CommandClientThread(host=self.host, port=self.port, queue=self.cmd_queue,
                                                          data_queue=self.data_queue, lock=self.data_q_lock, name="cmdThread")
        except Exception as e:
            log.error("could not connect to mpd: %s" % e)
            raise e

        self.mpd_stats = self.get_mpd_stats()
        log.debug("mpd stats: %s" % self.mpd_stats)
        self.mpd_outputs = self.get_mpd_outputs()
        log.debug("mpd outputs: %s" % self.mpd_outputs)

        #self.content_tree = data.ContentTree(Constants.browser_1st_column_rows)
        #self.load_albumartists()
        #for i in range(5):
        #    albumartist = self.content_tree.get_top_layer().get_node_list()[0].get_child_layer().get_node_list()[i]
        #    self.load_albums_by_albumartist(albumartist)
        #    for j in range(len(albumartist.get_child_layer().get_node_list())):
        #        album = albumartist.get_child_layer().get_node_list()[j]
        #        self.load_songs_by_album_by_albumartist(album, albumartist)
        #data.Dumper.dump(self.content_tree.get_top_layer())

        # initialize cache
        #self.get_albumartists()
        #self.get_artists()
        #self.get_albums()
        #self.get_genres()
        #self.get_files_list()

        self.thread_comms_timeout_id = GLib.timeout_add(Constants.check_thread_comms_interval, self.idle_thread_comms_handler)
        self.thread_comms_timeout_id = GLib.timeout_add(Constants.playback_update_interval_play, self.refresh_playback)

        self.connect('activate', self.on_activate)
        self.connect('shutdown', self.on_quit)

    def on_activate(self, app):
        #try:
        self.window = MpdFrontWindow(application=self, config=self.config, queue=self.cmd_queue, data_queue=self.data_queue)
        #except Exception as e:
        #    log.critical("could not create main window: %s" % e)
        #    self.quit()
        #else:
        if self.css_file and os.path.isfile(self.css_file):
            log.debug("reading css file: %s" % self.css_file)
            self.css_provider = Gtk.CssProvider.new()
            try:
                self.css_provider.load_from_path(self.css_file)
                display = Gtk.Widget.get_display(self.window)
                Gtk.StyleContext.add_provider_for_display(display, self.css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            except Exception as e:
                log.error("could not load CSS: %s" % e)
                #raise e
        self.add_window(self.window)
        self.window.present()
        self.window.set_dividers()

    def on_quit(self, app):
        self.quit()

    def get_artists(self):
        """
        Gets the list of artists from mpd, enters artists into db_cache if needed
        :return: list of artist names
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
        :return: list of artist names
        """
        if not len(DataCache.cache['Album Artists']):
            recv = self.mpd_cmd.list("albumartist")
            #log.debug("received albumartists: %s" % recv)
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

    def get_albums_by_artist(self, artist:str):
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

    def get_albums_by_albumartist(self, artist:str):
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

    def get_songs_by_album_by_artist(self, album:str, artist:str):
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

    def get_songs_by_album_by_genre(self, album:str, genre:str):
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

    def get_songs_by_album_by_albumartist(self, album:str, artist:str):
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

    def get_songs_by_album(self, album:str):
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

    def get_albums_by_genre(self, genre:str):
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
        self.get_mpd_status()
        self.get_mpd_currentsong()
        self.data_q_lock.acquire()
        self.window.playback_display.update(data.mpd_status, data.mpd_currentsong, self.config.get("main", "music_dir"))
        self.data_q_lock.release()
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

    def idle_thread_comms_handler(self):
        msg = None
        try:
            if not self.idle_queue.empty():
                msg = self.idle_queue.get_nowait()
                log.debug("message from thread, type: %s" % type(msg))
        except Exception as e:
            return True

        if msg and isinstance(msg, QueueMessage):
            log.debug("processing queued message type: %s, item: %s" % (msg.get_type(), msg.get_item()))
            log.debug("data: %s" % msg.get_data())
            if msg.get_type() == Constants.message_type_change:
                if msg.get_item() == Constants.message_item_playlist:
                    self.window.playlist_list.update(msg.get_data()['playlist'], msg.get_data()['current'])
                if msg.get_item() == Constants.message_item_player:
                    self.window.playback_display.update(msg.get_data()['status'], msg.get_data()['current'],
                                                        self.config.get("main", "music_dir"))
        return True

    def get_mpd_response(self, type:str, item:str, data=None):
        if not type or not item:
            err_msg = "type, item are required arguments"
            log.error(err_msg)
            raise ValueError(err_msg)
        try:
            self.cmd_queue.put(QueueMessage(type=type, item=item, data=data))
            msg = self.data_queue.get()
            if msg and isinstance(msg, QueueMessage) and msg.get_type() == Constants.message_type_data and msg.get_item() == item:
                return msg.get_data()
            else:
                log.error("message mismatch. type: %s, item: %s" % (msg.get_type(), msg.get_item()))
                return None
        except Exception as e:
            log.error("error sending/getting data from mpd: %s" % e)
            return None

    def get_mpd_status(self):
        self.cmd_queue.put(QueueMessage(type=Constants.message_type_command, item="status"))

    def get_mpd_stats(self):
        return self.get_mpd_response(type=Constants.message_type_command, item="stats")

    def get_mpd_currentsong(self):
        self.cmd_queue.put(QueueMessage(type=Constants.message_type_command, item="currentsong"))

    def get_mpd_playlistinfo(self):
        return self.get_mpd_response(type=Constants.message_type_command, item="playlistinfo")

    def get_mpd_outputs(self):
        return self.get_mpd_response(type=Constants.message_type_command, item="outputs")

    def load_albumartists(self):
        try:
            n = self.content_tree.get_top_layer().get_node(Constants.topnode_name_albumartists)
            if not n:
                log.debug("no top node: %s" % n)
                return
            recv = self.get_mpd_response(type=Constants.message_type_command, item="list", data=["albumartist"])
            for r in recv:
                if r:
                    n.get_child_layer().add_node(data.ContentTreeNode({ 'name': r }))
        except Exception as e:
            log.error("could not load albumartists" % e)

    def load_albums_by_albumartist(self, albumartist:data.ContentTreeNode):
        try:
            recv = self.get_mpd_response(type=Constants.message_type_command, item="list",
                                         data=["album", "albumartist", albumartist.get_name()])
            log.debug("albums by albumartist '%s': %s" % (albumartist.get_name(), recv))
            for r in recv:
                albumartist.get_child_layer().add_node(data.ContentTreeNode({ 'name': r }))
        except Exception as e:
            log.error("could not load albums by albumartist '%s': %s" % (albumartist.get_name(), e))

    def load_songs_by_album_by_albumartist(self, album:data.ContentTreeNode, albumartist:data.ContentTreeNode):
        try:
            recv = self.get_mpd_response(type=Constants.message_type_command, item="find",
                                         data=["albumartist", albumartist.get_name(), "album", album.get_name()])
            log.debug("songs by albums by album by albumartist '%s' '%s': %s" % (album.get_name(), albumartist.get_name(), recv))
            for r in recv:
                new_node = data.ContentTreeNode({ 'name': r })
                new_node.set_name(r['title'])
                album.get_child_layer().add_node(new_node)
        except Exception as e:
            log.error("could not load albums by albumartist '%s': %s" % (albumartist.get_name(), e))

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
