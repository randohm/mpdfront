import queue
import time
import threading
import logging
import musicpd

from . import Constants
from .message import QueueMessage

log = logging.getLogger(__name__)

class Client:
    def __init__(self, host:str, port:int):
        if not host or not port:
            err_msg = "host or port not defined"
            log.error(err_msg)
            raise ValueError(err_msg)
        self.host = host
        self.port = port
        try:
            self.mpd = musicpd.MPDClient()
            self.mpd.connect(host, port)
            log.info("connected to mpd %s:%d" % (host, port))
        except Exception as e:
            log.critical("could not connect to mpd %s:%d: %s" % (host, port, e))
            raise e

    def reconnect(self):
        try:
            log.debug("attempting disconnect")
            self.mpd.disconnect()
        except Exception as e:
            log.debug("diconnect failed: %s" % e)
        try:
            log.debug("attempting reconnect")
            self.mpd.connect()
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
                return callback(*args, **kwargs)
            except (musicpd.ConnectionError, BrokenPipeError, ConnectionResetError, ConnectionError,
                    ConnectionAbortedError, ConnectionRefusedError) as e:
                log.error("command failed, type: %s message: %s" % (type(e).__name__, e))
                try_reconnect = True
                time.sleep(Constants.reconnect_retry_sleep_secs)
                continue
            except musicpd.PendingCommandError as e:
                log.error("PendingCommandError: %s" % e)
                return []
            except Exception as e:
                log.error("unhandled exception, type: %s message: %s" % (type(e).__name__, e))
                return None
            else:
                log.debug("else pass")
            finally:
                retries += 1

    def list(self, *args, **kwargs):
        return self.run_command(self.mpd.list, *args, **kwargs)

    def find(self, *args, **kwargs):
        return self.run_command(self.mpd.find, *args, **kwargs)

    def status(self, *args, **kwargs):
        return self.run_command(self.mpd.status, *args, **kwargs)

    def stats(self, *args, **kwargs):
        return self.run_command(self.mpd.stats, *args, **kwargs)

    def outputs(self, *args, **kwargs):
        return self.run_command(self.mpd.outputs, *args, **kwargs)

    def lsinfo(self, *args, **kwargs):
        return self.run_command(self.mpd.lsinfo, *args, **kwargs)

    def play(self, *args, **kwargs):
        return self.run_command(self.mpd.play, *args, **kwargs)

    def pause(self, *args, **kwargs):
        return self.run_command(self.mpd.pause, *args, **kwargs)

    def stop(self, *args, **kwargs):
        return self.run_command(self.mpd.stop, *args, **kwargs)

    def currentsong(self, *args, **kwargs):
        return self.run_command(self.mpd.currentsong, *args, **kwargs)

    def playlistinfo(self, *args, **kwargs):
        return self.run_command(self.mpd.playlistinfo, *args, **kwargs)

    def previous(self, *args, **kwargs):
        return self.run_command(self.mpd.previous, *args, **kwargs)

    def next(self, *args, **kwargs):
        return self.run_command(self.mpd.next, *args, **kwargs)

    def seekcur(self, *args, **kwargs):
        return self.run_command(self.mpd.seekcur, *args, **kwargs)

    def enableoutput(self, *args, **kwargs):
        return self.run_command(self.mpd.enableoutput, *args, **kwargs)

    def disableoutput(self, *args, **kwargs):
        return self.run_command(self.mpd.disableoutput, *args, **kwargs)

    def consume(self, *args, **kwargs):
        return self.run_command(self.mpd.consume, *args, **kwargs)

    def random(self, *args, **kwargs):
        return self.run_command(self.mpd.random, *args, **kwargs)

    def repeat(self, *args, **kwargs):
        return self.run_command(self.mpd.repeat, *args, **kwargs)

    def single(self, *args, **kwargs):
        return self.run_command(self.mpd.single, *args, **kwargs)

    def moveid(self, *args, **kwargs):
        return self.run_command(self.mpd.moveid, *args, **kwargs)

    def deleteid(self, *args, **kwargs):
        return self.run_command(self.mpd.deleteid, *args, **kwargs)

    def clear(self, *args, **kwargs):
        return self.run_command(self.mpd.clear, *args, **kwargs)

    def add(self, *args, **kwargs):
        return self.run_command(self.mpd.add, *args, **kwargs)

    def findadd(self, *args, **kwargs):
        return self.run_command(self.mpd.findadd, *args, **kwargs)

    def playid(self, *args, **kwargs):
        return self.run_command(self.mpd.playid, *args, **kwargs)

    def send_idle(self, *args, **kwargs):
        return self.run_command(self.mpd.send_idle, *args, **kwargs)

    def fetch_idle(self, *args, **kwargs):
        return self.run_command(self.mpd.fetch_idle, *args, **kwargs)

    def play_or_pause(self):
        """
        Check the player status, play if stopped, pause otherwise.
        """
        if self.status()['state'] == "stop":
            return self.play()
        else:
            return self.pause()

class ClientThread:
    def __init__(self, host:str, port:int, queue:queue.Queue, name:str):
        if not host or not port or not queue:
            err_msg = "host, port, app, or queue not defined"
            log.error(err_msg)
            raise ValueError(err_msg)
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

class CommandClientThread(ClientThread):
    """
    Connects to mpd, waits on messages from the UI, and runs commands based on the messages.
    """
    def __init__(self, data_queue:queue.Queue, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_queue = data_queue

    def pre_run(self):
        self.cmd_callbacks = {
            'toggle': self.mpd.play_or_pause,
            'add': self.mpd.add,
            'clear': self.mpd.clear,
            'consume': self.mpd.consume,
            'currentsong': self.mpd_currentsong,
            'deleteid': self.mpd.deleteid,
            'disableoutput': self.mpd.disableoutput,
            'enableoutput': self.mpd.enableoutput,
            'fetch_idle': self.mpd.fetch_idle,
            'find': self.mpd.find,
            'findadd': self.mpd.findadd,
            'list': self.mpd.list,
            'lsinfo': self.mpd.lsinfo,
            'moveid': self.mpd.moveid,
            'next': self.mpd.next,
            'outputs': self.mpd_outputs,
            'pause': self.mpd.pause,
            'play': self.mpd.play,
            'play_or_pause': self.mpd.play_or_pause,
            'playid': self.mpd.playid,
            'playlistinfo': self.mpd_playlistinfo,
            'previous': self.mpd.previous,
            'random': self.mpd.random,
            'repeat': self.mpd.repeat,
            'seekcur': self.mpd.seekcur,
            'send_idle': self.mpd.send_idle,
            'single': self.mpd.single,
            'stats': self.mpd_stats,
            'status': self.mpd_status,
            'stop': self.mpd.stop,
        }

    def one_run(self):
        try:
            log.debug("waiting for message")
            msg = self.queue.get()
            log.debug("message received, type: %s, item: %s, data: %s" % (msg.get_type(), msg.get_item(), msg.get_data()))
        except Exception as e:
            log.error("error receiving message from queue: %e" % e)
            return

        if msg.get_type() == Constants.message_type_command:
            log.debug("running command: %s" % msg.get_item())
            try:
                if msg.get_data():
                    self.cmd_callbacks[msg.get_item()](*msg.get_data())
                else:
                    self.cmd_callbacks[msg.get_item()]()
            except Exception as e:
                log.error("error running command '%s': %s" % (msg.get_item(), e))
                return
        else:
            log.debug("unhandled type: %s" % msg.get_type())

    def get_command_response(self, callback, item):
        r = callback()
        log.debug("got response: %s" % r)
        self.data_queue.put(QueueMessage(type=Constants.message_type_data, item=item, data=r))

    def mpd_status(self):
        self.get_command_response(self.mpd.status, item="status")

    def mpd_currentsong(self):
        self.get_command_response(self.mpd.currentsong, item="currentsong")

    def mpd_playlistinfo(self):
        self.get_command_response(self.mpd.playlistinfo, item="playlistinfo")

    def mpd_stats(self):
        self.get_command_response(self.mpd.stats, item="stats")

    def mpd_outputs(self):
        self.get_command_response(self.mpd.outputs, item="outputs")
