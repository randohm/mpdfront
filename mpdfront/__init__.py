import sys, os, signal
import logging, logging.config
import argparse
import configparser
import yaml
from .constants import Constants
from .application import MpdFrontApp

log = logging.getLogger(__name__)

def signal_exit(sig, frame):
    """
    Perform a clean exit.
    """
    sys.stderr.write("caught signal %s, exiting\n" % signal.Signals(sig).name)
    sys.exit(0)

def main():
    ## set signal handlers
    signal.signal(signal.SIGINT, signal_exit)
    signal.signal(signal.SIGTERM, signal_exit)

    ## parse args
    arg_parser = argparse.ArgumentParser(description="MPD Frontend", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    arg_parser.add_argument("-v", "--verbose", action='store_true', help="Turn on verbose output.")
    arg_parser.add_argument("-H", "--host", action='store', help="Remote host name or IP address.")
    arg_parser.add_argument("-p", "--port", type=int, action='store', help="Remote TCP port number.")
    arg_parser.add_argument("-s", "--css", action='store', help="CSS file for the Gtk App.")
    arg_parser.add_argument("-c", "--config", default=Constants.default_config_file, action='store', help="Config file.")
    args = arg_parser.parse_args()

    ## load configs and run application
    if not os.path.exists(args.config):  ## verify config file exists
        sys.stderr.write("config file not found: %s\n" % args.config)
        return  1
    config = configparser.ConfigParser()
    config.read(args.config)

    ## load logger config
    logger_config_loaded = False
    if config.has_option("main", "logger_config"):
        try:
            logger_config = config.get("main", "logger_config")
            if logger_config and os.path.isfile(logger_config):
                with open(logger_config, 'r') as f:
                    log_cfg = yaml.safe_load(f.read())
                logging.config.dictConfig(log_cfg)
                logger_config_loaded = True
        except configparser.NoOptionError as e:
            pass
        except Exception as e:
            sys.stderr.write("could not load logger config: %s\n" % e)
    ## Load default logger configs if no logger config file was loaded
    if not logger_config_loaded:
        formatter = logging.Formatter(Constants.default_log_format)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        log.addHandler(handler)
    if args.verbose:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)

    ## Create App object and run it
    try:
        app = MpdFrontApp(config=config, css_file=args.css, application_id=Constants.application_id, host=args.host, port=args.port)
    except Exception as e:
        sys.stderr.write("could not create application: %s\n" % e)
        return 2

    app.run(None)
    return 0
