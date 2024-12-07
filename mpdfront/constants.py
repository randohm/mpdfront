import os

class Constants:
    application_id = "com.github.randohm.mpdfront"
    log_format = "%(asctime)s %(levelname)s %(threadName)s %(module)s::%(funcName)s(%(lineno)d): %(message)s"
    config_file = os.environ['HOME'] + "/.config/mpdfront/mpdfront.cfg"
    idle_sleep_retry_connect = 2
    display_referesh_interval = 330

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
    #keyval_delete = 0x

    ## names of data nodes
    topnode_name_albumartists = "Album Artists"
    topnode_name_artists = "Artists"
    topnode_name_albums = "Albums"
    topnode_name_genres = "Genres"
    topnode_name_files = "Files"

    ## Rows for 1st column of browser
    browser_1st_column_rows = [
        {'type': 'category', 'name': topnode_name_albumartists, 'value': topnode_name_albumartists, 'data': None},
        {'type': 'category', 'name': topnode_name_artists, 'value': topnode_name_artists, 'data': None},
        {'type': 'category', 'name': topnode_name_albums, 'value': topnode_name_albums, 'data': None},
        {'type': 'category', 'name': topnode_name_genres, 'value': topnode_name_genres, 'data': None},
        {'type': 'category', 'name': topnode_name_files, 'value': topnode_name_files, 'data': None},
    ]

    proc_file_fmt = "/proc/asound/card%s/pcm%sp/sub%s/hw_params"  ## proc file with DAC information
    #proc_file_fmt = "./hw_params"

    ## QueueMessage types and items
    message_type_change = "change"
    message_item_playlist = "playlist"
    message_item_player = "player"
    message_type_command = "command"
    message_type_data = "data"

    ## sleep/wait intervals
    check_thread_comms_interval = 1000      ## milliseconds
    playback_update_interval_play = 1000    ## milliseconds
    reconnect_retry_sleep_secs = 1          ## seconds
    thread_alive_check_interval = 1000      ## milliseconds

