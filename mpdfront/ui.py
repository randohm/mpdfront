import configparser
import re, os, html, inspect
import logging
import mutagen
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
import gi
from . import data
from .constants import Constants

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GObject, Pango, GLib, Gio

log = logging.getLogger(__name__)

def pp_time(secs):
    """
    Pretty-print time convenience function. Takes a count of seconds and formats to MM:SS.
    :param secs: int of number of seconds
    :return: string with the time in the format of MM:SS
    """
    return "%d:%02d" % (int(int(secs) / 60), int(secs) % 60)

def pp_file_format(format:str):
    s = format.split(':')
    rate = float(s[0])/1000
    return "%.1fkHz %s bits %s channels" % (rate, s[1], s[2])

class KeyPressedReceiver(Gtk.Widget):
    @property
    def key_pressed_callbacks(self):
        if not hasattr(self, '_key_pressed_callbacks'):
            return {}
        return self._key_pressed_callbacks
    @key_pressed_callbacks.setter
    def key_pressed_callbacks(self, callbacks:dict):
        self._key_pressed_callbacks = callbacks

    @property
    def key_pressed_callbacks_mod_meta(self):
        if not hasattr(self, '_key_pressed_callbacks_mod_meta'):
            return {}
        return self._key_pressed_callbacks_mod_meta
    @key_pressed_callbacks_mod_meta.setter
    def key_pressed_callbacks_mod_meta(self, callbacks:dict):
        self._key_pressed_callbacks_mod_meta = callbacks

    @property
    def key_pressed_callbacks_mod_ctrl(self):
        if not hasattr(self, '_key_pressed_callbacks_mod_ctrl'):
            return {}
        return self._key_pressed_callbacks_mod_ctrl
    @key_pressed_callbacks_mod_ctrl.setter
    def key_pressed_callbacks_mod_ctrl(self, callbacks:dict):
        self._key_pressed_callbacks_mod_ctrl = callbacks

    @property
    def key_pressed_callbacks_mod_alt(self):
        if not hasattr(self, '_key_pressed_callbacks_mod_alt'):
            return {}
        return self._key_pressed_callbacks_mod_alt
    @key_pressed_callbacks_mod_alt.setter
    def key_pressed_callbacks_mod_alt(self, callbacks:dict):
        self._key_pressed_callbacks_mod_alt = callbacks

    def set_key_pressed_controller(self):
        self.key_pressed_controller = Gtk.EventControllerKey.new()
        self.key_pressed_controller.connect('key-pressed', self.on_key_pressed)
        self.add_controller(self.key_pressed_controller)

    def on_key_pressed(self, controller, keyval, keycode, state):
        """
        Keypress handler for toplevel widget. Responds to global keys for playback control.
        """
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        ctrl_pressed = state & Gdk.ModifierType.CONTROL_MASK
        meta_pressed = state & Gdk.ModifierType.META_MASK   ## Cmd
        alt_pressed = state & Gdk.ModifierType.ALT_MASK
        shift_pressed = state & Gdk.ModifierType.SHIFT_MASK

        ## Attempt to run the pre-defined callback.
        log.debug("Key pressed: 0x%x, 0x%x" % (keyval, keycode))
        try:
            tup = None
            if meta_pressed:
                log.debug("meta modifier pressed")
                tup = self.key_pressed_callbacks_mod_meta.get(keyval)
            elif ctrl_pressed:
                log.debug("ctrl meta modifier pressed")
                tup = self.key_pressed_callbacks_mod_ctrl.get(keyval)
            elif alt_pressed:
                log.debug("alt meta modifier pressed")
                tup = self.key_pressed_callbacks_mod_alt.get(keyval)
            else:
                tup = self.key_pressed_callbacks.get(keyval)
            if tup and isinstance(tup, tuple):
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
            log.debug("KeyError on callback: %s" % e)
        except Exception as e:
            log.error("could not call callback (%s): %s" % (type(e).__name__, e))

    def add_config_keys(self, callbacks:dict, addition:dict, config:configparser):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        for k in addition:
            log.debug("callback key:%s, value:%s" % (k, addition.get(k)))
            if config.has_option(*k):
                log.debug("option exists")
                callbacks[ord(config.get(*k))] = addition[k]
        log.debug("keypress callbacks: %s" % callbacks)

class SongInfoDialog(Gtk.Window):
    def __init__(self, window:Gtk.Window, node:data.ContentTreeNode, *args, **kwargs):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        super().__init__(*args, **kwargs)
        self._builder = Gtk.Builder.new_from_file("songinfo.ui")
        if not self._builder:
            log.error("could not create builder")
            return
        main_box = self._builder.get_object('main-box')
        if not main_box:
            log.error("main_box is None")
            return
        self.set_child(main_box)
        self.set_transient_for(window)
        #self.set_size_request(600, 400)

        song = node.get_metadata()
        log.debug("song: %s" % song)
        if 'title' in song:
            self._builder.get_object('songtitle').set_label(song['title'])
        if 'artist' in song:
            self._builder.get_object('artist-label').set_label(song['artist'])
        if 'albumartist' in song:
            self._builder.get_object('albumartist-label').set_label(song['albumartist'])
        if 'album' in song:
            self._builder.get_object('album-label').set_label(song['album'])
        if 'time' in song:
            self._builder.get_object('time-label').set_label(pp_time(song['time']))
        if 'track' in song:
            self._builder.get_object('track-label').set_label(song['track'])
        if 'date' in song:
            self._builder.get_object('date-label').set_label(song['date'])
        if 'genre' in song:
            self._builder.get_object('genre-label').set_label(song['genre'])
        if 'composer' in song:
            self._builder.get_object('composer-label').set_label(song['composer'])
        if 'format' in song:
            self._builder.get_object('format-label').set_label(pp_file_format(song['format']))
        if 'file' in song:
            self._builder.get_object('file-label').set_label(song['file'])
        if 'disc' in song:
            self._builder.get_object('disc-label').set_label(song['disc'])

        button_click_ctrler = Gtk.GestureClick.new()
        button_click_ctrler.connect("pressed", self.close_clicked)
        self._builder.get_object('close-button').add_controller(button_click_ctrler)
        button_pressed_ctrler = Gtk.EventControllerKey.new()
        button_pressed_ctrler.connect("key-pressed", self.close_pressed)
        self._builder.get_object('close-button').add_controller(button_pressed_ctrler)

    def close_clicked(self, controller, x, y, user_data):
        self.close()

    def close_pressed(self, controller, keyval, keycode, state):
        if keyval in (Gdk.KEY_Return, Gdk.KEY_Escape):
            self.close()

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

    def on_response(self, dialog, response):
        self.destroy()

class PlaylistConfirmDialog(Gtk.Dialog):
    _button_text_add        = "Add"
    _button_text_replace    = "Replace"
    _button_text_cancel     = "Cancel"
    def __init__(self, parent, add_item:data.ContentTreeNode, *args, **kwargs):
        super().__init__(title="Update playlist?", *args, **kwargs)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.add_button(self._button_text_add, Constants.playlist_confirm_reponse_add)
        self.add_button(self._button_text_replace, Constants.playlist_confirm_reponse_replace)
        self.add_button(self._button_text_cancel, Constants.playlist_confirm_reponse_cancel)
        self.get_content_area().append(Gtk.Label(label="Selected: " + add_item.metaname))
        self.get_content_area().set_size_request(300, 100)

class PlaylistEditDialog(Gtk.Dialog):
    _button_text_play       = "Play"
    _button_text_up         = "Up"
    _button_text_down       = "Down"
    _button_text_delete     = "Delete"
    _button_text_cancel     = "Cancel"
    def __init__(self, parent, song, *args, **kwargs):
        super().__init__(title="Edit playlist", *args, **kwargs)
        self.set_transient_for(parent)
        self.set_modal(True)

        for tup in ((self._button_text_play, Constants.playlist_edit_response_play), 
                             (self._button_text_up, Constants.playlist_edit_response_up), 
                             (self._button_text_down, Constants.playlist_edit_response_down), 
                             (self._button_text_delete, Constants.playlist_edit_response_delete), 
                             (self._button_text_cancel, Constants.playlist_confirm_reponse_cancel)):
            self.add_button(tup[0], tup[1])
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
        if not hasattr(self, '_node'):
            return None
        return self._node
    node = property(fget=get_node, fset=set_node)

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
        if not hasattr(self, '_index'):
            return None
        return self._index

    index = property(fget=get_index, fset=set_index)

class ColumnBrowser(Gtk.Box, KeyPressedReceiver):
    """
    Column browser for a tree data structure. Inherits from GtkBox.
    Creates columns with a list of GtkScrolledWindows containing a GtkListBox.
    """
    def __init__(self, parent:Gtk.Window, app:Gtk.Application, content_tree:Gio.ListStore, cols=2, spacing=0, hexpand=True, vexpand=True, *args, **kwargs):
        """
        Constructor for the column browser.
        :param parent: parent object
        :param app: main application object
        :param content_tree: Gio.ListStore containing the content metadata tree
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
        self._columns = []
        ## Initialize the columns
        for i in range(0, cols):
            scroll = Gtk.ScrolledWindow()
            listbox = IndexedListBox()
            listbox.set_hexpand(hexpand)
            listbox.set_vexpand(vexpand)
            listbox.index = i
            listbox.connect("row-selected", self.on_row_selected)
            #listbox.connect("row-activated", self.on_row_activated)
            scroll.set_child(listbox)
            self.append(scroll)
            self._columns.append(listbox)
        ## Initialize data in 1st column
        self._columns[0].bind_model(model=content_tree, create_widget_func=self.create_list_label)

        self.set_key_pressed_controller()
        self.key_pressed_callbacks = {
            Gdk.KEY_Return:     (self.parent.add_to_playlist,),
        }
        callback_config_tuples = {
            (Constants.config_section_keys, "info"):       (self.info_popup,),
        }
        self.add_config_keys(self.key_pressed_callbacks, callback_config_tuples, self.app.config)

    def get_last_selected_row(self):
        log = logging.getLogger(__name__ + "." + self.__class__.__name__ + "." + inspect.stack()[0].function)
        for i in range(self.num_columns-1, -1, -1):
            row = self._columns[i].get_selected_row()
            if not row:
                log.debug("no selected row: %d" % i)
                continue
            return row

    def create_list_label(self, node):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        label = ContentTreeLabel(label=node.metaname, node=node)
        label.set_halign(Gtk.Align.START)
        label.set_valign(Gtk.Align.START)
        log.debug("returning label for: %s" % label.get_label())
        return label

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
        node = label.node
        if not node:
            log.error("node is None")
            return
        log.debug("row selected: %s %s" % (node.metatype, node.get_metadata()))
        ## clear out all columns to the right
        for i in range(listbox.get_index()+1, self.num_columns):
            self._columns[i].bind_model(model=None, create_widget_func=None)
        ## load and show the next column to the right based on the current column
        self.app.load_content_data(node=node)
        if node.metatype not in (Constants.node_t_song, Constants.node_t_file) and listbox.get_index() < self.num_columns-1:
            self._columns[listbox.get_index()+1].bind_model(model=node.get_child_layer(), create_widget_func=self.create_list_label)

    def on_row_activated(self, listbox, listboxrow):
        log = logging.getLogger(__name__ + "." + self.__class__.__name__ + "." + inspect.stack()[0].function)
        try:
            label = listboxrow.get_child()
            if label.metatype in ('song', 'album'):
                self.parent.add_to_playlist()
        except Exception as e:
            log.error("error on row_activated (%s): %s" % (type(e).__name__, e))

    def info_popup(self):
        """
        Call SongInfoDialog to display the song data from the selected browser row
        """
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        selected = self.get_last_selected_row()
        if not selected:
            log.error("no row selected")
            return
        log.debug("selected: %s" % selected)
        label = selected.get_child()
        if not label and not isinstance(label, ContentTreeLabel):
            log.error("ColumnBrowser selected row child is of type: %s" % type(selected.get_child()).__name__)
            return
        log.debug("song info: %s" % label.node.get_metadata())
        dialog = SongInfoDialog(self.parent, label.node)
        dialog.show()

class PlaybackDisplay(Gtk.Grid):
    def __init__(self, parent:Gtk.Window, app:Gtk.Application, sound_card:int=None, sound_device:int=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_audiofile = None
        self.parent = parent
        self.app = app
        self.sound_card = sound_card
        self.sound_device = sound_device
        self.set_name("playback-display")
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.FILL)
        self.set_hexpand(True)
        self.set_vexpand(True)

        ## Current album art
        self.current_albumart = Gtk.Picture.new()
        self.current_albumart.set_name("albumart")
        self.current_albumart.props.content_fit = Gtk.ContentFit.COVER
        self.current_albumart.set_can_shrink(True)
        self.current_albumart.set_halign(Gtk.Align.BASELINE)
        self.current_albumart.set_valign(Gtk.Align.BASELINE)
        self.current_albumart.set_hexpand(False)
        self.current_albumart.set_vexpand(False)

        ## Box containing playback info labels+text
        self.playback_info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.playback_info_box.set_name("playback-info")
        self.playback_info_box.set_halign(Gtk.Align.FILL)
        self.playback_info_box.set_valign(Gtk.Align.FILL)
        self.playback_info_box.set_hexpand(True)
        self.playback_info_box.set_vexpand(True)

        # song title label
        self.current_title_label = Gtk.Label(label=" ")
        self.current_title_label.set_name("current-title")
        self.current_title_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.current_title_label.set_halign(Gtk.Align.START)
        self.current_title_label.set_valign(Gtk.Align.START)
        self.current_title_label.set_wrap(False)
        self.current_title_label.set_hexpand(False)
        self.current_title_label.set_vexpand(False)
        self.current_title_label.set_justify(Gtk.Justification.LEFT)

        # artist label
        self.current_artist_label = Gtk.Label(label=" ")
        self.current_artist_label.set_name("current-artist")
        self.current_artist_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.current_artist_label.set_halign(Gtk.Align.START)
        self.current_artist_label.set_valign(Gtk.Align.START)
        self.current_artist_label.set_wrap(False)
        self.current_artist_label.set_hexpand(False)
        self.current_artist_label.set_vexpand(False)
        self.current_artist_label.set_justify(Gtk.Justification.LEFT)

        # album label
        self.current_album_label = Gtk.Label(label=" ")
        self.current_album_label.set_name("current-album")
        self.current_album_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.current_album_label.set_halign(Gtk.Align.START)
        self.current_album_label.set_valign(Gtk.Align.START)
        self.current_album_label.set_wrap(False)
        self.current_album_label.set_hexpand(False)
        self.current_album_label.set_vexpand(True)
        self.current_album_label.set_justify(Gtk.Justification.LEFT)

        # time label
        self.current_time_label = Gtk.Label(label=" ")
        self.current_time_label.set_name("current-time")
        self.current_time_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.current_time_label.set_halign(Gtk.Align.START)
        self.current_time_label.set_valign(Gtk.Align.END)
        self.current_time_label.set_wrap(False)
        self.current_time_label.set_hexpand(False)
        self.current_time_label.set_vexpand(False)
        self.current_time_label.set_justify(Gtk.Justification.LEFT)

        # stats1 label
        self.stats1_label = Gtk.Label(label=" ")
        self.stats1_label.set_name("stats1")
        self.stats1_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.stats1_label.set_halign(Gtk.Align.START)
        self.stats1_label.set_valign(Gtk.Align.END)
        self.stats1_label.set_wrap(False)
        self.stats1_label.set_hexpand(False)
        self.stats1_label.set_vexpand(False)
        self.stats1_label.set_justify(Gtk.Justification.LEFT)

        # stats2 label
        self.stats2_label = Gtk.Label(label=" ")
        self.stats2_label.set_name("stats2")
        self.stats2_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.stats2_label.set_halign(Gtk.Align.START)
        self.stats2_label.set_valign(Gtk.Align.END)
        self.stats2_label.set_wrap(False)
        self.stats2_label.set_hexpand(False)
        self.stats2_label.set_vexpand(False)
        self.stats2_label.set_justify(Gtk.Justification.LEFT)

        ## Add labels to box
        self.playback_info_box.append(self.current_title_label)
        self.playback_info_box.append(self.current_artist_label)
        self.playback_info_box.append(self.current_album_label)
        self.playback_info_box.append(self.current_time_label)
        self.playback_info_box.append(self.stats1_label)
        self.playback_info_box.append(self.stats2_label)

        self._create_progressbar()
        self._create_button_box()

        self.attach(self.current_albumart, 1, 1, 1, 1)
        self.attach(self.playback_info_box, 1, 1, 1, 1)
        self.attach(self.song_progress, 1, 2, 1, 1)
        self.attach(self.playback_button_box, 1, 3, 1, 1)
        self._set_controllers()

    def _create_progressbar(self):
        ## Song progress bar
        self.song_progress = Gtk.LevelBar()
        self.song_progress.set_size_request(-1, Constants.progressbar_height)
        self.song_progress.set_name("progressbar")

    def _create_button_box(self):
        ## Setup playback button box
        self.playback_button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.playback_button_box.set_name("button-box")
        self.playback_button_box.set_spacing(Constants.button_box_spacing)
        self.previous_button = Gtk.Button(label=Constants.symbol_previous)
        self.previous_button.set_hexpand(True)
        self.previous_button.set_vexpand(False)
        self.rewind_button = Gtk.Button(label=Constants.symbol_rewind)
        self.rewind_button.set_hexpand(True)
        self.rewind_button.set_vexpand(False)
        self.stop_button = Gtk.Button(label=Constants.symbol_stop)
        self.stop_button.set_hexpand(True)
        self.stop_button.set_vexpand(False)
        self.play_button = Gtk.Button(label=Constants.symbol_play)
        self.play_button.set_hexpand(True)
        self.play_button.set_vexpand(False)
        self.cue_button = Gtk.Button(label=Constants.symbol_cue)
        self.cue_button.set_hexpand(True)
        self.cue_button.set_vexpand(False)
        self.next_button = Gtk.Button(label=Constants.symbol_next)
        self.next_button.set_hexpand(True)
        self.next_button.set_vexpand(False)
        self.playback_button_box.append(self.previous_button)
        self.playback_button_box.append(self.rewind_button)
        self.playback_button_box.append(self.stop_button)
        self.playback_button_box.append(self.play_button)
        self.playback_button_box.append(self.cue_button)
        self.playback_button_box.append(self.next_button)
        self.playback_button_box.set_hexpand(True)
        self.playback_button_box.set_hexpand(False)

    def _set_controllers(self):
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
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
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
                    log.error("opening up proc file (%s): %s" % (type(e).__name__, e))
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
                pass
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

    def get_albumart_from_audiofile(self, audiofile:str):
        """
        Extract album art from a file
        :param audiofile: string, path of the file containing the audio data
        :return: raw image data
        """
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        log.debug("audiofile: %s" % audiofile)
        img_data = None

        ## Try to find album art in the media file
        if not os.path.isfile(audiofile):
            log.debug("audio file does not exist: %s" % audiofile)
            return None
        else:
            try:
                if re.search(r'\.flac$', audiofile, re.IGNORECASE):
                    log.debug("checking flac file")
                    a = FLAC(audiofile)
                    if len(a.pictures):
                        img_data = a.pictures[0].data
                elif re.search(r'\.m4a$', audiofile, re.IGNORECASE):
                    log.debug("checking mp4 file")
                    a = MP4(audiofile)
                    if 'covr' in a.tags:
                        if len(a.tags['covr']):
                            img_data = a.tags['covr'][0]
                else:
                    log.debug("checking generic file")
                    a = mutagen.File(audiofile)
                    for k in a:
                        if re.match(r'APIC:', k):
                            img_data = a[k].data
                            break
            except Exception as e:
                log.error("could not open audio file '%s' (%s): %s" % (audiofile, type(e).__name__, e))
        return img_data

    def get_albumart_filename(self, audiofile:str):
        ## Look for album art on the directory of the media file
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        log.debug("audiofile: %s" % audiofile)
        cover_path = ""
        song_dir = os.path.dirname(audiofile)
        if os.path.isdir(song_dir):
            try:
                log.debug("looking for image files in directory: %s" % song_dir)
                for f in os.listdir(song_dir):
                    if re.match(r'.*(cover|albumart|folder).*\.(jpg|png|jpeg)', f, re.IGNORECASE):
                        log.debug("found potential cover file: %s" % f)
                        cover_path = song_dir + "/" + f
                        break
                log.debug("looking for cover file: %s" % cover_path)
                if os.path.isfile(cover_path):
                    return cover_path
            except Exception as e:
                log.error("error finding cover file (%s): %s" % (type(e).__name__, e))
        return None

    def set_current_albumart(self, mpd_currentsong:dict, music_dir:str):
        """
        Load and display image of current song if it has changed since the last time this function was run, or on the first run.
        """
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        if not mpd_currentsong or not 'file' in mpd_currentsong:
            self.current_albumart.set_paintable(None)
            self.current_albumart.set_size_request(0, 0)
            return

        audiofile = music_dir + "/" + mpd_currentsong['file']
        if not hasattr(self, 'last_audiofile') or self.last_audiofile != audiofile:
            ## The file has changed since the last update, get the new album art.
            log.debug("new cover file, updating")
            ## Try to load image from audiofile 1st
            img_data = self.get_albumart_from_audiofile(audiofile)
            if img_data:
                log.debug("image data found in audiofile")
                try:
                    tex = Gdk.Texture.new_from_bytes(GLib.Bytes(img_data))
                    log.debug("from bytes image size: %d x %d" % (tex.get_width(), tex.get_height()))
                    self.current_albumart.set_paintable(tex)
                except Exception as e:
                    log.error("error loading image from bytes (%s): %s" % (type(e).__name__, e))
            else:
                log.debug("no image data found in audiofile")
                coverfile = self.get_albumart_filename(audiofile)
                if coverfile:
                    try:
                        self.current_albumart.set_filename(coverfile)
                        paintable = self.current_albumart.get_paintable()
                        if not paintable:
                            log.debug("no paintable object")
                        else:
                            log.debug("from file image size: %d x %d" % (paintable.get_width(), paintable.get_height()))
                    except Exception as e:
                        log.error("error loading image from file (%s): %s" % (type(e).__name__, e))
                else:
                    ## No album art, clear the image in the UI.
                    log.debug("no albumart found for: %s" % audiofile)
                    self.current_albumart.set_paintable(None)
                    self.current_albumart.set_size_request(0,0)
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

class PlaylistDisplay(Gtk.ListBox, KeyPressedReceiver):
    """
    Handles display and updates of the playlist. The listbox entries are controlled by a Gio.ListStore listmodel.
    """
    last_selected = 0  ## Points to last selected song in playlist

    def __init__(self, parent:Gtk.Window, app:Gtk.Application,  *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_name("playlist-display")
        self.liststore = Gio.ListStore()
        self.bind_model(model=self.liststore, create_widget_func=self.create_list_label)
        self.parent = parent
        self.app = app

        self.set_key_pressed_controller()
        self.key_pressed_callbacks = {
            Gdk.KEY_Return:         (self.edit_popup,),
            Gdk.KEY_Delete:         (self.track_delete,),
            Gdk.KEY_BackSpace:      (self.track_delete,),
        }
        callback_config_tuples = {
            (Constants.config_section_keys, "info"):       (self.info_popup,),
            (Constants.config_section_keys, "moveup"):     (self.track_moveup,),
            (Constants.config_section_keys, "movedown"):   (self.track_movedown,),
            (Constants.config_section_keys, "delete"):     (self.track_delete,),
        }
        self.add_config_keys(self.key_pressed_callbacks, callback_config_tuples, self.app.config)

    def update(self, playlist:dict, mpd_currentsong:dict):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        self.liststore.remove_all()
        if playlist:
            log.debug("playlist: %s" % playlist)
            ## Add songs to the list
            for song in playlist:
                log.debug("adding song to playlist: %s" % song['title'])
                self.liststore.append(data.ContentTreeNode(metadata=song))
            if not self.last_selected is None:
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

    def edit_popup(self):
        """
        Displays dialog with playlist edit options. Performs task based on user input.
        Play, move song up in playlist, down in playlist, delete from playlist.
        """
        song = self.get_selected_row().get_child().node.get_metadata()
        edit_playlist_dialog = PlaylistEditDialog(parent=self.parent, song=song)
        edit_playlist_dialog.connect('response', self.edit_response)
        edit_playlist_dialog.show()

    def edit_response(self, dialog, response):
        if response == Constants.playlist_edit_response_up:
            self.track_moveup()
        elif response == Constants.playlist_edit_response_down:
            self.track_movedown()
        elif response == Constants.playlist_edit_response_delete:
            dialog.destroy()
            self.track_delete()
        elif response == Constants.playlist_edit_response_play:
            song = self.get_selected_row().get_child().node.get_metadata()
            self.parent.mpd_playid(song['id'])
            dialog.destroy()
        elif response == Constants.playlist_edit_response_cancel:
            dialog.destroy()

    def info_popup(self):
        """
        Call SongInfoDialog to display the song data from the selected playlist row
        """
        selected = self.get_selected_row()
        if not selected:
            log.error("no row selected")
            return
        label = selected.get_child()
        if not label or not isinstance(label, ContentTreeLabel):
            log.error("invalid child of row")
        song = label.node.get_metadata()
        if song is None:
            return
        log.debug("song info: %s" % song)
        dialog = SongInfoDialog(self.parent, label.node)
        dialog.show()

    def track_moveup(self):
        index = self.get_selected_row().get_index()
        song = self.get_selected_row().get_child().node.get_metadata()
        log.debug("moving song up 1: '%s'" % song['title'])
        if index > 0:
            index -= 1
            self.app.mpd_moveid(song['id'], index)
        self.last_selected = index

    def track_movedown(self):
        index = self.get_selected_row().get_index()
        song = self.get_selected_row().get_child().node.get_metadata()
        log.debug("moving song down 1: '%s'" % song['title'])
        if index + 1 < len(self.liststore):
            self.app.mpd_moveid(song['id'], index+1)
        self.last_selected = index+1

    def track_delete(self):
        index = self.get_selected_row().get_index()
        song = self.get_selected_row().get_child().node.get_metadata()
        log.debug("deleting song: '%s'" % song)
        index -= 1
        if index < 0:
            index = 0
        self.app.mpd_deleteid(song['id'])
        self.last_selected = index

class MpdFrontWindow(Gtk.Window, KeyPressedReceiver):
    focus_on = "broswer"        ## Either 'playlist' or 'browser'

    def __init__(self, config:configparser, application:Gtk.ApplicationWindow, content_tree:Gio.ListStore, *args, **kwargs):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        super().__init__(title=Constants.window_title, application=application, *args, **kwargs)
        self.config = config
        self.app = application
        self.content_tree = content_tree
        self._initial_resized = False

        ## Set basic window properties
        width = Constants.default_width
        height = Constants.default_height
        if config.has_option(Constants.config_section_main, "width"):
            width = int(config.get(Constants.config_section_main, "width"))
        if config.has_option(Constants.config_section_main, "height"):
            height = int(config.get(Constants.config_section_main, "height"))
        self.set_default_size(width, height)
        if (config.has_option(Constants.config_section_main, "resize") and
                re.match(r'yes$', config.get(Constants.config_section_main, "resize"), re.IGNORECASE)):
            self.set_resizable(True)
        else:
            self.set_resizable(False)
        if (config.has_option(Constants.config_section_main, "decorations") and
                re.match(r'yes$', config.get(Constants.config_section_main, "decorations"), re.IGNORECASE)):
            self.set_decorated(True)
        else:
            self.set_decorated(False)
        if (config.has_option(Constants.config_section_main, "fullscreen") and
                re.match(r'yes$', config.get(Constants.config_section_main, "fullscreen"), re.IGNORECASE)):
            self.fullscreen()

        ## mainpaned is the toplevel layout container
        self.mainpaned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        self.mainpaned.set_name("mainpaned")
        self.set_child(self.mainpaned)

        ## Setup browser columns
        self.browser = ColumnBrowser(parent=self, app=self.app, content_tree=self.content_tree,
                                         cols=Constants.browser_num_columnns, spacing=0, hexpand=True, vexpand=True)
        self.browser.set_name("browser")
        self.mainpaned.set_start_child(self.browser)

        ## Setup bottom half
        self.bottompaned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.mainpaned.set_end_child(self.bottompaned)

        ## Setup playback display
        sound_card = None
        sound_device = None
        if self.config.has_option(Constants.config_section_main, "sound_card"):
            sound_card = self.config.get(Constants.config_section_main, "sound_card")
        if self.config.has_option(Constants.config_section_main, "sound_device"):
            sound_device = self.config.get(Constants.config_section_main, "sound_device")
        self.playback_display = PlaybackDisplay(parent=self, app=self.app, sound_card=sound_card, sound_device=sound_device)
        self.bottompaned.set_start_child(self.playback_display)

        ## Setup playlist
        self.playlist_list = PlaylistDisplay(parent=self, app=self.app)
        self.playlist_scroll = Gtk.ScrolledWindow()
        self.playlist_scroll.set_name("playlistscroll")
        self.playlist_scroll.set_hexpand(True)
        self.playlist_scroll.set_child(self.playlist_list)
        self.bottompaned.set_end_child(self.playlist_scroll)

        ## Setup key-pressed events
        self.set_key_pressed_controller()
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
            Gdk.KEY_AudioRewind:        (self.app.mpd_seekcur, (Constants.rewind_arg,)),
            Gdk.KEY_AudioForward:       (self.app.mpd_seekcur, (Constants.cue_arg,)),
            Gdk.KEY_v:                  (self.set_dividers,),
            Gdk.KEY_q:                  (log.debug, ("pressed q",)),
            Gdk.KEY_b:                  (data.dump, (self.content_tree,)),
        }
        ## callbacks for meta mod key
        self.key_pressed_callbacks_mod_meta = {
            Gdk.KEY_q:                  (self.close,),
            Gdk.KEY_Q:                  (self.close,),
        }
        ## callbacks for ctrl mod key
        self.key_pressed_callbacks_mod_ctrl = {
            Gdk.KEY_q:                  (self.close,),
            Gdk.KEY_Q:                  (self.close,),
        }
        #self.key_pressed_callbacks_mod_alt = {}
        ## keys defined in config file
        callback_config_tuples = {
            (Constants.config_section_keys, "playpause"):      (self.app.mpd_toggle,),
            (Constants.config_section_keys, "stop"):           (self.app.mpd_stop,),
            (Constants.config_section_keys, "previous"):       (self.app.mpd_previous,),
            (Constants.config_section_keys, "next"):           (self.app.mpd_next,),
            (Constants.config_section_keys, "rewind"):         (self.app.mpd_seekcur, (Constants.rewind_arg,)),
            (Constants.config_section_keys, "cue"):            (self.app.mpd_seekcur, (Constants.cue_arg,)),
            (Constants.config_section_keys, "outputs"):        (self.event_outputs_dialog,),
            (Constants.config_section_keys, "options"):        (self.event_options_dialog,),
            (Constants.config_section_keys, "cardselect"):     (self.event_cardselect_dialog,),
            (Constants.config_section_keys, "browser"):        (self.event_focus_browser,),
            (Constants.config_section_keys, "playlist"):       (self.event_focus_playlist,),
            (Constants.config_section_keys, "toggle_main"):    (self.event_toggle_main,),
            (Constants.config_section_keys, "toggle_bottom"):  (self.event_toggle_bottom,),
        }
        self.add_config_keys(self.key_pressed_callbacks, callback_config_tuples, config)

        ## Set initially selected widgets
        self._playlist_last_selected = 0
        self.playlist_list.select_row(self.playlist_list.get_row_at_index(self._playlist_last_selected))
        #self.browser.columns[0].select_row(self.browser.columns[0].get_row_at_index(0))

        ## Set event handlers
        self.connect("destroy", self.destroy)
        self.connect("state_flags_changed", self.on_state_flags_changed)

    def event_outputs_dialog(self):
        self.outputs_dialog = OutputsDialog(self, self.outputs_changed)

    def event_options_dialog(self):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        mpd_status = self.app.mpd_status()
        options_dialog = OptionsDialog(self, self.options_changed, mpd_status)
        options_dialog.show()

    def event_cardselect_dialog(self):
        cards_dialog = CardSelectDialog(self, self.soundcard_changed)
        cards_dialog.show()

    def event_focus_browser(self):
        ## Focus on the last selected row in the browser
        self.browser.get_last_selected_row().grab_focus()
        if self.mainpaned.get_position() < Constants.divider_tolerance:
            self.mainpaned.set_position(self.mainpaned.get_height()/2)
        return

    def event_focus_playlist(self):
        ## Focus on the selected row in the playlist
        selected_row = self.playlist_list.get_selected_row()
        if not selected_row:
            selected_row = self.playlist_list.get_row_at_index(0)
            self.playlist_list.select_row(selected_row)
        selected_row.grab_focus()

    def event_toggle_main(self):
        """
        Rotates through full and split screen for the main window. Rotation: split, browser full, bottom full
        """
        log = logging.getLogger(__name__ + "." + self.__class__.__name__ + "." + inspect.stack()[0].function)
        height = self.get_height()
        position = self.mainpaned.get_position()
        if position < Constants.divider_tolerance:
            log.debug("setting main to split screen")
            self.mainpaned.set_position(height/2)
        elif position > (height - Constants.divider_tolerance):
            log.debug("setting bottom to full screen")
            self.mainpaned.set_position(0)
        else:
            log.debug("setting browser to full screen")
            self.mainpaned.set_position(height)

    def event_toggle_bottom(self):
        """
        Rotates through full and split screen for the bottom paned. Rotation: split, playlist full, playlist full
        :return:
        """
        log = logging.getLogger(__name__ + "." + self.__class__.__name__ + "." + inspect.stack()[0].function)
        width = self.get_width()
        position = self.bottompaned.get_position()
        if position < Constants.divider_tolerance:
            self.bottompaned.set_position(width/2)
        elif position > (width - Constants.divider_tolerance):
            self.bottompaned.set_position(0)
        else:
            self.bottompaned.set_position(width)

    def add_to_playlist(self):
        """
        Displays playlist confirmation dialog
        """
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        selected = self.browser.get_last_selected_row()
        if not selected:
            return
        label = selected.get_child()
        if not label or not isinstance(label, ContentTreeLabel):
            return
        log.debug("selected metatype: %s" % label.node.metatype)
        if not label.node.metatype in (Constants.node_t_song, Constants.node_t_album, Constants.node_t_file):
            log.debug("Not adding this node type: %s" % label.node.metatype)
            return
        log.debug("confirming add item: %s" % label.node.get_metadata())
        playlist_confirm_dialog = PlaylistConfirmDialog(parent=self, add_item=label.node)
        playlist_confirm_dialog.connect('response', self.playlist_confirm_dialog_response)
        playlist_confirm_dialog.show()

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
        log = logging.getLogger(__name__ + "." + self.__class__.__name__ + "." + inspect.stack()[0].function)
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
        log = logging.getLogger(__name__ + "." + self.__class__.__name__ + "." + inspect.stack()[0].function)
        log.debug("changing sound card: %s = %s" % (change, button.get_value_as_int()))
        if change == "card_id":
            self.card_id = button.get_value_as_int()
        elif change == "device_id":
            self.device_id = button.get_value_as_int()

    def playlist_confirm_dialog_response(self, dialog, response):
        log = logging.getLogger(__name__ + "." + self.__class__.__name__ + "." + inspect.stack()[0].function)
        log.debug("dialog response: %s" % response)
        dialog.destroy()
        selected = self.browser.get_last_selected_row()
        if not selected:
            log.error("attempting to add with nothing selected")
            return
        label = selected.get_child()
        if not label or not isinstance(label, ContentTreeLabel):
            log.error("no valid label returned from row: %s" % label)
            return
        node = label.node
        if response == Constants.playlist_confirm_reponse_replace:
            ## Clear list before adding for "replace"
            self.app.mpd_clear()
        if response in (Constants.playlist_confirm_reponse_add, Constants.playlist_confirm_reponse_replace):
            self.app.add_to_playlist(node)

    def on_state_flags_changed(self, widget, flags):
        log = logging.getLogger(__name__ + "." + self.__class__.__name__ + "." + inspect.stack()[0].function)
        log.debug("state flags: %s" % flags)
        #if not self._initial_resized and (flags & Gtk.StateFlags.FOCUS_WITHIN):
        #    self.set_dividers()
        #    self._initial_resized = True

    def set_dividers(self):
        log = logging.getLogger(__name__+"."+self.__class__.__name__+"."+inspect.stack()[0].function)
        log.debug("setting dividers")
        if self.mainpaned.get_height():
            self.mainpaned.set_position(self.mainpaned.get_height()/2)
        else:
            self.mainpaned.set_position(self.props.default_height/2)
        if self.bottompaned.get_width():
            self.bottompaned.set_position(self.bottompaned.get_width()/2)
        else:
            self.bottompaned.set_position(self.props.default_width/2)
