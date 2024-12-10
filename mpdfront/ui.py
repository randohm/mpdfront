import configparser
import re, os, html, io, inspect
import logging
from PIL import Image
import mutagen
from mutagen.id3 import ID3, APIC
from mutagen.flac import FLAC
from mutagen.dsf import DSF
from mutagen.mp4 import MP4
import gi
from . import data
from .constants import Constants

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GObject, Pango, GLib, Gio

log = logging.getLogger(__name__)

def listbox_cmp(row1, row2, data, notify_destroy):
    """
    Compare function for Gtk.ListBox sorting. Does a simple string cmp on the rows' text
    Args:
        Standard args for Gtk.ListBox sort compare function.
    """
    return row1.get_child().get_text() > row2.get_child().get_text()

def listbox_cmp_by_track(row1, row2, data, notify_destroy):
    """
    Compare function for Gtk.ListBox sorting. Modifies the text before comparison.
    Args:
        Standard args for Gtk.ListBox sort compare function.
    """
    if not ('track' in row1.get_child().metadata['track'] and 'track' in row2.get_child().metadata['track']):
        return 0
    row1_value = int(row1.get_child().metadata['track'])
    row2_value = int(row2.get_child().metadata['track'])

    return row1_value > row2_value

def pp_time(secs):
    """
    Pretty-print time convenience function. Takes a count of seconds and formats to MM:SS.
    :param secs: int of number of seconds
    :return: string with the time in the format of MM:SS
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
    Display dialog to select sound card and device IDs. This is for displaying DAC stats.
    It is not associated to the outputs configured in MPD.
    Button click events are handled by a callback function passed to __init__.
    """

    def __init__(self, parent, button_pressed_callback, *args, **kwargs):
        """
        :param parent: parent window
        :param button_pressed_callback: callback function handling spinbutton change events. callback accepts +1 args for the type of change.
        :param args: args for super's constructor
        :param kwargs: args for super's constructor
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
    Display dialog with list of outputs as individual CheckButtons. These are outputs defined in MPD.
    Button click events are handled by a callback function passed to __init__.
    """

    def __init__(self, parent, button_pressed_callback, *args, **kwargs):
        """
        :param parent: parent window
        :param button_pressed_callback: callback function handling checkbutton click events. callback accepts 1 arg with the output ID.
        :param args: args for super's constructor
        :param kwargs: args for super's constructor
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
    def __init__(self, parent, button_pressed_callback, mpd_status, *args, **kwargs):
        """
        :param parent: parent window
        :param button_pressed_callback: callback function handling checkbutton click events. callback accepts 1 arg with the option name.
        :param args: args for super's constructor
        :param kwargs: args for super's constructor
        """
        super().__init__(title="Set Options", parent=parent, *args, **kwargs)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.add_button("Close", 0)
        self.set_name("options-dialog")
        self.get_content_area().set_size_request(300, 200)

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
    def __init__(self, parent, add_item_name, *args, **kwargs):
        super().__init__(title="Update playlist?", parent=parent, *args, **kwargs)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.add_button("Add", 1)
        self.add_button("Replace", 2)
        self.add_button("Cancel", 3)
        self.get_content_area().append(Gtk.Label(label="Selected: " + add_item_name))
        self.get_content_area().set_size_request(300, 100)

class PlaylistEditDialog(Gtk.Dialog):
    def __init__(self, parent, song, *args, **kwargs):
        super().__init__(title="Edit playlist", parent=parent, *args, **kwargs)
        self.set_transient_for(parent)
        self.set_modal(True)

        for button_tuple in (("Play", 4), ("Up", 1), ("Down", 2), ("Delete", 3), ("Cancel", 0)):
            self.add_button(button_tuple[0], button_tuple[1])
        if 'title' in song:
            self.get_content_area().append(Gtk.Label(label="Edit: " + song['title']))
        else:
            self.get_content_area().append(Gtk.Label(label="Edit: " + song['file']))
        self.get_content_area().set_size_request(300, 100)

class ContentTreeLabel(Gtk.Label):
    def __init__(self, node:data.ContentTreeNode=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if node:
            self._node = node

    def set_node(self, node:data.ContentTreeNode):
        self._node = node

    def get_node(self):
        return self._node

class IndexedListBox(Gtk.ListBox):
    """
    Gtk.ListBox with an index variable. This allows ListBoxes to track their position in list of ListBoxes.
    """
    def set_index(self, index):
        """
        Sets the index of the ListBox
        :param index:  int, the ListBox's position in the parent's list
        """
        self._index = index

    def get_index(self):
        return self._index

class ColumnBrowser(Gtk.Box):
    """
    Column browser for a tree data structure. Inherits from GtkBox.
    Creates columns with a list of GtkScrolledWindows containing a GtkListBox.
    """
    def __init__(self, parent:Gtk.Window, app:Gtk.Application, content_tree:Gio.ListStore, cols=2, spacing=0, hexpand=True, vexpand=True, *args, **kwargs):
        """
        Constructor for the column browser.
        :param parent: parent object
        :param app: main application object
        :param cols: int for number of colums
        :param hexpand: boolean for whether to set horizontal expansion
        :param vexpand: boolean for whether to set vertical expansion
        :param args: args for super's constructor
        :param kwargs: args for super's constructor
        """
        assert cols > 1, "Number of columns (cols) must be greater than 1"
        super().__init__(*args, **kwargs)
        self.parent = parent
        self.app = app
        self.content_tree = content_tree
        self.previous_selected = None
        self.set_spacing(spacing)
        self.num_columns = cols
        self.columns = []
        ## Initialize the columns
        for i in range(0, cols):
            scroll = Gtk.ScrolledWindow()
            listbox = IndexedListBox()
            listbox.set_hexpand(hexpand)
            listbox.set_vexpand(vexpand)
            listbox.set_index(i)
            listbox.connect("row-selected", self.on_row_selected)
            #listbox.connect("row-activated", self.on_row_activated)
            scroll.set_child(listbox)
            self.append(scroll)
            self.columns.append(listbox)
        ## Initialize data in 1st column
        self.columns[0].bind_model(model=content_tree, create_widget_func=self.create_list_label)

        self.controller = Gtk.EventControllerKey.new()
        self.controller.connect('key-pressed', self.on_key_pressed)
        self.add_controller(self.controller)

    def get_selected_rows(self):
        """
        Gets the child objects of all selected rows.
        Inserting them into a list in order from least to highest column index.
        :return: list of selected rows' child objects.
        """
        log.debug("looking for selected row")
        ret = []
        for c in self.columns:
            row = c.get_selected_row()
            if row:
                child = row.get_child()
                ret.append(child.get_node())
        return ret

    def create_list_label(self, node):
        label = ContentTreeLabel(label=node.get_metaname(), node=node)
        label.set_halign(Gtk.Align.START)
        label.set_valign(Gtk.Align.START)
        #log.debug("returning label for: %s" % label.get_label())
        return label

    def on_key_pressed(self, controller, keyval, keycode, state):
        """
        Keypress handler for toplevel widget. Responds to global keys for playback control.
        """
        #ctrl_pressed = state & Gdk.ModifierType.CONTROL_MASK
        #cmd_pressed = state & Gdk.ModifierType.META_MASK   ## Cmd
        #shift_pressed = state & Gdk.ModifierType.SHIFT_MASK
        #alt_pressed = state & Gdk.ModifierType.ALT_MASK

        try:
            #log.debug("Key pressed: %x" % keyval)
            if keyval == Gdk.KEY_Return:
                self.parent.add_to_playlist()
        except Exception as e:
            log.error("error on keypress (%s): %s" % (type(e).__name__, e))

    def on_row_selected(self, listbox, row):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        log.debug("row selected args: %s, %s" % (listbox, row))
        if not row:
            log.debug("row is None")
            return
        label = row.get_child()
        if not label:
            log.error("label is None")
            return
        node = label.get_node()
        if not node:
            log.error("node is None")
            return
        log.debug("row selected: %s %s" % (node.get_metatype(), node.get_metadata()))
        ## clear out all columns to the right
        for i in range(listbox.get_index()+1, self.num_columns):
            self.columns[i].bind_model(model=None, create_widget_func=None)
        ## load and show the next column to the right based on the current column
        self.app.load_content_data(node=node)
        if node.get_metatype() not in (Constants.label_t_song, Constants.label_t_file) and listbox.get_index() < self.num_columns-1:
            self.columns[listbox.get_index()+1].bind_model(model=node.get_child_layer(), create_widget_func=self.create_list_label)

    def on_row_activated(self, listbox, listboxrow):
        try:
            label = listboxrow.get_child()
            if label.get_metatype() in ('song', 'album'):
                self.parent.add_to_playlist()
        except Exception as e:
            log.error("error on row_activated (%s): %s" % (type(e).__name__, e))

class PlaybackDisplay(Gtk.Box):
    def __init__(self, parent:Gtk.Window, app:Gtk.Application, sound_card:int=None, sound_device:int=None, *args, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, *args, **kwargs)
        self.parent = parent
        self.app = app
        self.sound_card = sound_card
        self.sound_device = sound_device
        self.set_name("playback-display")

        self.song_display_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.song_display_box.set_hexpand(True)
        self.song_display_box.set_vexpand(True)
        self.playback_info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.playback_info_box.set_hexpand(False)
        self.playback_info_box.set_vexpand(False)
        self.song_display_box.append(self.playback_info_box)

        ## Current album art
        self.current_albumart = Gtk.Picture()
        self.current_albumart.set_valign(Gtk.Align.END)
        self.current_albumart.set_halign(Gtk.Align.END)
        self.current_albumart.set_vexpand(True)
        self.current_albumart.set_hexpand(True)
        self.song_display_box.append(self.current_albumart)
        self.append(self.song_display_box)

        # song title label
        self.current_title_label = Gtk.Label(label=" ")
        self.current_title_label.set_name("current-title")
        self.current_title_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.current_title_label.set_halign(Gtk.Align.START)
        self.current_title_label.set_valign(Gtk.Align.START)
        self.current_title_label.set_wrap(True)
        self.current_title_label.set_hexpand(False)
        self.current_title_label.set_vexpand(False)
        self.current_title_label.set_justify(Gtk.Justification.LEFT)

        # artist label
        self.current_artist_label = Gtk.Label(label=" ")
        self.current_artist_label.set_name("current-artist")
        self.current_artist_label.set_halign(Gtk.Align.START)
        self.current_artist_label.set_valign(Gtk.Align.START)
        self.current_artist_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.current_artist_label.set_wrap(False)
        self.current_artist_label.set_hexpand(False)
        self.current_artist_label.set_vexpand(False)
        self.current_artist_label.set_justify(Gtk.Justification.LEFT)

        # album label
        self.current_album_label = Gtk.Label(label=" ")
        self.current_album_label.set_name("current-album")
        self.current_album_label.set_halign(Gtk.Align.START)
        self.current_album_label.set_valign(Gtk.Align.START)
        self.current_album_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.current_album_label.set_wrap(False)
        self.current_album_label.set_hexpand(False)
        self.current_album_label.set_vexpand(False)
        self.current_album_label.set_justify(Gtk.Justification.LEFT)

        # time label
        self.current_time_label = Gtk.Label(label=" ")
        self.current_time_label.set_name("current-time")
        self.current_time_label.set_halign(Gtk.Align.START)
        self.current_time_label.set_valign(Gtk.Align.END)
        self.current_time_label.set_wrap(False)
        self.current_time_label.set_hexpand(False)
        self.current_time_label.set_vexpand(False)
        self.current_time_label.set_justify(Gtk.Justification.LEFT)

        # stats1 label
        self.stats1_label = Gtk.Label(label=" ")
        self.stats1_label.set_name("stats1")
        self.stats1_label.set_halign(Gtk.Align.START)
        self.stats1_label.set_valign(Gtk.Align.END)
        self.stats1_label.set_wrap(True)
        self.stats1_label.set_hexpand(False)
        self.stats1_label.set_vexpand(False)
        self.stats1_label.set_justify(Gtk.Justification.LEFT)

        # stats2 label
        self.stats2_label = Gtk.Label(label=" ")
        self.stats2_label.set_name("stats2")
        self.stats2_label.set_halign(Gtk.Align.START)
        self.stats2_label.set_valign(Gtk.Align.END)
        self.stats2_label.set_wrap(True)
        self.stats2_label.set_hexpand(False)
        self.stats2_label.set_vexpand(False)
        self.stats2_label.set_justify(Gtk.Justification.LEFT)

        ## Add labels to playback grid
        self.playback_info_box.append(self.current_title_label)
        self.playback_info_box.append(self.current_artist_label)
        self.playback_info_box.append(self.current_album_label)
        self.playback_info_box.append(self.current_time_label)
        self.playback_info_box.append(self.stats1_label)
        self.playback_info_box.append(self.stats2_label)

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

    def update(self, mpd_status:dict, mpd_currentsong:dict, music_dir:str):
        if not mpd_status:
            log.error("mpd_status not defined: %s" % mpd_status)
            return
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
        if 'audio' in mpd_status:
            if re.match(r'dsd\d+:', mpd_status['audio']):
                bits = "dsd"
                freq, chs = re.split(r':', mpd_status['audio'], maxsplit=1)
            else:
                freq, bits, chs = re.split(r':', mpd_status['audio'], maxsplit=2)
        if 'bitrate' in mpd_status:
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
            self.stats2_label.set_markup("<small><b>src:</b></small> " + format_text + " @ " + bitrate + " kbps")

            ## Get and format DAC rate, format
            dac_freq = dac_bits = ""
            proc_file = Constants.proc_file_fmt % (self.sound_card, self.sound_device, "0")
            #proc_file = Constants.proc_file_fmt
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
            self.stats1_label.set_markup("<small><b>dac:</b></small> " + dac_text)
        else:
            self.stats1_label.set_text(" ")
            self.stats2_label.set_text(" ")

        ## Format and set time information and state
        if 'time' in mpd_status:
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

    def get_albumart(self, audiofile:dict, mpd_currentsong:dict):
        """
        Extract album art from a file, or look for a cover in its directory.
        Tries to fetch art from Last.fm if all else fails.
        :param audiofile: string, path of the file containing the audio data
        :return: raw image data
        """
        img_data = None

        ## Try to find album art in the media file
        if not os.path.isfile(audiofile):
            log.debug("audio file does not exist: %s" % audiofile)
        else:
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
                    for k in a:
                        if re.match(r'APIC:', k):
                            img_data = a[k].data
                            break
            except Exception as e:
                log.error("could not open audio file: %s" % e)

        ## Look for album art on the directory of the media file
        if not img_data:
            cover_path = ""
            song_dir = os.path.dirname(audiofile)
            if os.path.isdir(song_dir):
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
        else:
            log.debug("album art loaded from audio file")
        return img_data

    def set_current_albumart(self, mpd_currentsong:dict, music_dir:str):
        """
        Load and display image of current song if it has changed since the last time this function was run, or on the first run.
        Loads image data into a PIL.Image object, then into a GdkPixbuf object, then into a Gtk.Image object for display.
        """
        if not mpd_currentsong or not 'file' in mpd_currentsong:
            return

        audiofile = music_dir + "/" + mpd_currentsong['file']
        if not hasattr(self, 'last_audiofile') or self.last_audiofile != audiofile:
            ## The file has changed since the last update, get the new album art.
            log.debug("new cover file, updating")
            img_data = self.get_albumart(audiofile, mpd_currentsong)
            if img_data:
                ## Album art retrieved, load it into a pixbuf
                img = Image.open(io.BytesIO(img_data))
                img_bytes = GLib.Bytes.new(img.tobytes())
                log.debug("image size: %d x %d" % img.size)
                w, h = img.size
                try:
                    if img.has_transparency_data:
                        current_albumart_pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(img_bytes, GdkPixbuf.Colorspace.RGB,
                                                                                       True, 8, w, h, w * 4)
                    else:
                        current_albumart_pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(img_bytes, GdkPixbuf.Colorspace.RGB,
                                                                                       False, 8, w, h, w * 3)
                except Exception as e:
                    log.error("could not load image into pixbuf: %s" % e)
                    return
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
        self.app.mpd_previous()
        controller.reset()

    def rewind_clicked(self, controller, x, y, user_data):
        """
        Click handler for rewind button
        """
        self.app.mpd_seekcur(Constants.rewind_arg)
        controller.reset()

    def stop_clicked(self, controller, x, y, user_data):
        """
        Click handler for stop button
        """
        self.app.mpd_stop()
        controller.reset()

    def play_clicked(self, controller, x, y, user_data):
        """
        Click handler for play/pause button
        """
        self.app.mpd_toggle()
        controller.reset()

    def cue_clicked(self, controller, x, y, user_data):
        """
        Click handler for cue button
        """
        self.app.mpd_seekcur(Constants.cue_arg)
        controller.reset()

    def next_clicked(self, controller, x, y, user_data):
        """
        Click handler for next button
        """
        self.app.mpd_next()
        controller.reset()

class PlaylistDisplay(Gtk.ListBox):
    """
    Handles display and updates of the playlist. The listbox entries are controlled by a Gio.ListStore listmodel.
    """
    last_selected = 0  ## Points to last selected song in playlist

    def __init__(self, parent:Gtk.Window, app:Gtk.Application,  *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_name("playlistbox")
        self.liststore = Gio.ListStore()
        self.bind_model(model=self.liststore, create_widget_func=self.create_list_label)
        self.parent = parent
        self.app = app
        controller = Gtk.EventControllerKey.new()
        controller.connect("key-pressed", self.on_key_pressed)
        self.add_controller(controller)

    def update(self, playlist:dict, mpd_currentsong:dict):
        self.liststore.remove_all()
        if playlist:
            #log.debug("playlist: %s" % playlist)
            ## Add songs to the list
            for song in playlist:
                #log.debug("adding song to playlist: %s" % song['title'])
                self.liststore.append(data.ContentTreeNode(metadata=song))
            if self.last_selected != None:
                self.select_row(self.get_row_at_index(self.last_selected))
            if self.parent.focus_on == "playlist" and self.get_row_at_index(self.last_selected):
                self.get_row_at_index(self.last_selected).grab_focus()
            if 'pos' in mpd_currentsong:
                self.get_row_at_index(int(mpd_currentsong['pos'])).set_name("current-track")
            log.debug("playlist refresh complete")

    def create_list_label(self, node):
        if node.get_metadata('track') and node.get_metadata('time') and node.get_metadata('title'):
            label_text = re.sub(r'/.*', '', html.escape(node.get_metadata('track'))) + " (" + html.escape(
                pp_time(node.get_metadata('time'))) + ") <b>" + html.escape(node.get_metadata('title')) + "</b>"
        else:
            label_text = os.path.basename(node.get_metadata('file'))
        label = ContentTreeLabel(node=node)
        label.set_markup(label_text)
        label.set_halign(Gtk.Align.START)
        label.set_valign(Gtk.Align.START)
        return label

    def on_key_pressed(self, controller, keyval, keycode, state):
        """
        Event handler for playlist box key presses
        """
        if keyval == Gdk.KEY_Return:
            self.edit_popup()
        elif keyval == ord(self.parent.config.get("keys", "info")):
            self.info_popup()
        elif keyval == ord(self.parent.config.get("keys", "moveup")):
            self.track_moveup()
        elif keyval == ord(self.parent.config.get("keys", "movedown")):
            self.track_movedown()
        elif keyval == ord(self.parent.config.get("keys", "delete")) or keyval in (Gdk.KEY_Delete, Gdk.KEY_BackSpace):
            self.track_delete()

    def edit_popup(self):
        """
        Displays dialog with playlist edit options. Performs task based on user input.
        Play, move song up in playlist, down in playlist, delete from playlist.
        """
        song = self.get_selected_row().get_child().get_node().get_metadata()
        self.edit_playlist_dialog = PlaylistEditDialog(parent=self.parent, song=song)
        self.edit_playlist_dialog.connect('response', self.edit_response)
        self.edit_playlist_dialog.show()

    def edit_response(self, dialog, response):
        if response == 1:
            self.track_moveup()
        elif response == 2:
            self.track_movedown()
        elif response == 3:
            dialog.destroy()
            self.track_delete()
        elif response == 4:
            song = self.get_selected_row().get_child().get_node().get_metadata()
            self.parent.mpd_playid(song['id'])
            dialog.destroy()
        elif response == 0:
            dialog.destroy()

    def info_popup(self):
        """
        Call SongInfoDialog to display the song data from the selected playlist row
        """
        song = self.get_selected_row().get_child().get_node().get_metadata()
        if song is None:
            return
        log.debug("song info: %s" % song)
        dialog = SongInfoDialog(self.parent, song)

    def track_moveup(self):
        index = self.get_selected_row().get_index()
        song = self.get_selected_row().get_child().get_node().get_metadata()
        log.debug("moving song up 1: '%s'" % song['title'])
        if index > 0:
            index -= 1
            self.app.mpd_moveid(song['id'], index)
        self.last_selected = index
        self.focus_on = "playlist"

    def track_movedown(self):
        index = self.get_selected_row().get_index()
        song = self.get_selected_row().get_child().get_node().get_metadata()
        log.debug("moving song down 1: '%s'" % song['title'])
        if index + 1 < len(self.liststore):
            self.app.mpd_moveid(song['id'], index+1)
        self.last_selected = index+1
        self.focus_on = "playlist"

    def track_delete(self):
        index = self.get_selected_row().get_index()
        song = self.get_selected_row().get_child().get_node().get_metadata()
        log.debug("deleting song: '%s'" % song)
        index -= 1
        if index < 0:
            index = 0
        self.app.mpd_deleteid(song['id'])
        self.last_selected = index
        self.focus_on = "playlist"

class MpdFrontWindow(Gtk.Window):
    last_audiofile = ""         ## Tracks albumart for display
    browser_full = False        ## Tracks if the browser is fullscreen
    browser_hidden = False      ## Tracks if the browser is hidden
    bottom_full = False         ## Tracks if the bottom half of mainpained is fullscreen
    last_width = 0              ## Tracks width of window when window changes size
    last_height = 0             ## Tracks height of window when window changes size
    playlist_last_selected = 0  ## Points to last selected song in playlist
    focus_on = "broswer"        ## Either 'playlist' or 'browser'
    initial_resized = False

    def __init__(self, config:configparser, application:Gtk.ApplicationWindow, content_tree:Gio.ListStore, *args, **kwargs):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        super().__init__(application=application, *args, **kwargs)
        self.config = config
        self.app = application
        self.content_tree = content_tree
        self.set_default_size(int(config.get("main", "width")), int(config.get("main", "height")))
        self.set_resizable(False)
        self.set_decorated(False)

        self.controller = Gtk.EventControllerKey.new()
        self.controller.connect('key-pressed', self.on_key_pressed)
        self.add_controller(self.controller)

        ## mainpaned is the toplevel layout container
        self.mainpaned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        self.mainpaned.set_name("mainpaned")
        self.set_child(self.mainpaned)

        ## Setup browser columns
        self.browser_box = ColumnBrowser(parent=self, app=self.app, content_tree=self.content_tree,
                                         cols=Constants.browser_num_columnns, spacing=0, hexpand=True, vexpand=True)
        self.browser_box.set_name("browser")
        self.mainpaned.set_start_child(self.browser_box)

        ## Setup bottom half
        self.bottompaned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.mainpaned.set_end_child(self.bottompaned)

        self.playback_display = PlaybackDisplay(parent=self, app=self.app, sound_card=self.config.get("main", "sound_card"),
                                                sound_device=self.config.get("main", "sound_device"))
        self.bottompaned.set_start_child(self.playback_display)

        ## Setup playlist
        self.playlist_list = PlaylistDisplay(parent=self, app=self.app)
        self.playlist_scroll = Gtk.ScrolledWindow()
        self.playlist_scroll.set_name("playlistscroll")
        self.playlist_scroll.set_hexpand(True)
        self.playlist_scroll.set_child(self.playlist_list)
        self.bottompaned.set_end_child(self.playlist_scroll)

        ## Set event handlers
        self.connect("destroy", self.close)
        self.connect("state_flags_changed", self.on_state_flags_changed)

        if config.has_option("main", "fullscreen") and re.match(r'yes$', config.get("main", "fullscreen"), re.IGNORECASE):
            self.fullscreen()

        self.playlist_last_selected = 0
        self.playlist_list.select_row(self.playlist_list.get_row_at_index(self.playlist_last_selected))
        self.browser_box.columns[0].select_row(self.browser_box.columns[0].get_row_at_index(0))

        ## Setup callbacks for keypress events
        ## values of dicts are tuples with: function, args (optional)
        self.key_pressed_callbacks = {
            Gdk.KEY_VoidSymbol:         (lambda: True,),
            Gdk.KEY_Up:                 (log.debug, ("UP",)), #(lambda: True,),
            Gdk.KEY_Down:               (log.debug, ("DOWN",)), #(lambda: True,),
            Gdk.KEY_Right:              (log.debug, ("RIGHT",)), #(lambda: True,),
            Gdk.KEY_Left:               (log.debug, ("LEFT",)), #(lambda: True,),
            Gdk.KEY_Return:             (log.debug, ("RETURN",)), #(lambda: True,),
            Gdk.KEY_Escape:             (log.debug, ("ESC",)), #(lambda: True,),
            Gdk.KEY_AudioPlay:          (self.app.mpd_toggle,),
            Gdk.KEY_AudioStop:          (self.app.mpd_stop,),
            Gdk.KEY_AudioPrev:          (self.app.mpd_previous,),
            Gdk.KEY_AudioNext:          (self.app.mpd_next,),
            Gdk.KEY_v:                  (self.set_dividers,),
            Gdk.KEY_q:                  (log.debug, ("pressed q",)),
            Gdk.KEY_b:                  (data.dump, (self.content_tree,)),
        }
        ## callbacks for meta mod key
        self.key_pressed_callbacks_mod_meta = {
            Gdk.KEY_q:                  (self.close,),
        }
        ## callbacks for ctrl mod key
        self.key_pressed_callbacks_mod_ctrl = {
            Gdk.KEY_q:                  (self.close,),
        }
        ## keys defined in config file
        self.key_pressed_callback_config_tuples = {
            ("keys", "playpause"):      (self.app.mpd_toggle,),
            ("keys", "stop"):           (self.app.mpd_stop,),
            ("keys", "previous"):       (self.app.mpd_previous,),
            ("keys", "next"):           (self.app.mpd_next,),
            ("keys", "rewind"):         (self.app.mpd_seekcur, (Constants.rewind_arg,)),
            ("keys", "cue"):            (self.app.mpd_seekcur, (Constants.cue_arg,)),
            ("keys", "outputs"):        (self.event_outputs_dialog,),
            ("keys", "options"):        (self.event_options_dialog,),
            ("keys", "cardselect"):     (self.event_cardselect_dialog,),
            ("keys", "browser"):        (self.event_focus_browser,),
            ("keys", "playlist"):       (self.event_focus_playlist,),
            ("keys", "full_browser"):   (self.event_full_browser,),
            ("keys", "full_bottom"):    (self.event_full_bottom,),
            ("keys", "full_playback"):  (self.event_full_playback,),
            ("keys", "full_playlist"):  (self.event_full_playlist,),
        }
        ## add keys defined in config file
        for k in self.key_pressed_callback_config_tuples:
            log.debug("callback key:%s, value:%s" % (k, self.key_pressed_callback_config_tuples.get(k)))
            if config.has_option(*k):
                log.debug("option exists")
                self.key_pressed_callbacks[ord(config.get(*k))] = self.key_pressed_callback_config_tuples[k]
        log.debug("keypress callbacks: %s" % self.key_pressed_callbacks)

    def on_key_pressed(self, controller, keyval, keycode, state):
        """
        Keypress handler for toplevel widget. Responds to global keys for playback control.
        """
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        ctrl_pressed = state & Gdk.ModifierType.CONTROL_MASK
        meta_pressed = state & Gdk.ModifierType.META_MASK   ## Cmd
        #shift_pressed = state & Gdk.ModifierType.SHIFT_MASK
        #alt_pressed = state & Gdk.ModifierType.ALT_MASK

        ## Attempt to run the pre-defined callback.
        log.debug("Key pressed: 0x%x, 0x%x" % (keyval, keycode))
        try:
            tup = None
            if meta_pressed:
                log.debug("meta modifier pressed")
                tup = self.key_pressed_callbacks_mod_meta.get(keyval)
            elif ctrl_pressed:
                log.debug("ctrl meta modifier pressed")
                tup = self.key_pressed_callbacks_mod_meta.get(keyval)
            else:
                tup = self.key_pressed_callbacks.get(keyval)
            if tup:
                callback = tup[0]
                cb_args = None
                if len(tup) >= 2:
                    cb_args = tup[1]
                if callback:
                    log.debug("calling : %s" % callback)
                    log.debug("with args: %s" % (cb_args,))
                    if cb_args and isinstance(cb_args, tuple) and len(cb_args):
                        log.debug("calling with args")
                        callback(*cb_args)
                    else:
                        log.debug("calling with no args")
                        callback()
            else:
                log.debug("no action defined for keyval: 0x%x" % keyval)
        except KeyError as e:
            log.debug("KeyError on callback: %s" % (e))
        except Exception as e:
            log.error("could not call callback: %s %s" % (type(e), e))

    def event_outputs_dialog(self):
        self.outputs_dialog = OutputsDialog(self, self.outputs_changed)

    def event_options_dialog(self):
        mpd_status = self.app.mpd_status()
        self.options_dialog = OptionsDialog(self, self.options_changed, mpd_status)

    def event_cardselect_dialog(self):
        self.cards_dialog = CardSelectDialog(self, self.soundcard_changed)

    def event_focus_browser(self):
        ## Focus on the last selected row in the browser
        self.focus_on = "broswer"
        selected_items = self.browser_box.get_selected_rows()
        if not len(selected_items):
            self.browser_box.columns[0].select_row(self.browser_box.columns[0].get_row_at_index(0))
            selected_items = self.browser_box.get_selected_rows()
        focus_col = self.browser_box.columns[len(selected_items) - 1]
        focus_row = focus_col.get_selected_row()
        focus_row.grab_focus()

    def event_focus_playlist(self):
        ## Focus on the selected row in the playlist
        self.focus_on = "playlist"
        selected_row = self.playlist_list.get_selected_row()
        if not selected_row:
            selected_row = self.playlist_list.get_row_at_index(0)
            self.playlist_list.select_row(selected_row)
        selected_row.grab_focus()

    def event_full_browser(self):
        log = logging.getLogger(__name__ + "." + self.__class__.__name__ + "." + inspect.stack()[0].function)
        height = self.get_height()
        position = self.mainpaned.get_position()
        if position > (height-5):
            log.debug("setting browser to split screen")
            self.mainpaned.set_position(height/2)
        else:
            log.debug("setting browser to full screen")
            self.mainpaned.set_position(height)

    def event_full_bottom(self):
        log = logging.getLogger(__name__ + "." + self.__class__.__name__ + "." + inspect.stack()[0].function)
        height = self.get_height()
        position = self.mainpaned.get_position()
        log.debug("position: %d, height: %d" % (position, height))
        if position < 5:
            log.debug("setting bottom to split screen")
            self.mainpaned.set_position(height/2)
        else:
            log.debug("setting bottom to full screen")
            self.mainpaned.set_position(0)

    def event_full_playback(self):
        log = logging.getLogger(__name__ + "." + self.__class__.__name__ + "." + inspect.stack()[0].function)
        width = self.get_width()
        position = self.bottompaned.get_position()
        log.debug("position: %d, width: %d" % (position, width))
        ## old
        if position > (width-5):
            self.bottompaned.set_position(width/2)
        else:
            self.bottompaned.set_position(width)

    def event_full_playlist(self):
        log = logging.getLogger(__name__ + "." + self.__class__.__name__ + "." + inspect.stack()[0].function)
        width = self.get_width()
        position = self.bottompaned.get_position()
        log.debug("position: %d, width: %d" % (position, width))
        if position < 5:
            self.bottompaned.set_position(width/2)
        else:
            self.bottompaned.set_position(0)

    def add_to_playlist(self):
        """
        Displays confirmation dialog, presenting options to add, replace or cancel.
        """
        self.browser_selected_items = self.browser_box.get_selected_rows()
        log.debug("selected items: %s" % self.browser_selected_items)
        if not self.browser_selected_items[-1].get_metatype() in (Constants.label_t_song, Constants.label_t_album, Constants.label_t_file):
            return
        add_item_name = ""
        for i in range(1, len(self.browser_selected_items)):
            log.debug("confirming add item: %s" % self.browser_selected_items[i].get_metaname())
            if self.browser_selected_items[i].get_metatype() == Constants.label_t_song:
                add_item_name += self.browser_selected_items[i].get_metadata('title') + " "
            else:
                add_item_name += self.browser_selected_items[i].get_metaname() + " "
        log.debug("confirming add item: %s" % add_item_name)
        self.playlist_confirm_dialog = PlaylistConfirmDialog(parent=self, add_item_name=add_item_name)
        self.playlist_confirm_dialog.connect('response', self.playlist_confirm_dialog_response)
        self.playlist_confirm_dialog.show()

    def browser_info_popup(self):
        """
        Call SongInfoDialog to display the song data from the selected browser row
        """
        song = self.browser_box.get_selected_rows()[-1]['data']
        if song is None:
            return
        log.debug("song info: %s" % song)
        dialog = SongInfoDialog(self, song)

    def outputs_changed(self, button, outputid):
        """
        Callback function passed to OutputsDialog. Expects the output ID, enables or disables the output based
        on the button's state.
        :param button: Gtk.Button, event source
        :param outputid: output ID from the button
        """
        if button.get_active():
            self.app.mpd_enableoutput.enableoutput(outputid)
        else:
            self.app.mpd_disableoutput(outputid)
        self.app.mpd_outputs = self.app.get_mpd_outputs()

    def options_changed(self, button, option):
        """
        Callback function passed to OptionsDialog. Sets/unsets options based on input.
        :param button: Gtk.Button, event source
        :param option: name of the option to change
        """
        if option == "consume":
            self.app.mpd_consume(int(button.get_active()))
        elif option == "random":
            self.app.mpd_random(int(button.get_active()))
        elif option == "repeat":
            self.app.mpd_repeat(int(button.get_active()))
        elif option == "single":
            self.app.mpd_single(int(button.get_active()))
        else:
            log.info("unhandled option: %s" % option)

    def soundcard_changed(self, button, change):
        log.debug("changing sound card: %s = %s" % (change, button.get_value_as_int()))
        if change == "card_id":
            self.card_id = button.get_value_as_int()
        elif change == "device_id":
            self.device_id = button.get_value_as_int()

    def playlist_confirm_dialog_response(self, dialog, response):
        log = logging.getLogger(__name__ + "." + self.__class__.__name__ + "." + inspect.stack()[0].function)
        log.debug("dialog response: %s" % response)
        dialog.destroy()
        if response == 2:
            ## Clear list before adding for "replace"
            self.app.mpd_clear()
        if response in (1, 2): ## Add or replace
            if self.browser_selected_items[-1].get_metatype() in (Constants.label_t_song, Constants.label_t_file):
                log.debug("adding song: %s" % self.browser_selected_items[-1].get_metadata())
                if self.browser_selected_items[-1].get_metatype() == Constants.label_t_song:
                    self.app.mpd_add(self.browser_selected_items[-1].get_metadata('file'))
                elif self.browser_selected_items[-1].get_metatype() == Constants.label_t_file:
                    self.app.mpd_add(self.browser_selected_items[-1].get_metadata('data')['file'])
                else:
                    log.error("unhandled type: %s" % self.browser_selected_items[-1].get_metatype())
            elif self.browser_selected_items[-1].get_metatype() == Constants.label_t_album:
                log.debug("adding album: %s" % self.browser_selected_items[-1].get_metaname())
                if self.browser_selected_items[-2].get_metatype() == Constants.label_t_artist:
                    log.debug("adding album by artist: %s" % self.browser_selected_items[-2].get_metaname())
                    self.app.mpd_findadd("artist", self.browser_selected_items[-2].get_metatype(), "album",
                                         self.browser_selected_items[-1].get_metaname())
                elif self.browser_selected_items[-2].get_metatype() == Constants.label_t_albumartist:
                    log.debug("adding album by albumartist: %s" % self.browser_selected_items[-2].get_metaname())
                    self.app.mpd_findadd("albumartist", self.browser_selected_items[-2].get_metaname(), "album",
                                         self.browser_selected_items[-1].get_metaname())
                elif self.browser_selected_items[-2].get_metatype() == Constants.label_t_genre:
                    log.debug("adding album by genre: %s" % self.browser_selected_items[-2].get_metaname())
                    self.app.mpd_findadd("genre", self.browser_selected_items[-2].get_metaname(), "album",
                                         self.browser_selected_items[-1].get_metaname())
                else:
                    log.error("unhandled type 2: %s" % self.browser_selected_items[-2].get_metatype())
            else:
                log.error("unhandled type 1: %s" % self.browser_selected_items[-1].get_metatype())
        self.browser_selected_items = None

    def on_mainpaned_show(self, widget, user_data):
        log.debug("showed mainpaned, height: %d, %s" % (self.get_height(), user_data))
        if self.get_height():
            self.mainpaned.set_position(self.get_height()/2)
        else:
            self.mainpaned.set_position(self.props.default_height / 2)

    def on_state_flags_changed(self, widget, flags):
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
