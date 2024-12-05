import sys, time
import threading
import logging
import musicpd
from .constants import Constants

log = logging.getLogger(__name__)

_RETRY_WAIT=1000

class Client:
    def __init__(self, host:str=None, port:int=None):
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
            self.mpd.connect()
            log.info("reconnected to mpd")
        except Exception as e:
            log.critical("could not reconnect to mpd %s:%d: %s" % (self.host, self.port, e))
            raise e

    def run_command(self, callback, *args, **kwargs):
        try_reconnect = False
        while True:
            if try_reconnect:
                try:
                    self.reconnect()
                    try_reconnect = False
                except Exception as e:
                    log.error("reconnect failed: %s" % e)
                    time.sleep(_RETRY_WAIT)
                    continue
            try:
                return callback(*args, **kwargs)
            except (musicpd.ConnectionError, BrokenPipeError) as e:
                log.error("command failed: %s" % e)
                try_reconnect = True
                time.sleep(_RETRY_WAIT)
            except Exception as e:
                raise e

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

    def play_or_pause(self):
        """
        Check the player status, play if stopped, pause otherwise.
        """
        if self.status()['state'] == "stop":
            return self.play()
        else:
            return self.pause()

class UpdaterClient:
    def __init__(self, host:str=None, port:int=None):
        if not host or not port:
            err_msg = "host or port not defined"
            log.error(err_msg)
            raise ValueError(err_msg)
        try:
            self.mpd = musicpd.MPDClient()
            self.mpd.connect(host, port)
            log.debug("connected to mpd %s:%d" % (host, port))
        except Exception as e:
            log.critical("could not connect to mpd %s:%d: %s" % (host, port, e))
            raise e

class IdleClientThread:
    """
    Connects to mpd and runs idle commands waiting for notification of state changes.
    """
    def __init__(self, host:str=None, port:int=None, queue=None):
        if not host or not port or not queue:
            err_msg = "host, port, app, or queue not defined"
            log.error(err_msg)
            raise ValueError(err_msg)
        self.host = host
        self.port = port
        self.queue = queue
        self.run_idle = True
        self.run()

    def idle_thread(self):
        """
        Function that runs in the idle thread created by spawn_idle_thread().
        Listens for changes from MPD, using the idle command.
        Updates UI to idle()
        """
        try:
            self.mpd = Client(self.host, self.port)
        except Exception as e:
            log.error("could not connect to host %s at port %d: %s" % (self.host, self.port, e))
            raise e
        log.debug("idle thread connected to mpd %s:%d" % (self.host, self.port))

        while self.run_idle:
            error = False
            reconnect = False
            try:
                self.mpd.mpd.send_idle()
                changes = self.mpd.mpd.fetch_idle()
            except (musicpd.ConnectionError, BrokenPipeError) as e:
                log.error("idle connection failed: %s" % e)
                reconnect = True
                error = True
            except Exception as e:
                log.error("idle failed: %s" % e)
                error = True
            if reconnect:
                try:
                    self.reconnect()
                except (musicpd.ConnectionError, BrokenPipeError) as e:
                    log.error("idle failed reconnect: %s" % e)
                    time.sleep(RETRY_WAIT)
                    error = True
            if error:
                log.error("idle thread connection error(s)")
                continue
            else:
                log.debug("changes: %s" % changes)
                for c in changes:
                    if c == "playlist":
                        log.debug("playlist changes")
                        playlistinfo = self.mpd.playlistinfo()
                        currentsong = self.mpd.currentsong()
                        self.queue.put({ "type": "change", "item": "playlist", "playlist": playlistinfo, "current": currentsong })
                    elif c == "player":
                        log.debug("player changes")
                        status = self.mpd.status()
                        currentsong = self.mpd.currentsong()
                        self.queue.put({ "type": "change", "item": "player", "status": status, "current": currentsong })
                    elif c == "database":
                        log.debug("database changes")
                        self.queue.put("change:database")
                    elif c == "outputs":
                        log.debug("outputs changes")
                        self.queue.put("change:outputs")
                    elif c == "mixer":
                        log.debug("mixer changes")
                        self.queue.put("change:mixer")
                    else:
                        log.info("Unhandled change: %s" % c)

    def run(self):
        """
        Creates and starts the idle thread that listens for change events from MPD.
        """
        try:
            idle_thread = threading.Thread(target=self.idle_thread, args=(), name="idleThread", daemon=True)
            idle_thread.start()
        except Exception as e:
            log.critical("Could not spawn idle thread: %s" % e)
            raise e
        return True
