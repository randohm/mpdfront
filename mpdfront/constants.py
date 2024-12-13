import os

class Constants:
    application_id = "com.github.randohm.mpdfront"
    window_title = "MPD Front"
    default_host = "localhost"
    default_port = 6600
    default_width = 1920
    default_height = 1080
    default_config_file = os.environ['HOME'] + "/.config/mpdfront/mpdfront.cfg"
    default_log_format = "%(asctime)s %(levelname)s %(threadName)s %(module)s::%(funcName)s(%(lineno)d): %(message)s"
    browser_num_columnns = 4

    rewind_arg = "-5"
    cue_arg = "+5"

    ## symbols for playback control button labels
    symbol_previous = chr(9612) + chr(9664)
    symbol_rewind = chr(9664) + chr(9664)
    symbol_stop = " " + chr(9608) + " "
    symbol_play = chr(9613) + chr(9654)
    symbol_pause = chr(9613) + chr(9613)
    symbol_cue = chr(9654) + chr(9654)
    symbol_next = chr(9654) + " " + chr(9612)

    ## names of toplevel data nodes
    topnode_name_albumartists = "Album Artists"
    topnode_name_artists = "Artists"
    topnode_name_albums = "Albums"
    topnode_name_genres = "Genres"
    topnode_name_files = "Files"

    ## node metatypes
    node_t_category = "category"
    node_t_albumartist = "albumartist"
    node_t_artist = "artist"
    node_t_album = "album"
    node_t_genre = "genre"
    node_t_dir = "directory"
    node_t_file = "file"
    node_t_song = "song"

    ## Rows for 1st column of browser
    browser_1st_column_rows = [
        {'type': node_t_category, 'name': topnode_name_albumartists, 'next_type': node_t_albumartist},
        {'type': node_t_category, 'name': topnode_name_artists, 'next_type': node_t_artist},
        {'type': node_t_category, 'name': topnode_name_albums, 'next_type': node_t_album},
        {'type': node_t_category, 'name': topnode_name_genres, 'next_type': node_t_genre},
        {'type': node_t_category, 'name': topnode_name_files, 'next_type': node_t_dir},
    ]

    proc_file_fmt = "/proc/asound/card%s/pcm%sp/sub%s/hw_params"  ## proc file with DAC information
    #proc_file_fmt = "./hw_params"

    ## QueueMessage types and items
    message_type_change = "change"
    message_item_playlist = "playlist"
    message_item_player = "player"

    ## sleep/wait intervals
    idle_thread_interval = 334              ## milliseconds
    playback_refresh_interval = 1000        ## milliseconds
    reconnect_retry_sleep_secs = 1          ## seconds
    alive_check_interval = 5000             ## milliseconds

    config_section_main = "main"
    config_section_keys = "keys"

    divider_tolerance = 5       ## tolerance in pixels for how close the paned divider is to the edge
    pixel_tolerance = 12        ## tolerance in pixels for general geometry calculations
    button_box_spacing = 5

    playlist_confirm_reponse_cancel = 0
    playlist_confirm_reponse_add = 1
    playlist_confirm_reponse_replace = 2

    playlist_edit_response_cancel = 0
    playlist_edit_response_play = 1
    playlist_edit_response_up = 2
    playlist_edit_response_down = 3
    playlist_edit_response_delete = 4

    progressbar_height = 20