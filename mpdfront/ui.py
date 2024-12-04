import sys, re, time, os, html, io
import logging
import PIL
from PIL import Image
import musicpd
import mutagen
from mutagen.id3 import ID3, APIC
from mutagen.flac import FLAC
from mutagen.dsf import DSF
from mutagen.mp4 import MP4
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GObject, Pango, GLib, Gio

from .constants import Constants

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
formatter = logging.Formatter(Constants.log_format)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
log.addHandler(handler)

def listbox_cmp(row1, row2, data, notify_destroy):
    """
    Compare function for Gtk.ListBox sorting. Does a simple string cmp on the rows' text
    Args:
        Standard args for Gtk.ListBox sort compare function.
    """
    return row1.get_child().get_text() > row2.get_child().get_text()

def listbox_cmp_filtered(row1, row2, data, notify_destroy):
    """
    Compare function for Gtk.ListBox sorting. Modifies the text before comparison.
    Removes from text: /^The /
    Args:
        Standard args for Gtk.ListBox sort compare function.
    """
    row1_value = re.sub(r'^The ', '', row1.get_child().get_text(), flags=re.IGNORECASE)
    row2_value = re.sub(r'^The ', '', row2.get_child().get_text(), flags=re.IGNORECASE)

    return row1_value > row2_value

def listbox_cmp_by_track(row1, row2, data, notify_destroy):
    """
    Compare function for Gtk.ListBox sorting. Modifies the text before comparison.
    Args:
        Standard args for Gtk.ListBox sort compare function.
    """
    if not ('track' in row1.get_child().data['track'] and 'track' in row2.get_child().data['track']):
        return 0
    row1_value = int(row1.get_child().data['track'])
    row2_value = int(row2.get_child().data['track'])

    return row1_value > row2_value

def pp_time(secs):
    """
    Pretty-print time convenience function. Takes a count of seconds and formats to MM:SS.

    Args:
        secs: int of number of seconds

    Returns:
        string with the time in the format of MM:SS
    """
    return "%d:%02d" % (int(int(secs) / 60), int(secs) % 60)

class SongInfoDialog(Gtk.AlertDialog):
    """
    Shows a MessageDialog with song tags and information.
    Click OK to exit.
    """

    def __init__(self, parent, song, *args, **kwargs):
        """
        Build markup text to display, display markup text
        """
        super().__init__(*args, **kwargs)
        self.set_modal(True)
        message = ""
        detail = ""
        if 'title' in song:
            message = song['title']
        if 'artist' in song:
            detail += "Artist: %s\n" % song['artist']
        if 'album' in song:
            detail += "Album: %s\n" % song['album']
        if 'time' in song:
            detail += "Time: %s\n" % pp_time(song['time'])
        if 'track' in song:
            detail += "Track: %s\n" % song['track']
        if 'date' in song:
            detail += "Date: %s\n" % song['date']
        if 'genre' in song:
            detail += "Genre: %s\n" % song['genre']

        if message == "":
            message = "File: %s" % song['file']
        else:
            detail += "File: %s" % song['file']

        self.set_message(message)
        self.set_detail(detail)
        self.choose(parent=parent, cancellable=None, callback=None)

class CardSelectDialog(Gtk.Dialog):
    """
    Display dialog to select sound card and device IDs.
    Button click events are handled by a callback function passed to __init__.
    """

    def __init__(self, parent, button_pressed_callback, *args, **kwargs):
        """
        Args:
            parent: parent window
            button_pressed_callback: callback function handling spinbutton change events.
                                     callback accepts +1 args for the type of change.
        """
        super().__init__(title="Select Sound Card", parent=parent, *args, **kwargs)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.add_button("Close", 0)
        self.set_name("cardselect-dialog")
        self.get_content_area().set_size_request(300, 200)

        card_id_button = Gtk.SpinButton.new_with_range(0, 4, 1)
        card_id_button.set_name("card_id")
        card_id_button.set_numeric(True)
        card_id_button.set_value(parent.app.card_id)
        card_id_label = Gtk.Label(label="Card ID")
        card_id_button.connect("value-changed", button_pressed_callback, "card_id")

        device_id_button = Gtk.SpinButton.new_with_range(0, 4, 1)
        device_id_button.set_name("device_id")
        device_id_button.set_numeric(True)
        device_id_button.set_value(parent.app.device_id)
        device_id_label = Gtk.Label(label="Device ID")
        device_id_button.connect("value-changed", button_pressed_callback, "device_id")

        hbox1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox1.append(card_id_label)
        hbox1.append(card_id_button)
        hbox2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox2.append(device_id_label)
        hbox2.append(device_id_button)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.append(hbox1)
        vbox.append(hbox2)
        self.get_content_area().append(vbox)

        self.connect('response', self.on_response)
        self.show()

    def on_response(self, dialog, response):
        self.destroy()

class OutputsDialog(Gtk.Dialog):
    """
    Display dialog with list of outputs as individual CheckButtons.
    Button click events are handled by a callback function passed to __init__.
    """

    def __init__(self, parent, button_pressed_callback, *args, **kwargs):
        """
        Args:
            parent: parent window
            button_pressed_callback: callback function handling checkbutton click events. callback accepts 1 arg with the output ID.
        """
        super().__init__(title="Select Outputs", parent=parent, *args, **kwargs)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.add_button("Close", 0)
        self.set_name("outputs-dialog")
        self.get_content_area().set_size_request(300, 200)
        for o in parent.app.mpd_outputs:
            log.debug("output: %s" % o)
            button = Gtk.CheckButton.new_with_label(o['outputname'])
            button.set_active(int(o['outputenabled']))
            self.get_content_area().append(button)
            button.connect("toggled", button_pressed_callback, o['outputid'])
        self.connect('response', self.on_response)
        self.show()

    def on_response(self, dialog, response):
        self.destroy()

class OptionsDialog(Gtk.Dialog):
    """
    Displays dialog of options. Each option is an individual CheckButton.
    Button click events are handled by a callback function passed to __init__.
    """
    def __init__(self, parent, button_pressed_callback, *args, **kwargs):
        """
        Args:
            parent: parent window
            button_pressed_callback: callback function handling checkbutton click events. callback accepts 1 arg with the option name.
        """
        super().__init__(title="Set Options", parent=parent, *args, **kwargs)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.add_button("Close", 0)
        self.set_name("options-dialog")
        self.get_content_area().set_size_request(300, 200)
        mpd_status = parent.app.mpd_cmd.status()

        self.consume_button = Gtk.CheckButton.new_with_label("Consume")
        self.consume_button.set_active(int(mpd_status['consume']))
        self.consume_button.connect("toggled", button_pressed_callback, "consume")
        self.get_content_area().append(self.consume_button)

        self.shuffle_button = Gtk.CheckButton.new_with_label("Shuffle")
        self.shuffle_button.set_active(int(mpd_status['random']))
        self.shuffle_button.connect("toggled", button_pressed_callback, "random")
        self.get_content_area().append(self.shuffle_button)

        self.repeat_button = Gtk.CheckButton.new_with_label("Repeat")
        self.repeat_button.set_active(int(mpd_status['repeat']))
        self.repeat_button.connect("toggled", button_pressed_callback, "repeat")
        self.get_content_area().append(self.repeat_button)

        self.single_button = Gtk.CheckButton.new_with_label("Single")
        self.single_button.set_active(int(mpd_status['single']))
        self.single_button.connect("toggled", button_pressed_callback, "single")
        self.get_content_area().append(self.single_button)

        self.connect('response', self.on_response)
        self.show()

    def on_response(self, dialog, response):
        self.destroy()

class PlaylistConfirmDialog(Gtk.Dialog):
    """
    """
    def __init__(self, parent, add_item_name, *args, **kwargs):
        super().__init__(title="Update playlist?", parent=parent, *args, **kwargs)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.add_button("Add", 1)
        self.add_button("Replace", 2)
        self.add_button("Cancel", 3)
        self.get_content_area().append(Gtk.Label(label="Selected: " + add_item_name))
        self.get_content_area().set_size_request(300, 100)
        #style_context = self.get_style_context()
        #style_context.add_provider(self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.connect('response', parent.playlist_dialog_response)
        self.show()

class MetadataLabel(Gtk.Label):
    """
    Gtk.Label with 2 accessible variables: data and type.
    """

    def set_metadata(self, data):
        """
        Set the metadata for the label

        Args:
            data: can be anything
        """
        self.data = data

    def set_metatype(self, t):
        """
        Set the metatype for the label

        Args:
            t: can be anything
        """
        self.type = t

class IndexedListBox(Gtk.ListBox):
    """
    Gtk.ListBox with an index variable. This allows ListBoxes to track their position in list of ListBoxes.
    """
    def set_index(self, index):
        """
        Sets the index of the ListBox

        Args:
            index:  int, the ListBox's position in the parent's list
        """
        self.index = index

class ColumnBrowser(Gtk.Box):
    """
    Column browser for a tree data structure. Inherits from GtkBox.
    Creates columns with a list of GtkScrolledWindows containing a GtkListBox.
    """
    def __init__(self, selected_callback=None, keypress_callback=None, cols=2, spacing=0, hexpand=True, vexpand=True, *args, **kwargs):
        """
        Constructor for the column browser.

        Args:
            selected_callback: callback function for handling row-selected events
            keypress_callback: callback function for handling key-press-event events
            cols: int for number of colums
            hexpand: boolean for whether to set horizontal expansion
            vexpand: boolean for whether to set vertical expansion
        """
        if not selected_callback or not keypress_callback:
            err_msg = "callback functions must be defined"
            log.error(err_msg)
            raise ValueError(err_msg)
        super().__init__(*args, **kwargs)
        self.set_spacing(spacing)
        if cols < 1:
            raise ValueError("Number of columns must be greater than 1")
        self.columns = []
        for i in range(0, cols):
            scroll = Gtk.ScrolledWindow()
            listbox = IndexedListBox()
            listbox.set_hexpand(hexpand)
            listbox.set_vexpand(vexpand)
            listbox.set_index(i)
            listbox.connect("row-selected", selected_callback)
            #listbox.connect("row-activated", keypress_callback)
            scroll.set_child(listbox)
            self.append(scroll)
            self.columns.append(listbox)

        self.controller = Gtk.EventControllerKey.new()
        self.controller.connect('key-pressed', keypress_callback)
        self.add_controller(self.controller)

    def get_selected_rows(self):
        """
        Gets the child objects of all selected rows.
        Inserting them into a list in order from least to highest column index.

        Returns:
            list of selected rows' child objects.
        """
        log.debug("looking for selected row")
        ret = []
        for c in self.columns:
            row = c.get_selected_row()
            if row:
                child = row.get_child()
                ret.append({'type': child.type, 'value': child.get_text(), 'data': child.data})
        return ret

    def set_column_data(self, col_index, data, clear_rest=True):
        """
        Populates a column at col_index.
        Args:
            col_index:  int, column index
            data:  dictionary
            clear_rest: boolean, True: clear all columns to the left as well. default: True
        """
        if clear_rest:
            for i in range(col_index, len(self.columns)):
                self.columns[i].remove_all()

        for i in data:
            #log.debug("data: %s" % i)
            label = MetadataLabel(label=i['value'])
            label.set_metatype(i['type'])
            label.set_metadata(i['data'])
            label.set_halign(Gtk.Align.START)
            self.columns[col_index].append(label)

class PlaybackDisplay(Gtk.Box):
    def __init__(self, parent, sound_card:str=None, sound_device:int=None, *args, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, *args, **kwargs)
        self.parent = parent
        self.sound_card = sound_card
        self.sound_device = sound_device
        self.set_name("playback-display")

        song_display_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        song_display_box.set_hexpand(True)
        song_display_box.set_vexpand(True)
        playback_info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        playback_info_box.set_hexpand(True)
        playback_info_box.set_vexpand(True)
        song_display_box.append(playback_info_box)

        ## Current album art
        self.current_albumart = Gtk.Picture()
        self.current_albumart.set_valign(Gtk.Align.START)
        self.current_albumart.set_halign(Gtk.Align.END)
        self.current_albumart.set_vexpand(True)
        self.current_albumart.set_hexpand(True)
        song_display_box.append(self.current_albumart)
        self.append(song_display_box)

        # song title label
        self.current_title_label = Gtk.Label(label=" ")
        self.current_title_label.set_name("current-title")
        self.current_title_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.current_title_label.set_halign(Gtk.Align.START)
        self.current_title_label.set_valign(Gtk.Align.START)
        self.current_title_label.set_wrap(True)
        self.current_title_label.set_hexpand(False)

        # artist label
        self.current_artist_label = Gtk.Label(label=" ")
        self.current_artist_label.set_name("current-artist")
        self.current_artist_label.set_halign(Gtk.Align.START)
        self.current_artist_label.set_valign(Gtk.Align.START)
        self.current_artist_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.current_artist_label.set_wrap(False)
        self.current_artist_label.set_hexpand(False)

        # album label
        self.current_album_label = Gtk.Label(label=" ")
        self.current_album_label.set_name("current-album")
        self.current_album_label.set_halign(Gtk.Align.START)
        self.current_album_label.set_valign(Gtk.Align.START)
        self.current_album_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.current_album_label.set_wrap(False)
        self.current_album_label.set_hexpand(False)

        # stats1 label
        self.stats1_label = Gtk.Label(label=" ")
        self.stats1_label.set_name("stats1")
        self.stats1_label.set_halign(Gtk.Align.START)
        self.stats1_label.set_valign(Gtk.Align.END)
        self.stats1_label.set_wrap(True)
        self.stats1_label.set_hexpand(True)

        # stats2 label
        self.stats2_label = Gtk.Label(label=" ")
        self.stats2_label.set_name("stats2")
        self.stats2_label.set_halign(Gtk.Align.START)
        self.stats2_label.set_valign(Gtk.Align.END)
        self.stats2_label.set_wrap(True)
        self.stats2_label.set_hexpand(True)

        # time label
        self.current_time_label = Gtk.Label(label=" ")
        self.current_time_label.set_name("current-time")
        self.current_time_label.set_halign(Gtk.Align.START)
        self.current_time_label.set_valign(Gtk.Align.END)
        self.current_time_label.set_wrap(True)
        self.current_time_label.set_hexpand(False)

        ## Add labels to playback grid
        playback_info_box.append(self.current_title_label)
        playback_info_box.append(self.current_artist_label)
        playback_info_box.append(self.current_album_label)
        playback_info_box.append(self.current_time_label)
        playback_info_box.append(self.stats2_label)
        playback_info_box.append(self.stats1_label)

        ## Song progress bar
        self.song_progress = Gtk.LevelBar()
        self.song_progress.set_size_request(-1, 20)
        self.song_progress.set_name("progressbar")
        self.append(self.song_progress)

        ## Setup playback button box
        self.playback_button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.playback_button_box.set_spacing(4)
        self.previous_button = Gtk.Button(label=Constants.symbol_previous)
        self.rewind_button = Gtk.Button(label=Constants.symbol_rewind)
        self.stop_button = Gtk.Button(label=Constants.symbol_stop)
        self.play_button = Gtk.Button(label=Constants.symbol_play)
        self.cue_button = Gtk.Button(label=Constants.symbol_cue)
        self.next_button = Gtk.Button(label=Constants.symbol_next)
        self.previous_button.set_hexpand(True)
        self.rewind_button.set_hexpand(True)
        self.stop_button.set_hexpand(True)
        self.play_button.set_hexpand(True)
        self.cue_button.set_hexpand(True)
        self.next_button.set_hexpand(True)
        self.playback_button_box.append(self.previous_button)
        self.playback_button_box.append(self.rewind_button)
        self.playback_button_box.append(self.stop_button)
        self.playback_button_box.append(self.play_button)
        self.playback_button_box.append(self.cue_button)
        self.playback_button_box.append(self.next_button)
        self.playback_button_box.set_hexpand(True)
        self.append(self.playback_button_box)

        # set button event handlers
        prev_button_ctrlr = Gtk.GestureClick.new()
        prev_button_ctrlr.connect("pressed", self.previous_clicked)
        self.previous_button.add_controller(prev_button_ctrlr)

        rew_button_ctrlr = Gtk.GestureClick.new()
        rew_button_ctrlr.connect("pressed", self.rewind_clicked)
        self.rewind_button.add_controller(rew_button_ctrlr)

        stop_button_ctrlr = Gtk.GestureClick.new()
        stop_button_ctrlr.connect("pressed", self.stop_clicked)
        self.stop_button.add_controller(stop_button_ctrlr)

        play_button_ctrlr = Gtk.GestureClick.new()
        play_button_ctrlr.connect("pressed", self.play_clicked)
        self.play_button.add_controller(play_button_ctrlr)

        cue_button_ctrlr = Gtk.GestureClick.new()
        cue_button_ctrlr.connect("pressed", self.cue_clicked)
        self.cue_button.add_controller(cue_button_ctrlr)

        next_button_ctrlr = Gtk.GestureClick.new()
        next_button_ctrlr.connect("pressed", self.next_clicked)
        self.next_button.add_controller(next_button_ctrlr)

    def update(self, mpd_status=None, mpd_currentsong=None, music_dir=""):
        log.debug("status: %s" % mpd_status)
        log.debug("currentsong: %s" % mpd_currentsong)

        ## Set labels with song information. Set to empty if there is no current song.
        if mpd_currentsong:
            if 'artist' in mpd_currentsong and 'title' in mpd_currentsong and 'album' in mpd_currentsong:
                self.current_title_label.set_text(mpd_currentsong['title'])
                self.current_artist_label.set_text(mpd_currentsong['artist'])
                self.current_album_label.set_text(mpd_currentsong['album'])
            else:
                filename = os.path.basename(mpd_currentsong['file'])
                self.current_title_label.set_text(" ")
                self.current_artist_label.set_text(filename)
                self.current_album_label.set_text(" ")
        else:
            self.current_title_label.set_text(" ")
            self.current_artist_label.set_text(" ")
            self.current_album_label.set_text(" ")

        ## Get stream rates, format
        freq = bits = bitrate = chs = ""
        if 'audio' in mpd_status.keys():
            if re.match(r'dsd\d+:', mpd_status['audio']):
                bits = "dsd"
                freq, chs = re.split(r':', mpd_status['audio'], maxsplit=1)
            else:
                freq, bits, chs = re.split(r':', mpd_status['audio'], maxsplit=2)
        if 'bitrate' in mpd_status.keys():
            bitrate = mpd_status['bitrate']

        ## Format and set stream/dac information. Set to empty if there is no info to display
        format_text = dac_text = ""
        if freq and bits and chs and bitrate:
            if bits == "dsd":
                if re.match(r'dsd', freq):
                    format_text = freq
                else:
                    format_text = "%2.1f MHz DSD" % (float(bitrate) / 1000)
            elif bits == "f":
                format_text = "%3.1f kHz float PCM" % (float(freq) / 1000)
            else:
                format_text = "%3.1f kHz %s bit PCM" % (float(freq) / 1000, bits)
            self.stats1_label.set_markup("<small><b>src:</b></small> " + format_text + " @ " + bitrate + " kbps")

            ## Get and format DAC rate, format
            dac_freq = dac_bits = ""
            proc_file = Constants.proc_file_fmt % (self.sound_card, self.sound_device, "0")
            #log.debug("proc file: %s" % proc_file)
            if os.path.exists(proc_file):
                lines = ()
                try:
                    fh = open(proc_file)
                    lines = fh.readlines()
                    fh.close()
                except Exception as e:
                    log.error("opening up proc file: %s" % e)
                for line in lines:
                    line = line.rstrip()
                    #log.debug("procfile line: %s" % line)
                    if re.match(r'rate:', line):
                        (junk1, dac_freq, junk2) = re.split(r' ', line, maxsplit=2)
                    elif re.match(r'format:', line):
                        (junk1, dac_bits) = re.split(r': ', line, maxsplit=1)
                    elif re.match(r'closed', line):
                        break
                if dac_freq and dac_bits:
                    num_bits = 0
                    if dac_bits in ("S32_LE"):
                        num_bits = 32
                    elif dac_bits in ("S24_LE", "S24_3LE"):
                        num_bits = 24
                    elif dac_bits in ("S16_LE"):
                        num_bits = 16
                    dac_text = "%3.1f kHz %d bit" % (float(dac_freq) / 1000, num_bits)
            else:
                #log.debug("proc file does not exist")
                None
            self.stats2_label.set_markup("<small><b>dac:</b></small> " + dac_text)
        else:
            self.stats1_label.set_text(" ")
            self.stats2_label.set_text(" ")

        ## Format and set time information and state
        if 'time' in mpd_status.keys():
            print_state = "Playing"
            if mpd_status['state'] == "pause":
                print_state = "Paused"
            self.song_progress.set_max_value(int(float(mpd_status['duration'])))
            self.song_progress.set_value(int(float(mpd_status['elapsed'])))
            self.current_time_label.set_text(pp_time(int(float(mpd_status['elapsed']))) + " / " + pp_time(
                int(float(mpd_status['duration']))) + " " + print_state)
        elif mpd_status['state'] == "stop":
            self.song_progress.set_value(0)
            self.current_time_label.set_text("Stopped")
            self.last_update_offset = 0

        self.set_current_albumart(mpd_currentsong, music_dir)

    def get_albumart(self, audiofile, mpd_currentsong, music_dir):
        """
        Extract album art from a file, or look for a cover in its directory.
        Tries to fetch art from Last.fm if all else fails.

        Args:
            audiofile: string, path of the file containing the audio data

        Returns:
            raw image data
        """
        img_data = None

        ## Try to find album art in the media file
        try:
            if re.search(r'\.flac$', mpd_currentsong['file'], re.IGNORECASE):
                a = FLAC(audiofile)
                if len(a.pictures):
                    img_data = a.pictures[0].data
            elif re.search(r'\.m4a$', mpd_currentsong['file'], re.IGNORECASE):
                a = MP4(audiofile)
                if 'covr' in a.tags:
                    if len(a.tags['covr']):
                        img_data = a.tags['covr'][0]
            else:
                a = mutagen.File(audiofile)
                for k in a.keys():
                    if re.match(r'APIC:', k):
                        img_data = a[k].data
                        break
        except Exception as e:
            log.error("could not open audio file: %s" % e)

        ## Look for album art on the directory of the media file
        if not img_data:
            cover_path = ""
            song_dir = music_dir + "/" + os.path.dirname(mpd_currentsong['file'])
            try:
                for f in os.listdir(song_dir):
                    if re.match(r'cover\.(jpg|png|jpeg)', f, re.IGNORECASE):
                        cover_path = song_dir + "/" + f
                        break
                log.debug("looking for cover file: %s" % cover_path)
                if os.path.isfile(cover_path):
                    cf = open(cover_path, 'rb')
                    img_data = cf.read()
                    cf.close()
            except Exception as e:
                log.error("error reading cover file: %s" % e)
        return img_data

    def set_current_albumart(self, mpd_currentsong=None, music_dir=""):
        """
        Load and display image of current song if it has changed since the last time this function was run, or on the first run.
        Loads image data into a PIL.Image object, then into a GdkPixbuf object, then into a Gtk.Image object for display.
        """
        if not mpd_currentsong or not 'file' in mpd_currentsong.keys():
            return

        audiofile = music_dir + "/" + mpd_currentsong['file']
        if not hasattr(self, 'last_audiofile') or self.last_audiofile != audiofile:
            ## The file has changed since the last update, get the new album art.
            log.debug("new cover file, updating")
            img_data = self.get_albumart(audiofile, mpd_currentsong, music_dir)
            if img_data:
                ## Album art retrieved, load it into a pixbuf
                img = Image.open(io.BytesIO(img_data))
                img_bytes = GLib.Bytes.new(img.tobytes())
                log.debug("image size: %d x %d" % img.size)
                w, h = img.size
                if img.has_transparency_data:
                    current_albumart_pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(img_bytes, GdkPixbuf.Colorspace.RGB,
                                                                                   True, 8, w, h, w * 4)
                else:
                    current_albumart_pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(img_bytes, GdkPixbuf.Colorspace.RGB,
                                                                                   False, 8, w, h, w * 3)
            else:
                ## No album art, clear the image in the UI.
                #self.current_albumart.clear()
                self.last_audiofile = audiofile
                return

        if not hasattr(self, 'last_audiofile') or self.last_audiofile != audiofile:
            ## Update the image
            if current_albumart_pixbuf:
                self.current_albumart.set_pixbuf(current_albumart_pixbuf)
            else:
                log.debug("could not get pixbuf, clearing album art")
                self.current_albumart.clear()
        self.last_audiofile = audiofile

    ##  Click handlers

    def previous_clicked(self, controller, x, y, user_data):
        """
        Click handler for previous button
        """
        self.parent.app.mpd_cmd.previous()
        controller.reset()

    def rewind_clicked(self, controller, x, y, user_data):
        """
        Click handler for rewind button
        """
        self.parent.app.mpd_cmd.seekcur("-5")
        controller.reset()

    def stop_clicked(self, controller, x, y, user_data):
        """
        Click handler for stop button
        """
        self.parent.app.mpd_cmd.stop()
        controller.reset()

    def play_clicked(self, controller, x, y, user_data):
        """
        Click handler for play/pause button
        """
        self.parent.app.mpd_cmd.play_or_pause()
        controller.reset()

    def cue_clicked(self, controller, x, y, user_data):
        """
        Click handler for cue button
        """
        self.parent.app.mpd_cmd.seekcur("+5")
        controller.reset()

    def next_clicked(self, controller, x, y, user_data):
        """
        Click handler for next button
        """
        self.parent.app.mpd_cmd.next()
        controller.reset()

class PlaylistDisplay(Gtk.ListBox):
    """
    Handles display and updates of the playlist. The listbox entries are controlled by a Gio.ListStore listmodel.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_name("playlistbox")
        self.liststore = Gio.ListStore()
        self.bind_model(model=self.liststore, create_widget_func=self.create_list_label)

    def update(self, playlist=None, mpd_currentsong=None):
        if playlist:
            self.liststore.remove_all()
            log.debug("playlist: %s" % playlist)
            ## Add songs to the list
            for song in playlist:
                log.debug("adding song to playlist: %s" % song['title'])
                self.liststore.append(PlaylistTrack(song))

            #if self.playlist_last_selected != None:
            #    self.select_row(self.get_row_at_index(self.playlist_last_selected))

            #if self.focus_on == "playlist" and self.playlist_list.get_row_at_index(self.playlist_last_selected):
            #    self.get_row_at_index(self.playlist_last_selected).grab_focus()

            #if 'pos' in mpd_currentsong:
            #    self.get_row_at_index(int(mpd_currentsong['pos'])).set_name("current")
            log.debug("playlist refresh complete")

    def create_list_label(self, track):
        if track.track and track.time and track.title:
            label_text = re.sub(r'/.*', '', html.escape(track.track)) + " (" + html.escape(
                pp_time(track.time)) + ") <b>" + html.escape(track.title) + "</b>"
        else:
            label_text = os.path.basename(track.song['file'])
        label = MetadataLabel()
        label.set_markup(label_text)
        label.set_metatype('song')
        label.set_metadata(track.song)
        label.set_halign(Gtk.Align.START)
        return label

class PlaylistTrack(GObject.GObject):
    def __init__(self, song: dict, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.song = song
        for k in song.keys():
            setattr(self, k, song[k])

class MpdFrontWindow(Gtk.ApplicationWindow):
    last_audiofile = ""  ## Tracks albumart for display
    resize_event_on = False  ## Flag for albumart to resize
    browser_full = False  ## Tracks if the browser is fullscreen
    browser_hidden = False  ## Tracks if the browser is hidden
    last_width = 0  ## Tracks width of window when window changes size
    last_height = 0  ## Tracks height of window when window changes size
    playlist_last_selected = None  ## Points to last selected song in playlist
    focus_on = "broswer"  ## Either 'playlist' or 'browser'
    initial_resized = False

    def __init__(self, config=None, application=None, *args, **kwargs):
        if not config or not application:
            err_msg = "config or app cannot be None"
            log.error(err_msg)
            raise ValueError(err_msg)
        super().__init__(application=application, *args, **kwargs)
        self.config = config
        self.set_default_size(int(config.get("main", "width")), int(config.get("main", "height")))
        self.set_resizable(False)
        self.set_decorated(False)
        self.app = application

        self.controller = Gtk.EventControllerKey.new()
        self.controller.connect('key-pressed', self.key_pressed)
        self.add_controller(self.controller)

        ## mainpaned is the toplevel layout container
        self.mainpaned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        self.mainpaned.set_name("mainpaned")
        self.set_child(self.mainpaned)

        ## Setup browser columns
        self.browser_box = ColumnBrowser(selected_callback=self.broswer_row_selected,
                                         keypress_callback=self.browser_key_pressed, cols=4, spacing=0,
                                         hexpand=True, vexpand=True)
        self.browser_box.set_name("browser")
        self.mainpaned.set_start_child(self.browser_box)
        self.browser_box.set_column_data(0, Constants.browser_1st_column_rows)

        ## Setup bottom half
        self.bottompaned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        #self.bottompaned.set_position(int(config.get("main", "width"))/2)
        self.mainpaned.set_end_child(self.bottompaned)

        self.playback_display = PlaybackDisplay(parent=self, sound_card=self.config.get("main", "sound_card"),
                                                sound_device=self.config.get("main", "sound_device"))
        self.bottompaned.set_start_child(self.playback_display)
        self.playback_display.update(self.app.mpd_cmd.status(), self.app.mpd_cmd.currentsong(),
                                     config.get("main", "music_dir"))

        ## Setup playlist
        self.playlist_list = PlaylistDisplay()
        self.playlist_scroll = Gtk.ScrolledWindow()
        self.playlist_scroll.set_name("playlistscroll")
        self.playlist_scroll.set_hexpand(True)
        self.playlist_scroll.set_child(self.playlist_list)
        self.bottompaned.set_end_child(self.playlist_scroll)
        self.playlist_list.update(self.app.mpd_cmd.playlistinfo(), self.app.mpd_cmd.currentsong())

        ## Set event handlers
        self.connect("destroy", self.close)
        self.connect("state_flags_changed", self.on_state_flags_changed)
        #self.connect("check-resize", self.window_resized)
        #self.playlist_list.connect("key-pressed", self.playlist_key_pressed)
        playlist_list_controller = Gtk.EventControllerKey.new()
        playlist_list_controller.connect("key-pressed", self.playlist_key_pressed)
        self.playlist_list.add_controller(playlist_list_controller)

        if re.match(r'yes$', self.config.get("main", "fullscreen"), re.IGNORECASE):
            self.fullscreen()

        self.app.get_albumartists()
        self.app.get_artists()
        self.app.get_albums()
        self.app.get_genres()
        self.app.get_files_list()

        self.playlist_last_selected = 0
        self.playlist_list.select_row(self.playlist_list.get_row_at_index(self.playlist_last_selected))
        self.browser_box.columns[0].select_row(self.browser_box.columns[0].get_row_at_index(0))

    ##  BEGIN EVENT HANDLERS

    def window_resized(self, widget):
        """
        Handler for window resize event
        """
        #log.debug("Window resize event")
        w = self.get_allocated_width()
        h = self.get_allocated_height()
        if self.last_width != w or self.last_height != h:
            self.last_width = w
            self.last_height = h
            self.resize_event_on = True
            self.resize_widgets()
            self.set_current_albumart()
            self.resize_event_on = False

    def on_keypress(self, controller, keyval, keycode, state):
        #log.debug("keypressed: %s %s %s" % (keyval, keycode, state))
        ctrl_pressed = state & Gdk.ModifierType.CONTROL_MASK
        cmd_pressed = state & Gdk.ModifierType.META_MASK
        if keyval in (ord('q'), ord('Q')) and (ctrl_pressed or cmd_pressed):
            log.debug("QUIT pressed")
            self.close()

    ##  Keyboard event handlers
    def key_pressed(self, controller, keyval, keycode, state):
        """
        Keypress handler for toplevel widget. Responds to global keys for playback control.
        """
        ctrl_pressed = state & Gdk.ModifierType.CONTROL_MASK
        cmd_pressed = state & Gdk.ModifierType.META_MASK   ## Cmd
        #shift_pressed = state & Gdk.ModifierType.SHIFT_MASK
        #alt_pressed = state & Gdk.ModifierType.ALT_MASK

        error = False
        reconnect = False
        try:
            log.debug("Key pressed: %x" % keyval)
            if (ctrl_pressed or cmd_pressed) and keyval in (ord('q'), ord('Q')):
                log.debug("QUIT pressed")
                self.close()
            elif keyval == Constants.keyval_play or keyval == ord(self.config.get("keys", "playpause")):
                log.debug("PLAY/PAUSE")
                self.app.mpd_cmd.play_or_pause()
            elif keyval == ord(self.config.get("keys", "stop")):
                log.debug("STOP")
                self.app.mpd_cmd.stop()
            elif keyval == Constants.keyval_previous or keyval == ord(self.config.get("keys", "previous")):
                log.debug("PREVIOUS")
                self.app.mpd_cmd.previous()
            elif keyval == Constants.keyval_next or keyval == ord(self.config.get("keys", "next")):
                log.debug("NEXT")
                self.app.mpd_cmd.next()
            elif keyval == Constants.keyval_rewind or keyval == ord(self.config.get("keys", "rewind")):
                log.debug("REWIND")
                self.app.mpd_cmd.seekcur("-5")
            elif keyval == Constants.keyval_cue or keyval == ord(self.config.get("keys", "cue")):
                log.debug("CUE")
                self.app.mpd_cmd.seekcur("+5")

            elif keyval == ord(self.config.get("keys", "outputs")):
                self.outputs_dialog = OutputsDialog(self, self.outputs_changed)
                #response = self.outputs_dialog.run()
                #self.outputs_dialog.destroy()

            elif keyval == ord(self.config.get("keys", "options")):
                self.options_dialog = OptionsDialog(self, self.options_changed)
                #response = self.options_dialog.run()
                #self.options_dialog.destroy()

            elif keyval == ord(self.config.get("keys", "cardselect")):
                self.cards_dialog = CardSelectDialog(self, self.soundcard_changed)
                #response = self.cards_dialog.run()
                #self.cards_dialog.destroy()

            elif keyval == ord(self.config.get("keys", "browser")):
                ## Focus on the last selected row in the browser
                self.focus_on = "broswer"
                selected_items = self.browser_box.get_selected_rows()
                if not len(selected_items):
                    self.browser_box.columns[0].select_row(self.browser_box.columns[0].get_row_at_index(0))
                    selected_items = self.browser_box.get_selected_rows()
                focus_col = self.browser_box.columns[len(selected_items) - 1]
                focus_row = focus_col.get_selected_row()
                focus_row.grab_focus()

            elif keyval == ord(self.config.get("keys", "playlist")):
                ## Focus on the selected row in the playlist
                self.focus_on = "playlist"
                selected_row = self.playlist_list.get_selected_row()
                if not selected_row:
                    selected_row = self.playlist_list.get_row_at_index(0)
                    self.playlist_list.select_row(selected_row)
                selected_row.grab_focus()

            elif keyval == ord(self.config.get("keys", "full_browser")):
                ## Hide bottom pane/fullscreen browser
                if self.mainpaned.get_position() == self.last_height - 1:
                    self.mainpaned.set_position(int(self.last_height / 2))
                    self.resize_event_on = True
                    self.set_current_albumart()
                    self.resize_event_on = False
                else:
                    self.mainpaned.set_position(self.last_height)

            elif keyval == ord(self.config.get("keys", "full_bottom")):
                ## Hide top pane
                if self.mainpaned.get_position() == 0:
                    self.mainpaned.set_position(int(self.last_height / 2))
                else:
                    self.mainpaned.set_position(0)
                self.resize_event_on = True
                self.set_current_albumart()
                self.resize_event_on = False

            elif keyval == ord(self.config.get("keys", "full_playback")):
                ## Hide playlist
                if self.bottompaned.get_position() == self.last_width - 1:
                    self.bottompaned.set_position(int(self.last_width / 2))
                else:
                    self.bottompaned.set_position(self.last_width)
                self.resize_event_on = True
                self.set_current_albumart()
                self.resize_event_on = False

            elif keyval == ord(self.config.get("keys", "full_playlist")):
                ## Hide top pane
                if self.bottompaned.get_position() == 0:
                    self.bottompaned.set_position(int(self.last_width / 2))
                    self.resize_event_on = True
                    self.set_current_albumart()
                    self.resize_event_on = False
                else:
                    self.bottompaned.set_position(0)

            elif keyval == ord('v'):
                self.set_dividers()

            #elif keyval == Gdk.KEY_Right:
            #    log.debug("RIGHT")
            #elif keyval == Gdk.KEY_Left:
            ##    log.debug("LEFT")
            #elif keyval == Gdk.KEY_Up:
            #    log.debug("UP")
            #elif keyval == Gdk.KEY_Down:
            #    log.debug("DOWN")
            #else:
            #    log.debug("key press: %s" % keyval)
        except Exception as e:
            log.error("Unknown exception: %s" % e)

    def browser_key_pressed(self, controller, keyval, keycode, state):
        """
        Event handler for browser box key presses
        """
        if keyval == Gdk.KEY_Return:
            #log.debug("browser key: ENTER")
            self.add_to_playlist()

        elif keyval == ord(self.config.get("keys", "info")):
            self.browser_info_popup()

    def playlist_key_pressed(self, controller, keyval, keycode, state):
        """
        Event handler for playlist box key presses
        """
        if keyval == Gdk.KEY_Return:
            #log.debug("playlist key: ENTER")
            self.edit_playlist()

        elif keyval == ord(self.config.get("keys", "info")):
            self.playlist_info_popup()
        elif keyval == ord(self.config.get("keys", "moveup")):
            self.playlist_moveup()
        elif keyval == ord(self.config.get("keys", "movedown")):
            self.playlist_movedown()
        elif keyval == ord(self.config.get("keys", "delete")):
            self.playlist_delete()


    ##  Selected handlers

    def broswer_row_selected(self, listbox, row):
        """
        Handler for selection event in browser_box
        """
        if not row:
            return

        child = row.get_child()
        if child:
            metatype = child.type
            value = child.get_text()
            log.debug("col %d, %s: %s" % (listbox.index, metatype, value))
            if metatype == "category":
                if value == "Album Artists":
                    artists = self.app.get_albumartists()
                    #log.debug("albumartists: %s" % artists)
                    rows = []
                    for a in artists:
                        rows.append({'type': 'albumartist', 'value': a, 'data': None})
                    self.browser_box.set_column_data(listbox.index + 1, rows)
                    self.browser_box.columns[listbox.index + 1].set_sort_func(listbox_cmp_filtered, None, False)

                elif value == "Artists":
                    artists = self.app.get_artists()
                    #log.debug("artists: %s" % artists)
                    rows = []
                    for a in artists:
                        rows.append({'type': 'artist', 'value': a, 'data': None})
                    self.browser_box.set_column_data(listbox.index + 1, rows)
                    self.browser_box.columns[listbox.index + 1].set_sort_func(listbox_cmp_filtered, None, False)

                elif value == "Albums":
                    albums = self.app.get_albums()
                    rows = []
                    for a in albums:
                        rows.append({'type': 'album', 'value': a, 'data': None})
                    self.browser_box.set_column_data(listbox.index + 1, rows)
                    self.browser_box.columns[listbox.index + 1].set_sort_func(listbox_cmp_filtered, None, False)

                elif value == "Genres":
                    genres = self.app.get_genres()
                    rows = []
                    for g in genres:
                        rows.append({'type': 'genre', 'value': g, 'data': None})
                    self.browser_box.set_column_data(listbox.index + 1, rows)
                    self.browser_box.columns[listbox.index + 1].set_sort_func(listbox_cmp, None, False)

                elif value == "Files":
                    files = self.app.get_files_list()
                    #log.debug("files: %s" % files)
                    rows = []
                    for f in files:
                        subf = self.app.get_files_list(f['data']['dir'])
                        for f2 in subf:
                            rows.append(
                                {'type': f2['type'], 'value': f['value'] + "/" + f2['value'], 'data': f2['data'], })
                    self.browser_box.set_column_data(listbox.index + 1, rows)
                    self.browser_box.columns[listbox.index + 1].set_sort_func(listbox_cmp, None, False)

                else:
                    self.browser_box.set_column_data(listbox.index + 1, [])

            elif metatype == "albumartist":
                albums = self.app.get_albums_by_albumartist(value)
                #log.debug("albums: %s" % albums)
                rows = []
                for a in albums:
                    rows.append({'type': 'album', 'value': a, 'data': None})
                self.browser_box.set_column_data(listbox.index + 1, rows)
                self.browser_box.columns[listbox.index + 1].set_sort_func(listbox_cmp, None, False)

            elif metatype == "artist":
                albums = self.app.get_albums_by_artist(value)
                #log.debug("albums: %s" % albums)
                rows = []
                for a in albums:
                    rows.append({'type': 'album', 'value': a, 'data': None})
                self.browser_box.set_column_data(listbox.index + 1, rows)
                self.browser_box.columns[listbox.index + 1].set_sort_func(listbox_cmp, None, False)

            elif metatype == "genre":
                albums = self.app.get_albums_by_genre(value)
                #log.debug("albums: %s" % albums)
                rows = []
                for a in albums:
                    rows.append({'type': 'album', 'value': a, 'data': None})
                self.browser_box.set_column_data(listbox.index + 1, rows)
                self.browser_box.columns[listbox.index + 1].set_sort_func(listbox_cmp, None, False)

            elif metatype == "album":
                selected_items = self.browser_box.get_selected_rows()
                #log.debug("selected items: %s" % selected_items)
                last_type = selected_items[listbox.index - 1]['type']
                last_value = selected_items[listbox.index - 1]['value']
                #log.debug("%s %s" % (value, last_value))
                songs = None
                if last_type == "albumartist":
                    songs = self.app.get_songs_by_album_by_albumartist(value, last_value)

                elif last_type == "artist":
                    songs = self.app.get_songs_by_album_by_artist(value, last_value)

                elif last_type == "category":
                    songs = self.app.get_songs_by_album(value)

                elif last_type == "genre":
                    songs = self.app.get_songs_by_album_by_genre(value, last_value)

                rows = []
                if songs:
                    for s in songs:
                        #log.debug(s)
                        track = ""
                        if 'track' in s:
                            track = re.sub(r'/.*', '', s['track'])
                        if 'title' in s:
                            rows.append({'type': 'song', 'value': track + " " + s['title'], 'data': s})
                        else:
                            rows.append({'type': 'song', 'value': os.path.basename(s['file']), 'data': s})
                self.browser_box.set_column_data(listbox.index + 1, rows)
                self.browser_box.columns[listbox.index + 1].set_sort_func(listbox_cmp_by_track, None, False)

            elif metatype == "directory":
                files = self.app.get_files_list(child.data['dir'])
                rows = []
                for f in files:
                    #log.debug("directory: %s" % f)
                    rows.append(f)
                self.browser_box.set_column_data(listbox.index + 1, rows)
                self.browser_box.columns[listbox.index + 1].set_sort_func(listbox_cmp, None, False)

    ##  END EVENT HANDLERS

    def get_albumart(self, audiofile):
        """
        Extract album art from a file, or look for a cover in its directory.
        Tries to fetch art from Last.fm if all else fails.

        Args:
            audiofile: string, path of the file containing the audio data

        Returns:
            raw image data
        """
        img_data = None

        ## Try to find album art in the media file
        try:
            if re.search(r'\.flac$', self.mpd_currentsong['file'], re.IGNORECASE):
                a = FLAC(audiofile)
                if len(a.pictures):
                    img_data = a.pictures[0].data
            elif re.search(r'\.m4a$', self.mpd_currentsong['file'], re.IGNORECASE):
                a = MP4(audiofile)
                if 'covr' in a.tags:
                    if len(a.tags['covr']):
                        img_data = a.tags['covr'][0]
            else:
                a = mutagen.File(audiofile)
                for k in a.keys():
                    if re.match(r'APIC:', k):
                        img_data = a[k].data
                        break
        except Exception as e:
            log.error("could not open audio file: %s" % e)

        ## Look for album art on the directory of the media file
        if not img_data:
            cover_path = ""
            song_dir = self.config.get("main", "music_dir") + "/" + os.path.dirname(self.mpd_currentsong['file'])
            try:
                for f in os.listdir(song_dir):
                    if re.match(r'cover\.(jpg|png|jpeg)', f, re.IGNORECASE):
                        cover_path = song_dir + "/" + f
                        break
                log.debug("looking for cover file: %s" % cover_path)
                if os.path.isfile(cover_path):
                    cf = open(cover_path, 'rb')
                    img_data = cf.read()
                    cf.close()
            except Exception as e:
                log.error("error reading cover file: %s" % e)
        return img_data

    def set_current_albumart(self):
        """
        Load and display image of current song if it has changed since the last time this function was run, or on the first run.
        Loads image data into a PIL.Image object, then into a GdkPixbuf object, then into a Gtk.Image object for display.
        """
        if not self.mpd_currentsong or not 'file' in self.mpd_currentsong.keys():
            return

        audiofile = self.config.get("main", "music_dir") + "/" + self.mpd_currentsong['file']
        if self.last_audiofile != audiofile:
            ## The file has changed since the last update, get the new album art.
            log.debug("new cover file, updating")
            img_data = self.get_albumart(audiofile)
            if img_data:
                ## Album art retrieved, load it into a pixbuf
                img = Image.open(io.BytesIO(img_data))
                img_bytes = GLib.Bytes.new(img.tobytes())
                log.debug("image size: %d x %d" % img.size)
                w, h = img.size
                if img.has_transparency_data:
                    self.current_albumart_pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(img_bytes, GdkPixbuf.Colorspace.RGB,
                                                                                   True, 8, w, h, w * 4)
                else:
                    self.current_albumart_pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(img_bytes, GdkPixbuf.Colorspace.RGB,
                                                                                   False, 8, w, h, w * 3)
            else:
                ## No album art, clear the image in the UI.
                self.current_albumart.clear()
                self.last_audiofile = audiofile
                return

        if self.last_audiofile != audiofile or self.resize_event_on:
            ## Update the image
            if self.current_albumart_pixbuf:
                self.current_albumart.set_pixbuf(self.current_albumart_pixbuf)
            else:
                log.debug("could not get pixbuf, clearing album art")
                self.current_albumart.clear()
        self.last_audiofile = audiofile

    def get_playlist(self):
        """
        Query for playlist. Clean up data before returning.

        Returns:
            list of filenames
        """
        error = False
        try:
            plist = self.app.mpd_cmd.playlistinfo()
            #log.debug("playlist: %s" % plist)
        except (musicpd.ConnectionError, BrokenPipeError) as e:
            log.error("could not fetch playlist: %s" % e)
            error = True
        if error:
            self.app.mpd_connect()
            return None
        #return plist
        playlist = []
        for song in plist:
            #log.debug("file_info: %s" % song)
            playlist.append(song)
        return playlist

    def update_playlist(self):
        """
        Updates playlist display. Makes MPD call for the playlist.
        Clears the current playlist. Adds song titles to the listbox.
        """
        self.playlist_list.remove_all()
        playlist = self.get_playlist()
        #log.debug("playlist: %s" % playlist)
        if not playlist:
            return

        ## Add songs to the list
        for song in playlist:
            log.debug("adding song to playlist: %s" % song['title'])
            label_text = ""
            if 'track' in song and 'time' in song and 'title' in song:
                label_text = re.sub(r'/.*', '', html.escape(song['track'])) + " (" + html.escape(
                    pp_time(song['time'])) + ") <b>" + html.escape(song['title']) + "</b>"
            else:
                label_text = os.path.basename(song['file'])
            label = MetadataLabel()
            label.set_markup(label_text)
            label.set_metatype('song')
            label.set_metadata(song)
            label.set_halign(Gtk.Align.START)
            self.playlist_list.append(label)

        if self.playlist_last_selected != None:
            self.playlist_list.select_row(self.playlist_list.get_row_at_index(self.playlist_last_selected))

        if self.focus_on == "playlist" and self.playlist_list.get_row_at_index(self.playlist_last_selected):
            self.playlist_list.get_row_at_index(self.playlist_last_selected).grab_focus()

        if 'pos' in self.mpd_currentsong:
            self.playlist_list.get_row_at_index(int(self.mpd_currentsong['pos'])).set_name("current")
        log.debug("playlist refresh complete")

    def add_to_playlist(self):
        """
        Displays confirmation dialog, presenting options to add, replace or cancel.
        """
        self.browser_selected_items = self.browser_box.get_selected_rows()
        #log.debug("selected items: %s" % selected_items)
        if not self.browser_selected_items[-1]['type'] in ("album", "song", "file"):
            return
        add_item_name = ""
        for i in range(1, len(self.browser_selected_items)):
            if self.browser_selected_items[i]['type'] == "song":
                add_item_name += self.browser_selected_items[i]['data']['title'] + " "
            else:
                add_item_name += self.browser_selected_items[i]['value'] + " "

        self.playlist_confirm_dialog = PlaylistConfirmDialog(self, add_item_name)

    def edit_playlist(self):
        """
        Displays dialog with playlist edit options. Performs task based on user input.
        Play, move song up in playlist, down in playlist, delete from playlist.
        """
        #index = self.playlist_list.get_selected_row().get_index()
        song = self.playlist_list.get_selected_row().get_child().data
        #log.debug("selected song: %s" % song)

        self.edit_playlist_dialog = Gtk.Dialog(title="Edit playlist", parent=self)
        self.edit_playlist_dialog.set_transient_for(self)
        self.edit_playlist_dialog.set_modal(True)
        for button_tuple in (("Play", 4), ("Up", 1), ("Down", 2), ("Delete", 3), ("Cancel", 0)):
            self.edit_playlist_dialog.add_button(button_tuple[0], button_tuple[1])
        if 'title' in song:
            self.edit_playlist_dialog.get_content_area().append(Gtk.Label(label="Edit: " + song['title']))
        else:
            self.edit_playlist_dialog.get_content_area().append(Gtk.Label(label="Edit: " + song['file']))
        self.edit_playlist_dialog.get_content_area().set_size_request(300, 100)
        #style_context = self.edit_playlist_dialog.get_style_context()
        #style_context.add_provider(self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.edit_playlist_dialog.connect('response', self.edit_playlist_response)
        self.edit_playlist_dialog.show();

    def playlist_info_popup(self):
        """
        Call SongInfoDialog to display the song data from the selected playlist row
        """
        song = self.playlist_list.get_selected_row().get_child().data
        if song is None:
            return
        log.debug("song info: %s" % song)
        dialog = SongInfoDialog(self, song)
        #dialog.run()
        #dialog.destroy()

    def browser_info_popup(self):
        """
        Call SongInfoDialog to display the song data from the selected browser row
        """
        song = self.browser_box.get_selected_rows()[-1]['data']
        if song is None:
            return
        log.debug("song info: %s" % song)
        dialog = SongInfoDialog(self, song)
        #dialog.run()
        #dialog.destroy()

    def outputs_changed(self, button, outputid):
        """
        Callback function passed to OutputsDialog.
        Expects the output ID, enables or disables the output based on the button's state.

        Args:
            button: Gtk.Button, event source
            outputid: output ID from the button

        """
        #log.debug("outputid: %s, %s" % (outputid, button.get_active()))
        error = False
        try:
            if button.get_active():
                self.app.mpd_cmd.enableoutput(outputid)
            else:
                self.app.mpd_cmd.disableoutput(outputid)
            self.app.mpd_outputs = self.app.mpd_cmd.outputs()
        except (musicpd.ConnectionError, BrokenPipeError) as e:
            log.info("previous mpd command failed: %s" % e)
            error = True
        if error:
            self.app.mpd_connect()

    def options_changed(self, button, option):
        """
        Callback function passed to OptionsDialog.
        Sets/unsets options based on input.

        Args:
            button: Gtk.Button, event source
            option: name of the option to change
        """
        error = False
        try:
            if option == "consume":
                self.app.mpd_cmd.consume(int(button.get_active()))
            elif option == "random":
                self.app.mpd_cmd.random(int(button.get_active()))
            elif option == "repeat":
                self.app.mpd_cmd.repeat(int(button.get_active()))
            elif option == "single":
                self.app.mpd_cmd.single(int(button.get_active()))
            else:
                log.info("unhandled option: %s" % option)
        except (musicpd.ConnectionError, BrokenPipeError) as e:
            log.info("previous mpd command failed: %s" % e)
            error = True
        if error:
            self.app.mpd_connect()

    def soundcard_changed(self, button, change):
        """
        """
        log.debug("changing sound card: %s = %s" % (change, button.get_value_as_int()))
        if change == "card_id":
            self.card_id = button.get_value_as_int()
        elif change == "device_id":
            self.device_id = button.get_value_as_int()
        self.update_playback()

    def playlist_moveup(self):
        index = self.playlist_list.get_selected_row().get_index()
        song = self.playlist_list.get_selected_row().get_child().data
        log.debug("moving song up 1: '%s'" % song['title'])
        if index > 0:
            try:
                index -= 1
                self.app.mpd_cmd.moveid(song['id'], index)
            except (musicpd.ConnectionError, BrokenPipeError) as e:
                log.error("could not move song up: %s" % e)
                self.mpd_connect()
                return None
            except Exception as e:
                log.error("unknown error could not move song up: %s" % e)
                return None
        self.playlist_last_selected = index
        self.focus_on = "playlist"

    def playlist_movedown(self):
        index = self.playlist_list.get_selected_row().get_index()
        song = self.playlist_list.get_selected_row().get_child().data
        log.debug("moving song down 1: '%s'" % song['title'])
        if index + 1 < len(self.playlist_list.get_children()):
            try:
                self.app.mpd_cmd.moveid(song['id'], index + 1)
            except (musicpd.ConnectionError, BrokenPipeError) as e:
                log.error("could not move song down: %s" % e)
                self.app.mpd_connect()
                return None
            except Exception as e:
                log.error("unknown error could not move song down: %s" % e)
                return None
        self.playlist_last_selected = index+1
        self.focus_on = "playlist"

    def playlist_delete(self):
        index = self.playlist_list.get_selected_row().get_index()
        song = self.playlist_list.get_selected_row().get_child().data
        log.debug("deleting song: '%s'" % song['title'])
        try:
            index -= 1
            if index < 0:
                index = 0
            self.app.mpd_cmd.deleteid(song['id'])
        except (musicpd.ConnectionError, BrokenPipeError) as e:
            log.error("could not delete song: %s" % e)
            self.app.mpd_connect()
        except Exception as e:
            log.error("unknown error could not delete song: %s" % e)
            return None
        self.playlist_last_selected = index
        self.focus_on = "playlist"

    ## New methods
    def playlist_dialog_response(self, dialog, response):
        log.debug("dialog response: %s" % response)
        dialog.destroy()

        error = False
        try:
            if response == 2:
                ## Clear list before adding for "replace"
                self.app.mpd_cmd.clear()

            if response in (1, 2):
                if self.browser_selected_items[-1]['type'] in ("song", "file"):
                    #log.debug("adding song: %s" % selected_items[-1]['data']['title'])
                    self.app.mpd_cmd.add(self.browser_selected_items[-1]['data']['file'])
                elif self.browser_selected_items[-1]['type'] == "album":
                    #log.debug("adding album: %s" % selected_items[-1]['value'])
                    if self.browser_selected_items[-2]['type'] == "artist":
                        self.app.mpd_cmd.findadd("artist", self.browser_selected_items[-2]['value'], "album", self.browser_selected_items[-1]['value'])
                    elif self.browser_selected_items[-2]['type'] == "albumartist":
                        self.app.mpd_cmd.findadd("albumartist", self.browser_selected_items[-2]['value'], "album",
                                         self.browser_selected_items[-1]['value'])
                    elif self.browser_selected_items[-2]['type'] == "genre":
                        self.app.mpd_cmd.findadd("genre", self.browser_selected_items[-2]['value'], "album", self.browser_selected_items[-1]['value'])


        except (musicpd.ConnectionError, BrokenPipeError) as e:
            log.error("adding to playlist: %s" % e)
            error = True
        if error:
            self.mpd_connect()

    def on_mainpaned_show(self, widget, user_data):
        log.debug("showed mainpaned, height: %d, %s" % (self.get_height(), user_data))
        if self.get_height():
            self.mainpaned.set_position(self.get_height()/2)
        else:
            self.mainpaned.set_position(self.props.default_height / 2)

    def on_state_flags_changed(self, widget=None, flags=None):
        #log.debug("state flags: %s" % flags)
        if not self.initial_resized and (flags & Gtk.StateFlags.FOCUS_WITHIN):
            self.set_dividers()
            self.initial_resized = True

    def set_dividers(self):
        log.debug("setting dividers")
        if self.get_height():
            self.mainpaned.set_position(self.get_height()/2)
        else:
            self.mainpaned.set_position(self.props.default_height/2)
        if self.get_width():
            self.bottompaned.set_position(self.get_width()/2)
        else:
            self.bottompaned.set_position(self.props.default_width/2)
        #self.set_current_albumart()

    def edit_playlist_response(self, dialog, response):
        if response == 1:
            self.playlist_moveup()
        elif response == 2:
            self.playlist_movedown()
        elif response == 3:
            dialog.destroy()
            self.playlist_delete()
        elif response == 4:
            song = self.playlist_list.get_selected_row().get_child().data
            self.app.mpd_cmd.playid(song['id'])
            dialog.destroy()
