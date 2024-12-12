import time, inspect
import threading, queue
import logging
import musicpd
from . import Constants
from .message import QueueMessage

log = logging.getLogger(__name__)

class Client:
    def __init__(self, host:str, port:int):
        self.host = host
        self.port = port
        try:
            self.mpd_client = musicpd.MPDClient()
            self.mpd_client.connect(host, port)
            log.info("connected to mpd %s:%d" % (host, port))
        except Exception as e:
            log.critical("could not connect to mpd %s:%d: %s" % (host, port, e))
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
            'play_or_pause': self.play_or_pause,
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
            'toggle': self.play_or_pause,
        }

    def __getattr__(self, attr):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        log.debug("called __getattr__: %s" % attr)
        if attr not in self._mpd_callbacks:
            raise AttributeError("object has no attribute %s" % attr)
        return lambda *args: self.run_command(self._mpd_callbacks[attr], *args)

    def reconnect(self):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        try:
            log.debug("attempting disconnect")
            self.mpd_client.disconnect()
        except Exception as e:
            log.debug("disconnect failed: %s" % e)
        try:
            log.debug("attempting reconnect")
            self.mpd_client.connect()
            log.info("reconnected to mpd")
        except Exception as e:
            log.critical("could not reconnect to mpd %s:%d: %s" % (self.host, self.port, e))
            raise e

    def run_command(self, callback, *args, **kwargs):
        """
        Calls callback(), assuming it is an MPD command. If it fails on connection-related errors, attempt to reconnect
        to MPD. Keeps trying until the connection and command stop throwing connection-related exceptions or abort on
        unknown exceptions.
        :param callback: function to call
        :param args: args for callback
        :param kwargs: args for callback
        :return:
        """
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        try_reconnect = False
        retries = 0
        while True:
            if retries > 0:
                log.debug("retry #%d try_reconnect: %s" % (retries, try_reconnect))
            if try_reconnect:
                try:
                    self.reconnect()
                    try_reconnect = False
                except Exception as e:
                    log.error("reconnect failed: %s" % e)
                    time.sleep(Constants.reconnect_retry_sleep_secs)
                    try_reconnect = True
                    retries += 1
                    continue
            try:
                #log.debug("callback: %s" % callback.__name__)
                ret = callback(*args, **kwargs)
                #log.debug("callback returned type: %s" % type(ret))
                return ret
            except (musicpd.ConnectionError, BrokenPipeError, ConnectionResetError, ConnectionError,
                    ConnectionAbortedError, ConnectionRefusedError) as e:
                log.error("command failed, type: %s message: %s" % (type(e).__name__, e))
                try_reconnect = True
                time.sleep(Constants.reconnect_retry_sleep_secs)
                retries += 1
                continue
            except musicpd.PendingCommandError as e:
                log.error("PendingCommandError: %s" % e)
                return []
            except Exception as e:
                log.error("unhandled exception, type: %s message: %s" % (type(e).__name__, e))
                return None
            #else:
            #    log.debug("else pass")
            #finally:
            #    retries += 1

    def play_or_pause(self):
        """
        Check the player status, play if stopped, pause otherwise.
        """
        if self.status()['state'] == "stop":
            return self.play()
        else:
            return self.pause()

class ClientThread:
    def __init__(self, host:str, port:int, queue:queue.Queue=None, name:str=""):
        self.host = host
        self.port = port
        self.queue = queue
        self.name = name
        self.spawn()

    def spawn(self):
        try:
            self.thread = threading.Thread(target=self.run, args=(), name=self.name, daemon=True)
            self.thread.start()
        except Exception as e:
            log.critical("Could not spawn thread '%s': %s" % (self.name, e))
            raise e
        return self.thread

    def run(self):
        try:
            self.mpd = Client(self.host, self.port)
        except Exception as e:
            log.error("client thread '%s' could not connect to host %s at port %d: %s" % (self.name, self.host, self.port, e))
            raise e
        log.debug("client thread '%s' connected to mpd %s:%d" % ((self.name, self.host, self.port)))

        self.pre_run()
        while True:
            self.one_run()

    def pre_run(self):
        pass

    def one_run(self):
        pass

class IdleClientThread(ClientThread):
    """
    Connects to mpd and runs idle commands waiting for notification of state changes.
    """
    def one_run(self):
        """
        Function that runs in the idle thread created by spawn_idle_thread().
        Listens for changes from MPD, using the idle command.
        Updates UI to idle()
        """
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        try:
            log.debug("sending idle")
            self.mpd.send_idle()
            log.debug("idle sent")
            changes = self.mpd.fetch_idle()
            log.debug("fetched idle")
        except Exception as e:
            log.error("idle failed: %s" % e)
            return

        else:
            log.debug("changes: %s" % changes)
            playlist_refreshed = False
            if not changes or not isinstance(changes, list):
                log.debug("changes not expected value/type")
                return
            for c in changes:
                if c == "playlist" and not playlist_refreshed:
                    log.debug("playlist changes")
                    playlistinfo = self.mpd.playlistinfo()
                    currentsong = self.mpd.currentsong()
                    self.queue.put(QueueMessage(type=Constants.message_type_change, item="playlist",
                                                data={"playlist": playlistinfo, "current": currentsong }))
                    playlist_refreshed = True
                elif c == "player":
                    log.debug("player changes")
                    status = self.mpd.status()
                    currentsong = self.mpd.currentsong()
                    self.queue.put(QueueMessage(type=Constants.message_type_change, item="player",
                                                data={"status": status, "current": currentsong }))
                    if not playlist_refreshed:
                        playlistinfo = self.mpd.playlistinfo()
                        self.queue.put(QueueMessage(type=Constants.message_type_change, item="playlist",
                                                    data={"playlist": playlistinfo, "current": currentsong }))
                        playlist_refreshed = True
                elif c == "database":
                    log.debug("database changes")
                    self.queue.put(QueueMessage(type=Constants.message_type_change, item="database"))
                elif c == "outputs":
                    log.debug("outputs changes")
                    self.queue.put(QueueMessage(type=Constants.message_type_change, item="outputs"))
                elif c == "mixer":
                    log.debug("mixer changes")
                    self.queue.put(QueueMessage(type=Constants.message_type_change, item="mixer"))
                else:
                    log.info("Unhandled change: %s" % c)
