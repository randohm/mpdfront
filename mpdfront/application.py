import os, re, inspect
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

def node_sort_filtered(row1, row2):
    """
    Compare function for Gio.ListStore sorting. Modifies the text before comparison.
    Removes from text: /^The /
    :param row1: left row
    :param row2: right now
    :return: value of comparison expression
    """
    row1_value = re.sub(r'^The ', '', row1.get_metaname(), flags=re.IGNORECASE)
    row2_value = re.sub(r'^The ', '', row2.get_metaname(), flags=re.IGNORECASE)
    return row1_value > row2_value

def node_sort_by_track(row1, row2):
    """
    Compare function for Gio.ListStore sorting. Sort according to disc and track numbers
    :param row1: left row
    :param row2: right now
    :return: value of comparison expression
    """
    try:
        log.debug("comparing input: %s,%s > %s,%s" % (row1.get_metadata('disc'), row1.get_metadata('track'), row2.get_metadata('disc'), row2.get_metadata('track')))
        if row1.get_metadata('disc') and row2.get_metadata('disc'):
            row1_disc = int(row1.get_metadata('disc'))
            row2_disc = int(row2.get_metadata('disc'))
            if row1_disc != row2_disc:
                return row1_disc > row2_disc
        if not row1.get_metadata('track') or not row2.get_metadata('track'):
            #log.debug("skipping comparison")
            return 0
        row1_value = int(row1.get_metadata('track'))
        row2_value = int(row2.get_metadata('track'))
        #log.debug("comparing values: %d > %d" % (row1_value, row2_value))
        return row1_value > row2_value
    except Exception as e:
        log.debug("sort compare failed: %s" % (e))
        return 0

class MpdFrontApp(Gtk.Application):
    """
    Main application class for mpdfront.
    """
    def __init__(self, config:configparser, css_file:str=None, host:str=None, port:int=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = config
        self.idle_queue = queue.Queue()
        if config.has_option(Constants.config_section_main, "sound_card"):
            self.card_id = int(config.get(Constants.config_section_main, "sound_card"))
        if config.has_option(Constants.config_section_main, "sound_device"):
            self.device_id = int(config.get(Constants.config_section_main, "sound_device"))
        if css_file:
            self.css_file = css_file
        elif config.has_option(Constants.config_section_main, "style"):
            self.css_file = config.get(Constants.config_section_main, "style")
        else:
            self.css_file = None
        if host:
            self.host = host
        elif config.has_option(Constants.config_section_main, "host"):
            self.host = config.get(Constants.config_section_main, "host")
        else:
            self.host = Constants.default_host
        if port:
            self.port = port
        elif config.has_option(Constants.config_section_main, "port"):
            self.port = int(config.get(Constants.config_section_main, "port"))
        else:
            self.port = Constants.default_port
        if config.has_option(Constants.config_section_main, "music_dir"):
            self.music_dir = config.get(Constants.config_section_main, "music_dir")

        ## Connect to MPD
        try:
            self.mpd_client = mpd.Client(self.host, self.port)
            self.mpd_idle_thread = mpd.IdleClientThread(host=self.host, port=self.port, queue=self.idle_queue, name="idleThread")
        except Exception as e:
            log.error("could not connect to mpd: %s" % e)
            raise e

        ## Define callbacks to handle mpd commands
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

        ## create and initialize content tree
        self.content_tree = Gio.ListStore()
        for r in Constants.browser_1st_column_rows:
            new_node = data.ContentTreeNode(metadata=r)
            self.content_tree.append(new_node)
            self.load_content_data(new_node)

        ## Set timers
        self.idle_thread_timeout_id = GLib.timeout_add(Constants.idle_thread_interval, self.idle_thread_comms_handler)
        self.refresh_thread_timeout_id = GLib.timeout_add(Constants.playback_refresh_interval, self.refresh_playback)
        self.alive_thread_timeout_id = GLib.timeout_add(Constants.alive_check_interval, self.check_threads)

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

    def refresh_playback(self):
        """
        Updates playback, time, info and progress bar.
        """
        mpd_status = self.mpd_client.status()
        currentsong = self.mpd_client.currentsong()
        self.window.playback_display.update(mpd_status, currentsong, self.music_dir)
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
        #log.debug("received files: %s" % files)
        rows = []
        for f in files:
            if 'directory' in f:
                dirname = os.path.basename(f['directory'])
                rows.append(
                    {'type': 'directory', 'name': dirname, 'data': {'name': dirname, 'dir': f['directory']}})
            elif 'file' in f:
                filename = os.path.basename(f['file'])
                finfo = self.mpd_client.lsinfo(f['file'])[0]
                if not finfo:
                    finfo = {'file': f['file']}
                rows.append({'type': 'file', 'name': filename, 'data': finfo})
        return rows

    def idle_thread_comms_handler(self):
        msg = None
        try:
            if not self.idle_queue.empty():
                msg = self.idle_queue.get_nowait()
        except Exception as e:
            return True

        if msg and isinstance(msg, QueueMessage):
            log.debug("processing queued message type: %s, item: %s" % (msg.get_type(), msg.get_item()))
            log.debug("data: %s" % msg.get_data())
            if msg.get_type() == Constants.message_type_change:
                if msg.get_item() == Constants.message_item_playlist:
                    self.window.playlist_list.update(msg.get_data()['playlist'], msg.get_data()['current'])
                if msg.get_item() == Constants.message_item_player:
                    self.window.playback_display.update(msg.get_data()['status'], msg.get_data()['current'], self.music_dir)
        return True

    ## BEGIN content tree data loaders
    def load_content_data(self, node):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        log.debug("load data for node, metadata: %s" % node.get_metadata())
        if node.get_child_layer().get_n_items(): # if data has already been loaded, skip
            log.debug("node child data already loaded, type: %s, name: %s" % (node.get_metatype(), node.get_metaname()))
            return
        if node.get_metatype() == Constants.node_t_category:
            if node.get_metadata('next_type') == Constants.node_t_albumartist:
                log.debug("loading albumartists")
                self.load_albumartists(node)
            elif node.get_metadata('next_type') == Constants.node_t_artist:
                log.debug("loading artists")
                self.load_artists(node)
            elif node.get_metadata('next_type') == Constants.node_t_album:
                log.debug("loading albums")
                self.load_albums(node)
            elif node.get_metadata('next_type') == Constants.node_t_genre:
                log.debug("loading genres")
                self.load_genres(node)
            elif node.get_metadata('next_type') in (Constants.node_t_file, Constants.node_t_dir):
                log.debug("loading directories")
                self.load_first_directory_level(node)
            else:
                log.error("unknown node next type: %s" % (node.get_metadata('next_type')))
        elif node.get_metatype() == Constants.node_t_albumartist:
            log.debug("loading albums by albumartist")
            self.load_albums_by_albumartist(node)
        elif node.get_metatype() == Constants.node_t_artist:
            log.debug("loading albums by artist")
            self.load_albums_by_artist(node)
        elif node.get_metatype() == Constants.node_t_genre:
            log.debug("loading albums by genre")
            self.load_albums_by_genre(node)
        elif node.get_metatype() == Constants.node_t_dir:
            #if node.get_metadata('previous_type') == Constants.node_t_category:
            #    log.debug("loading 2nd level files")
            self.load_directories(node)
            #elif node.get_metadata('previous_type') == Constants.node_t_dir:
            #    self.load_third_file_level(node)
            #else:
            #    log.debug("previous type: %s" % node.get_metadata('previous_type'))
        elif node.get_metatype() == Constants.node_t_album:
            log.debug("loading song by albums by: %s" % node.get_metadata('previous_type'))
            if node.get_metadata('previous_type') == Constants.node_t_albumartist:
                self.load_songs_by_album_by_albumartist(node, node.get_metadata('previous'))
            elif node.get_metadata('previous_type') == Constants.node_t_artist:
                self.load_songs_by_album_by_artist(node, node.get_metadata('previous'))
            elif node.get_metadata('previous_type') == Constants.node_t_category:
                self.load_songs_by_album(node)
            elif node.get_metadata('previous_type') == Constants.node_t_genre:
                self.load_songs_by_album_by_genre(node, node.get_metadata('previous'))
        elif node.get_metatype() == Constants.node_t_song:
            log.debug("nothing to do for a song: %s" % node.get_metaname())
        else:
            log.debug("unhandled metatype: %s" % node.get_metatype())

    ## by albumartist
    def load_albumartists(self, node:data.ContentTreeNode):
        try:
            recv = self.mpd_client.list("albumartist")
            if not recv:
                log.error("no data feteched for albumartist" )
                return
            for r in recv:
                if r:
                    new_node = data.ContentTreeNode(metadata={'name': r, 'type': Constants.node_t_albumartist,
                                                'previous': node, 'previous_type': node.get_metatype(),
                                                'next_type': Constants.node_t_album})
                    node.get_child_layer().append(new_node)
            node.get_child_layer().sort(node_sort_filtered)
        except Exception as e:
            log.error("could not load albumartists: %s" % e)

    def load_albums_by_albumartist(self, albumartist:data.ContentTreeNode):
        try:
            recv = self.mpd_list("album", "albumartist", albumartist.get_metaname())
            log.debug("albums by albumartist '%s': %s" % (albumartist.get_metaname(), recv))
            for r in recv:
                if r:
                    new_node = data.ContentTreeNode(metadata={'name': r,'type': Constants.node_t_album,
                                                'previous': albumartist, 'previous_type': albumartist.get_metatype(),
                                                'next_type': Constants.node_t_song})
                    albumartist.get_child_layer().append(new_node)
        except Exception as e:
            log.error("could not load albums by albumartist '%s': %s" % (albumartist.get_metaname(), e))

    def load_songs_by_album_by_albumartist(self, album:data.ContentTreeNode, albumartist:data.ContentTreeNode):
        try:
            recv = self.mpd_find("albumartist", albumartist.get_metaname(), "album", album.get_metaname())
            for r in recv:
                if r:
                    album.get_child_layer().append(self.create_song_node(r))
            album.get_child_layer().sort(node_sort_by_track)
        except Exception as e:
            log.error("could not load songs by albums by albumartist '%s', '%s': %s" %
                      (albumartist.get_metaname(), album.get_metaname(), e))

    ## by artist
    def load_artists(self, node:data.ContentTreeNode):
        try:
            recv = self.mpd_client.list("artist")
            if not recv:
                log.error("no data fetched for artist" )
                return
            for r in recv:
                if r:
                    new_node = data.ContentTreeNode(metadata={'name': r, 'type': Constants.node_t_artist,
                                                'previous': node, 'previous_type': Constants.node_t_category,
                                                'next_type': Constants.node_t_album})
                    node.get_child_layer().append(new_node)
            node.get_child_layer().sort(node_sort_filtered)
        except Exception as e:
            log.error("could not load artists: %s" % e)

    def load_albums_by_artist(self, artist:data.ContentTreeNode):
        try:
            recv = self.mpd_list("album", "artist", artist.get_metaname())
            #log.debug("albums by artist '%s': %s" % (artist.get_metaname(), recv))
            for r in recv:
                if r:
                    new_node = data.ContentTreeNode(metadata={'name': r, 'type': Constants.node_t_album,
                                                'previous': artist, 'previous_type': Constants.node_t_artist,
                                                'next_type': Constants.node_t_song})
                    artist.get_child_layer().append(new_node)
        except Exception as e:
            log.error("could not load albums by artist '%s': %s" % (artist.get_metaname(), e))

    def load_songs_by_album_by_artist(self, album:data.ContentTreeNode, artist:data.ContentTreeNode):
        try:
            recv = self.mpd_find("artist", artist.get_metaname(), "album", album.get_metaname())
            #log.debug("songs by album by artist '%s' '%s': %s" % (album.get_metaname(), artist.get_metaname(), recv))
            for r in recv:
                if r:
                    album.get_child_layer().append(self.create_song_node(r))
        except Exception as e:
            log.error("could not load songs by album by artist '%s', '%s': %s" %
                      (artist.get_metaname(), album.get_metaname(), e))

    # by albums
    def load_albums(self, node:data.ContentTreeNode):
        try:
            recv = self.mpd_client.list("album")
            if not recv:
                log.error("no data feteched for album" )
                return
            for r in recv:
                if r:
                    new_node = data.ContentTreeNode(metadata={'name': r, 'type': Constants.node_t_album,
                                                'previous': node, 'previous_type': Constants.node_t_category,
                                                'next_type': Constants.node_t_song})
                    node.get_child_layer().append(new_node)
        except Exception as e:
            log.error("could not load albums: %s" % e)

    def load_songs_by_album(self, album:data.ContentTreeNode):
        try:
            recv = self.mpd_find("album", album.get_metaname())
            #log.debug("songs by album '%s': %s" % (album.get_metaname(), recv))
            for r in recv:
                album.get_child_layer().append(self.create_song_node(r))
        except Exception as e:
            log.error("could not load songs by album '%s': %s" % (album.get_metaname(), e))

    ## by genres
    def load_genres(self, node:data.ContentTreeNode):
        try:
            recv = self.mpd_client.list("genre")
            if not recv:
                log.error("no data feteched for genre" )
                return
            for r in recv:
                if r != None:
                    new_node= data.ContentTreeNode(metadata={'name': r, 'type': Constants.node_t_genre,
                                                'previous': node, 'next_type': Constants.node_t_album})
                    node.get_child_layer().append(new_node)
        except Exception as e:
            log.error("could not load genres: %s" % e)

    def load_albums_by_genre(self, genre:data.ContentTreeNode):
        try:
            recv = self.mpd_list("album", "genre", genre.get_metaname())
            #log.debug("albums by genre '%s': %s" % (genre.get_metaname(), recv))
            for r in recv:
                if r:
                    genre.get_child_layer().append(data.ContentTreeNode(metadata={'name': r,
                                                'type': Constants.node_t_album, 'previous': genre,
                                                'previous_type': Constants.node_t_genre, 'next_type': Constants.node_t_song}))
        except Exception as e:
            log.error("could not load albums by genre '%s': %s" % (genre.get_metaname(), e))

    def load_songs_by_album_by_genre(self, album:data.ContentTreeNode, genre:data.ContentTreeNode):
        try:
            recv = self.mpd_find("genre", genre.get_metaname(), "album", album.get_metaname())
            #log.debug("songs by album by genre '%s' '%s': %s" % (album.get_metaname(), genre.get_metaname(), recv))
            for r in recv:
                if r:
                    album.get_child_layer().append(self.create_song_node(r))
        except Exception as e:
            log.error("could not load songs by album by genre '%s', '%s': %s" %
                      (genre.get_metaname(), album.get_metaname(), e))

    # by files
    def load_first_directory_level(self, node:data.ContentTreeNode):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        log.info("logger: %s" % log)
        log.debug("directory node metadata: %s" % node.get_metadata())
        try:
            path = ""
            if node.get_metadata('data') and 'dir' in node.get_metadata('data'):
                path = node.get_metadata('data')['dir']
            files = self.get_files_list(path)
            log.debug("files: %s" % files)
            if not files or not isinstance(files, list):
                log.error("could not get files successfully: %s" % files)
                return
            for f in files:
                #log.debug("adding file: %s" % f)
                subf = self.get_files_list(f['data']['dir'])
                for f2 in subf:
                    metadata = {'type': f2['type'], 'name': f['name'] + "/" + f2['name'], 'data': f2['data'],
                                'previous_type': Constants.node_t_category}
                    #log.debug("adding metadata: %s" % metadata)
                    new_node = data.ContentTreeNode(metadata=metadata)
                    node.get_child_layer().append(new_node)
        except Exception as e:
            log.error("could not load 1st level: %s" % e)

    def load_directories(self, dir:data.ContentTreeNode):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        try:
            log.debug("dir metadata: %s" % dir.get_metadata())
            files = self.get_files_list(dir.get_metadata('data')['dir'])
            log.debug("received files: %s" % files)
            for f in files:
                f['previous'] = dir
                f['previous_type'] = Constants.node_t_dir
                dir.get_child_layer().append(data.ContentTreeNode(metadata=f))
        except Exception as e:
            log.error("could not load 2nd level: %s" % e)

    ## END content tree data loaders

    def create_song_node(self, song:dict):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        log.debug("create song node: %s" % song)
        song['type'] = Constants.node_t_song
        if 'title' in song and 'track' in song:
            song['name'] = "%s %s" % (song['track'], song['title'])
        else:
            song['name'] = os.path.basename(song['file'])
        new_node = data.ContentTreeNode(metadata=song)
        log.debug("new node: %s" % new_node.get_metaname())
        return new_node

    def check_threads(self):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        if not self.mpd_idle_thread.thread.is_alive():
            log.error("idle thread has stopped, restarting")
            try:
                self.mpd_idle_thread = mpd.IdleClientThread(host=self.host, port=self.port, queue=self.idle_queue,
                                                            name="idleThread")
            except Exception as e:
                log.error("could not restart idle thread: %s" % e)
        else:
            log.debug("idle thread is alive")
        return True