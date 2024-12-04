import os

class Constants:
    application_id = "com.github.randohm.mpdfront"
    log_format = "%(asctime)s %(levelname)s %(threadName)s %(module)s::%(funcName)s(%(lineno)d): %(message)s"
    config_file = os.environ['HOME'] + "/.config/mpdfront/mpdfront.cfg"
    idle_sleep_retry_connect = 2

    ## symbols for playback control button labels
    symbol_previous = chr(9612) + chr(9664)
    symbol_rewind = chr(9664) + chr(9664)
    symbol_stop = " " + chr(9608) + " "
    symbol_play = chr(9613) + chr(9654)
    symbol_pause = chr(9613) + chr(9613)
    symbol_cue = chr(9654) + chr(9654)
    symbol_next = chr(9654) + " " + chr(9612)

    ## Key codes
    keyval_play = 0x1008ff14
    keyval_rewind = 0x1008ff3e
    keyval_cue = 0x1008ff97
    keyval_previous = 0x1008ff16
    keyval_next = 0x1008ff17

    ## Rows for 1st column of browser
    browser_1st_column_rows = [
        {'type': 'category', 'value': 'Album Artists', 'data': None},
        {'type': 'category', 'value': 'Artists', 'data': None},
        {'type': 'category', 'value': 'Albums', 'data': None},
        {'type': 'category', 'value': 'Files', 'data': None},
        {'type': 'category', 'value': 'Genres', 'data': None},
    ]

    proc_file_fmt = "/proc/asound/card%s/pcm%sp/sub%s/hw_params"  ## proc file with DAC information
    #proc_file_fmt = "./hw_params"
