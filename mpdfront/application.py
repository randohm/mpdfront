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

def node_sort_normal(row1:data.ContentTreeNode, row2:data.ContentTreeNode):
    """
    Alphanumeric compare function for Gio.ListStore sorting.
    :param row1: left row
    :param row2: right now
    :return: value of comparison expression
    """
    return row1.metaname > row2.metaname

def node_sort_filtered(row1:data.ContentTreeNode, row2:data.ContentTreeNode):
    """
    Compare function for Gio.ListStore sorting. Modifies the text before comparison.
    Removes from text: /^The /
    :param row1: left row
    :param row2: right now
    :return: value of comparison expression
    """
    row1_value = re.sub(r'^The ', '', row1.metaname, flags=re.IGNORECASE)
    row2_value = re.sub(r'^The ', '', row2.metaname, flags=re.IGNORECASE)
    return row1_value > row2_value

def node_sort_by_track(row1:data.ContentTreeNode, row2:data.ContentTreeNode):
    """
    Compare function for Gio.ListStore sorting. Sort according to disc and track numbers
    :param row1: left row
    :param row2: right now
    :return: value of comparison expression
    """
    log = logging.getLogger(__name__ + "." + inspect.stack()[0].function)
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
        log.debug("sort compare failed: %s" % e)
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
            log.error("could not connect to mpd (%s): %s" % (type(e).__name__, e))
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
        try:
            self.window = MpdFrontWindow(application=self, config=self.config, content_tree=self.content_tree)
        except Exception as e:
            log.critical("could not create main window (%s): %s" % (type(e).__name__, e))
            self.quit()
        else:
            if self.css_file and os.path.isfile(self.css_file):
                log.debug("reading css file: %s" % self.css_file)
                self.css_provider = Gtk.CssProvider.new()
                try:
                    self.css_provider.load_from_path(self.css_file)
                    display = Gtk.Widget.get_display(self.window)
                    Gtk.StyleContext.add_provider_for_display(display, self.css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
                except Exception as e:
                    log.error("could not load CSS (%s): %s" % (type(e).__name__, e))
                    #raise e
            self.add_window(self.window)
            self.window.present()
            self.window.set_layout1()
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
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        files = self.mpd_client.lsinfo(path)
        log.debug("received files: %s" % files)
        rows = []
        for f in files:
            if 'directory' in f:
                dirname = os.path.basename(f['directory'])
                rows.append({'type': Constants.node_t_directory, 'name': dirname, 'path': f['directory']})
            elif 'file' in f:
                filename = os.path.basename(f['file'])
                finfo = self.mpd_client.lsinfo(f['file'])[0]
                if not finfo:
                    finfo = {'file': f['file']}
                finfo.update({'type': Constants.node_t_file, 'name': filename})
                rows.append(finfo)
            else:
                log.error("unhandled type: %s" % f)
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

    def load_content_data(self, node):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        log.debug("load data for node, metadata: %s" % node.get_metadata())
        if node.get_child_layer().get_n_items(): # if data has already been loaded, skip
            log.debug("node child data already loaded, type: %s, name: %s" % (node.metatype, node.metaname))
            return
        if node.metatype == Constants.node_t_category:
            self.load_category_content(node)
        elif node.metatype == Constants.node_t_albumartist:
            log.debug("loading albums by albumartist")
            self.load_items_list(node, Constants.node_t_song, False, "album", "albumartist", node.metaname)
        elif node.metatype == Constants.node_t_artist:
            log.debug("loading albums by artist")
            self.load_items_list(node, Constants.node_t_song, False, "album", "artist", node.metaname)
        elif node.metatype == Constants.node_t_genre:
            log.debug("loading albums by genre")
            self.load_items_list(node, Constants.node_t_song, False, "album", "genre", node.metaname)
        elif node.metatype == Constants.node_t_directory:
            self.load_directories(node)
        elif node.metatype == Constants.node_t_album:
            self.load_album_content(node)
        elif node.metatype == Constants.node_t_song:
            log.debug("nothing to do for a song: %s" % node.metaname)
        else:
            log.debug("unhandled metatype: %s" % node.metatype)

    def load_category_content(self, node:data.ContentTreeNode):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        if node.next_type == Constants.node_t_albumartist:
            log.debug("loading albumartists")
            self.load_items_list(node, Constants.node_t_album, False,"albumartist")
            node.get_child_layer().sort(node_sort_filtered)
        elif node.next_type == Constants.node_t_artist:
            log.debug("loading artists")
            self.load_items_list(node, Constants.node_t_album, False, "artist")
            node.get_child_layer().sort(node_sort_filtered)
        elif node.next_type == Constants.node_t_album:
            log.debug("loading albums")
            self.load_items_list(node, Constants.node_t_song, False, "album")
        elif node.next_type == Constants.node_t_genre:
            log.debug("loading genres")
            self.load_items_list(node, Constants.node_t_album, True, "genre")
        elif node.next_type in (Constants.node_t_file, Constants.node_t_directory):
            log.debug("loading directories")
            self.load_first_directory_level(node)
        else:
            log.error("unknown node next type: %s" % (node.next_type))

    def load_album_content(self, node:data.ContentTreeNode):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        log.debug("loading song by albums by: %s" % node.previous.metatype)
        if node.previous.metatype == Constants.node_t_albumartist:
            self.load_songs(node, "albumartist", node.previous.metaname, "album", node.metaname)
        elif node.previous.metatype == Constants.node_t_artist:
            self.load_songs(node, "artist", node.previous.metaname, "album", node.metaname)
        elif node.previous.metatype == Constants.node_t_category:
            self.load_songs(node, "album", node.metaname)
        elif node.previous.metatype == Constants.node_t_genre:
            self.load_songs(node, "genre", node.previous.metaname, "album", node.metaname)
        node.get_child_layer().sort(node_sort_by_track)

    def load_items_list(self, node:data.ContentTreeNode, next_type:str, load_empty_string:bool=False, *args, **kwargs):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        try:
            log.debug("loading item: %s" % node.get_metadata())
            recv = self.mpd_list(*args, **kwargs)
            if not recv:
                log.error("no data feteched for node: %s" % node.metaname)
                return
            log.debug("items: %s" % recv)
            for r in recv:
                if r or (load_empty_string and r == ""):
                    new_node = data.ContentTreeNode(metadata={'name': r, 'type': node.next_type, 'next_type': next_type}, previous=node)
                    node.get_child_layer().append(new_node)
        except Exception as e:
            log.error("could not load item (%s): %s" % (type(e).__name__, e))

    def load_songs(self, node:data.ContentTreeNode, *args, **kwargs):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        try:
            recv = self.mpd_find(*args, **kwargs)
            if not recv:
                log.error("no songs for: %s" % node.metaname)
                return
            log.debug("songs from '%s': %s" % (node.metaname, recv))
            for r in recv:
                if r:
                    node.get_child_layer().append(self.create_song_node(metadata=r, previous=node))
            node.get_child_layer().sort(node_sort_by_track)
        except Exception as e:
            log.error("could not load songs by albums by albumartist '%s', '%s': %s" % (node.previous.metaname, node.metaname, e))

    def load_first_directory_level(self, node:data.ContentTreeNode):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        log.debug("directory node metadata: %s" % node.get_metadata())
        try:
            path = ""
            if 'path' in node.get_metadata():
                path = node.get_metadata('path')
            files = self.get_files_list(path)
            log.debug("files: %s" % files)
            if not files or not isinstance(files, list):
                log.error("could not get files successfully: %s" % files)
                return
            for f1 in files:
                log.debug("1st level file: %s" % f1)
                subf = self.get_files_list(f1['path'])
                for f2 in subf:
                    log.debug("2nd level file: %s" % f2)
                    metadata = {'type': f2['type'], 'name': f1['name'] + "/" + f2['name'], 'path': f2['path']}
                    log.debug("adding metadata: %s" % metadata)
                    new_node = data.ContentTreeNode(metadata=metadata, previous=node)
                    node.get_child_layer().append(new_node)
        except Exception as e:
            log.error("could not load 1st level (%s): %s" % (type(e).__name__, e))

    def load_directories(self, node:data.ContentTreeNode):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        try:
            log.debug("dir metadata: %s" % node.get_metadata())
            files = self.get_files_list(node.get_metadata('path'))
            log.debug("received files: %s" % files)
            for f in files:
                node.get_child_layer().append(data.ContentTreeNode(metadata=f, previous=node))
        except Exception as e:
            log.error("could not load 2nd level (%s): %s" % (type(e).__name__, e))

    def create_song_node(self, metadata:dict, previous:data.ContentTreeNode):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        log.debug("create song node: %s" % metadata)
        metadata['type'] = Constants.node_t_song
        if 'title' in metadata and 'track' in metadata:
            metadata['name'] = "%s %s" % (metadata['track'], metadata['title'])
        else:
            metadata['name'] = os.path.basename(metadata['file'])
        new_node = data.ContentTreeNode(metadata=metadata, previous=previous)
        log.debug("new node: %s" % new_node.metaname)
        return new_node

    def check_threads(self):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        try:
            self.mpd_idle_thread.thread.join(0)
            log.debug("join() returned")
        except Exception as e:
            log.error("error running join (%s): %s" % (type(e).__name__, e))
        if not self.mpd_idle_thread.thread.is_alive():
            log.error("idle thread has stopped, restarting")
            try:
                self.mpd_idle_thread = mpd.IdleClientThread(host=self.host, port=self.port, queue=self.idle_queue,
                                                            name="idleThread")
            except Exception as e:
                log.error("could not restart idle thread (%s): %s" % (type(e).__name__, e))
        else:
            log.debug("idle thread is alive")
        return True

    def add_to_playlist(self, node:data.ContentTreeNode):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        log.debug("adding to playlist: %s" % node.get_metadata())
        if node.metatype == Constants.node_t_song:
            self.mpd_add(node.get_metadata('file'))
        elif node.metatype == Constants.node_t_file:
            self.mpd_add(node.get_metadata('file'))
        elif node.metatype == Constants.node_t_album:
            log.debug("adding album: %s" % node.metaname)
            if node.previous.metatype == Constants.node_t_artist:
                log.debug("adding album by artist: %s" % node.previous.metaname)
                self.mpd_findadd("artist", node.previous.metaname, "album", node.metaname)
            elif node.previous.metatype == Constants.node_t_albumartist:
                log.debug("adding album by albumartist: %s" % node.previous.metaname)
                self.mpd_findadd("albumartist", node.previous.metaname, "album", node.metaname)
            elif node.previous.metatype == Constants.node_t_genre:
                log.debug("adding album by genre: %s" % node.previous.metaname)
                self.mpd_findadd("genre", node.previous.metaname, "album", node.metaname)
            elif node.previous.metatype == Constants.node_t_category:
                log.debug("adding album from toplevel: %s" % node.previous.metaname)
                self.mpd_findadd("album", node.metaname)
            else:
                log.error("unhandled type 2: %s" % node.previous.metatype)
        elif node.metatype == Constants.node_t_directory:
            log.debug("not adding dir: %s" % node.get_metadata())
        else:
            log.error("unhandled type 1: %s" % node.metatype)
