import os
import logging
import queue
import configparser

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
        super().__init__(*args, **kwargs)
        self.config = config
        self.css_file = css_file
        self.card_id = int(config.get("main", "sound_card"))
        self.device_id = int(config.get("main", "sound_device"))
        self.idle_queue = queue.Queue()

        if host:
            self.host = host
        else:
            self.host = config.get("main", "host")
        if port:
            self.port = port
        else:
            self.port = int(config.get("main", "port"))
        try:
            self.mpd_client = mpd.Client(self.host, self.port)
            self.mpd_idle_thread = mpd.IdleClientThread(host=self.host, port=self.port, queue=self.idle_queue, name="idleThread")
        except Exception as e:
            log.error("could not connect to mpd: %s" % e)
            raise e

        self._mpd_callbacks = {
            'add': self.mpd_client.add,
            'clear': self.mpd_client.clear,
            'consume': self.mpd_client.consume,
            'currentsong': self.mpd_client.currentsong,
            'deleteid': self.mpd_client.deleteid,
            'disableoutput': self.mpd_client.disableoutput,
            'enableoutput': self.mpd_client.enableoutput,
            'fetch_idle': self.mpd_client.fetch_idle,
            'find': self.mpd_client.find,
            'findadd': self.mpd_client.findadd,
            'list': self.mpd_client.list,
            'lsinfo': self.mpd_client.lsinfo,
            'moveid': self.mpd_client.moveid,
            'next': self.mpd_client.next,
            'outputs': self.mpd_client.outputs,
            'pause': self.mpd_client.pause,
            'play': self.mpd_client.play,
            'play_or_pause': self.mpd_client.play_or_pause,
            'playid': self.mpd_client.playid,
            'playlistinfo': self.mpd_client.playlistinfo,
            'previous': self.mpd_client.previous,
            'random': self.mpd_client.random,
            'repeat': self.mpd_client.repeat,
            'seekcur': self.mpd_client.seekcur,
            'send_idle': self.mpd_client.send_idle,
            'single': self.mpd_client.single,
            'stats': self.mpd_client.stats,
            'status': self.mpd_client.status,
            'stop': self.mpd_client.stop,
            'toggle': self.mpd_client.play_or_pause,
        }

        self.mpd_stats = self.mpd_stats()
        log.debug("mpd stats: %s" % self.mpd_stats)
        self.mpd_outputs = self.mpd_outputs()
        log.debug("mpd outputs: %s" % self.mpd_outputs)

        self.content_tree = data.ContentTree(Constants.browser_1st_column_rows)
        self.load_albumartists()
        self.load_artists()
        self.load_albums()
        self.load_genres()
        self.load_files_list()
        """
        for i in range(5):
            albumartist = self.content_tree.get_top_layer().get_node(Constants.topnode_name_albumartists).get_child_layer().get_node_list()[i]
            self.load_albums_by_albumartist(albumartist)
            for j in range(len(albumartist.get_child_layer().get_node_list())):
                a = albumartist.get_child_layer().get_node_list()[j]
                self.load_songs_by_album_by_albumartist(a, albumartist)

            artist = self.content_tree.get_top_layer().get_node(Constants.topnode_name_artists).get_child_layer().get_node_list()[i]
            self.load_albums_by_artist(artist)
            for j in range(len(artist.get_child_layer().get_node_list())):
                a = artist.get_child_layer().get_node_list()[j]
                self.load_songs_by_album_by_artist(a, artist)

            album = self.content_tree.get_top_layer().get_node(Constants.topnode_name_albums).get_child_layer().get_node_list()[i]
            self.load_songs_by_album(album)

            genre = self.content_tree.get_top_layer().get_node(Constants.topnode_name_genres).get_child_layer().get_node_list()[i]
            self.load_albums_by_genre(genre)
            for j in range(len(genre.get_child_layer().get_node_list())):
                a = genre.get_child_layer().get_node_list()[j]
                self.load_songs_by_album_by_genre(a, genre)

            files_list = self.content_tree.get_top_layer().get_node(Constants.topnode_name_files).get_child_layer().get_node_list()[i]
        """
        #data.Dumper.dump(self.content_tree.get_top_layer())

        self.thread_comms_timeout_id = GLib.timeout_add(Constants.check_thread_comms_interval, self.idle_thread_comms_handler)
        self.thread_comms_timeout_id = GLib.timeout_add(Constants.playback_update_interval_play, self.refresh_playback)

        self.connect('activate', self.on_activate)
        self.connect('shutdown', self.on_quit)

    def __getattr__(self, attr):
        #log.debug("called __getattr__: %s" % attr)
        if attr.startswith("mpd_"):
            command = attr.replace("mpd_", "")
            if command not in self._mpd_callbacks:
                raise AttributeError("object has no attribute %s" % attr)
        else:
            raise AttributeError("object has no attribute %s" % attr)
        return lambda *args, **kwargs: self._mpd_callbacks[command](*args, **kwargs)

    def on_activate(self, app):
        #try:
        self.window = MpdFrontWindow(application=self, config=self.config, content_tree=self.content_tree)
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
        self.refresh_playlist()
        self.refresh_playback()

    def on_quit(self, app):
        self.quit()

    def get_artists(self):
        """
        Gets the list of artists from mpd, enters artists into db_cache if needed
        :return: list of artist names
        """
        if not len(DataCache.cache['Artists']):
            recv = self.mpd_client.list("artist")
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
            recv = self.mpd_client.list("albumartist")
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
            recv = self.mpd_client.list("album")
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
            recv = self.mpd_client.list("album", artist)
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
            recv = self.mpd_client.list("album", "albumartist", artist)
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
            recv = self.mpd_client.find("artist", artist, "album", album)
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
            recv = self.mpd_client.find("genre", genre, "album", album)
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
            recv = self.mpd_client.find("albumartist", artist, "album", album)
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
            recv = self.mpd_client.find("album", album)
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
            recv = self.mpd_client.list("genre")
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
            recv = self.mpd_client.list("album", "genre", genre)
            for i in recv:
                if i == "":
                    continue
                DataCache.cache['Genres'][genre][i] = []
        return DataCache.cache['Genres'][genre]

    def refresh_playback(self):
        """
        Updates playback, time, info and progress bar.
        """
        mpd_status = self.mpd_client.status()
        currentsong = self.mpd_client.currentsong()
        self.window.playback_display.update(mpd_status, currentsong, self.config.get("main", "music_dir"))
        return True

    def refresh_playlist(self):
        """
        Updates playback, time, info and progress bar.
        """
        playlistinfo = self.mpd_client.playlistinfo()
        currentsong = self.mpd_client.currentsong()
        self.window.playlist_list.update(playlistinfo, currentsong)
        return True

    def get_files_list(self, path=""):
        files = self.mpd_client.lsinfo(path)
        rows = []
        for f in files:
            if 'directory' in f:
                dirname = os.path.basename(f['directory'])
                rows.append(
                    {'type': 'directory', 'value': dirname, 'data': {'name': dirname, 'dir': f['directory']}})
            elif 'file' in f:
                filename = os.path.basename(f['file'])
                finfo = self.mpd_client.lsinfo(f['file'])[0]
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

    ## Load data into content tree
    ## by albumartist
    def load_albumartists(self):
        try:
            n = self.content_tree.get_top_layer().get_node(Constants.topnode_name_albumartists)
            if not n:
                log.debug("album artist top node is not defined")
                return
            recv = self.mpd_client.list("albumartist")
            if not recv:
                log.error("no data feteched for albumartist" )
                return
            for r in recv:
                if r:
                    n.get_child_layer().add_node(data.ContentTreeNode({ 'name': r, 'type': Constants.label_t_albumartist }))
        except Exception as e:
            log.error("could not load albumartists" % e)

    def load_albums_by_albumartist(self, albumartist:data.ContentTreeNode):
        try:
            recv = self.mpd_list("album", "albumartist", albumartist.get_name())
            #log.debug("albums by albumartist '%s': %s" % (albumartist.get_name(), recv))
            for r in recv:
                albumartist.get_child_layer().add_node(data.ContentTreeNode({ 'name': r, 'type': Constants.label_t_album }))
        except Exception as e:
            log.error("could not load albums by albumartist '%s': %s" % (albumartist.get_name(), e))

    def load_songs_by_album_by_albumartist(self, album:data.ContentTreeNode, albumartist:data.ContentTreeNode):
        try:
            recv = self.mpd_find("albumartist", albumartist.get_name(), "album", album.get_name())
            #log.debug("songs by album by albumartist '%s' '%s': %s" % (album.get_name(), albumartist.get_name(), recv))
            for r in recv:
                new_node = data.ContentTreeNode({ 'name': r, 'type': Constants.label_t_song })
                new_node.set_name(r['title'])
                album.get_child_layer().add_node(new_node)
        except Exception as e:
            log.error("could not load songs by albums by albumartist '%s', '%s': %s" % (albumartist.get_name(), album.get_name(), e))

    ## by artist
    def load_artists(self):
        try:
            n = self.content_tree.get_top_layer().get_node(Constants.topnode_name_artists)
            if not n:
                log.debug("artists top node is not defined")
                return
            recv = self.mpd_client.list("artist")
            if not recv:
                log.error("no data fetched for artist" )
                return
            for r in recv:
                if r:
                    n.get_child_layer().add_node(data.ContentTreeNode({ 'name': r, 'type': Constants.label_t_artist }))
        except Exception as e:
            log.error("could not load artists" % e)

    def load_albums_by_artist(self, artist:data.ContentTreeNode):
        try:
            recv = self.mpd_list("album", "artist", artist.get_name())
            #log.debug("albums by artist '%s': %s" % (artist.get_name(), recv))
            for r in recv:
                artist.get_child_layer().add_node(data.ContentTreeNode({ 'name': r, 'type': Constants.label_t_album }))
        except Exception as e:
            log.error("could not load albums by artist '%s': %s" % (artist.get_name(), e))

    def load_songs_by_album_by_artist(self, album:data.ContentTreeNode, artist:data.ContentTreeNode):
        try:
            recv = self.mpd_find("artist", artist.get_name(), "album", album.get_name())
            #log.debug("songs by album by artist '%s' '%s': %s" % (album.get_name(), artist.get_name(), recv))
            for r in recv:
                new_node = data.ContentTreeNode({ 'name': r, 'type': Constants.label_t_song })
                new_node.set_name(r['title'])
                album.get_child_layer().add_node(new_node)
        except Exception as e:
            log.error("could not load songs by album by artist '%s', '%s': %s" % (artist.get_name(), album.get_name(), e))

    # by albums
    def load_albums(self):
        try:
            n = self.content_tree.get_top_layer().get_node(Constants.topnode_name_albums)
            if not n:
                log.debug("albums top node is not defined")
                return
            recv = self.mpd_client.list("album")
            if not recv:
                log.error("no data feteched for album" )
                return
            for r in recv:
                if r:
                    n.get_child_layer().add_node(data.ContentTreeNode({ 'name': r, 'type': Constants.label_t_album }))
        except Exception as e:
            log.error("could not load albums" % e)

    def load_songs_by_album(self, album:data.ContentTreeNode):
        try:
            recv = self.mpd_find("album", album.get_name())
            #log.debug("songs by album '%s': %s" % (album.get_name(), recv))
            for r in recv:
                new_node = data.ContentTreeNode({ 'name': r, 'type': Constants.label_t_song })
                new_node.set_name(r['title'])
                album.get_child_layer().add_node(new_node)
        except Exception as e:
            log.error("could not load songs by album '%s': %s" % (album.get_name(), e))

    ## by genres
    def load_genres(self):
        try:
            n = self.content_tree.get_top_layer().get_node(Constants.topnode_name_genres)
            if not n:
                log.debug("genres top node is not defined")
                return
            recv = self.mpd_client.list("genre")
            if not recv:
                log.error("no data feteched for genre" )
                return
            for r in recv:
                if r:
                    n.get_child_layer().add_node(data.ContentTreeNode({ 'name': r, 'type': Constants.label_t_genre }))
        except Exception as e:
            log.error("could not load genres" % e)

    def load_albums_by_genre(self, genre:data.ContentTreeNode):
        try:
            recv = self.mpd_list("album", "genre", genre.get_name())
            #log.debug("albums by genre '%s': %s" % (genre.get_name(), recv))
            for r in recv:
                genre.get_child_layer().add_node(data.ContentTreeNode({ 'name': r, 'type': Constants.label_t_album }))
        except Exception as e:
            log.error("could not load albums by genre '%s': %s" % (genre.get_name(), e))

    def load_songs_by_album_by_genre(self, album:data.ContentTreeNode, genre:data.ContentTreeNode):
        try:
            recv = self.mpd_find("genre", genre.get_name(), "album", album.get_name())
            #log.debug("songs by album by genre '%s' '%s': %s" % (album.get_name(), genre.get_name(), recv))
            for r in recv:
                new_node = data.ContentTreeNode({ 'name': r, 'type': Constants.label_t_song })
                new_node.set_name(r['title'])
                album.get_child_layer().add_node(new_node)
        except Exception as e:
            log.error("could not load songs by album by genre '%s', '%s': %s" % (genre.get_name(), album.get_name(), e))

    # by files
    def load_files_list(self):
        try:
            n = self.content_tree.get_top_layer().get_node(Constants.topnode_name_files)
            if not n:
                log.debug("files top node is not defined")
                return
            files = self.get_files_list()
            #log.debug("files: %s" % files)
            if not files or not isinstance(files, list):
                log.error("could not get files successfully: %s" % files)
                return
            for f in files:
                #log.debug("adding file: %s" % f)
                subf = self.get_files_list(f['data']['dir'])
                for f2 in subf:
                    metadata = {'type': f2['type'], 'name': f['value'] + "/" + f2['value'], 'data': f2['data'] }
                    #log.debug("adding metadata: %s" % metadata)
                    n.get_child_layer().add_node(data.ContentTreeNode(metadata))
        except Exception as e:
            log.error("could not load files" % e)

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
