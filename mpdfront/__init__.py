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
    arg_parser.add_argument("-c", "--config", default=Constants.config_file, action='store', help="Config file.")
    args = arg_parser.parse_args()

    ## load configs and run application
    if not os.path.exists(args.config):  ## verify config file exists
        sys.stderr.write("config file not found: %s\n" % args.config)
        sys.exit(1)
    config = configparser.ConfigParser()
    config.read(args.config)

    ## load logger config
    try:
        logger_config = config.get("main", "logger_config")
        if logger_config and os.path.isfile(logger_config):
            with open(logger_config, 'r') as f:
                log_cfg = yaml.safe_load(f.read())
            logging.config.dictConfig(log_cfg)
    except configparser.NoOptionError as e:
        pass
    except Exception as e:
        sys.stderr.write("could not load logger config: %s\n" % e)

    try:
        app = MpdFrontApp(config=config, css_file=args.css, application_id=Constants.application_id)
    except Exception as e:
        sys.stderr.write("could not create application: %s\n" % e)
        sys.exit(2)

    app.run(None)
    sys.exit(0)
