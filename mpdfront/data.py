import sys
import logging
import gi
from .constants import Constants
from gi.repository import GObject, Gio

log = logging.getLogger(__name__)

class ContentTreeNode(GObject.GObject):
    _child_layer:Gio.ListStore = None
    _name:str = None
    metadata:dict = None

    def __init__(self, metadata:dict, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._metadata = metadata
        self._child_layer = Gio.ListStore()
        if 'name' in metadata:
            self._metaname = metadata['name']
        if 'type' in metadata:
            self._metatype = metadata['type']
        if 'previous' in metadata:
            self._previous = metadata['previous']
        if 'previous_type' in metadata:
            self._previous_type = metadata['previous_type']
        if 'next_type' in metadata:
            self._next_type = metadata['next_type']

    def get_child_layer(self):
        if not hasattr(self, "_child_layer"):
            return None
        return self._child_layer

    def get_metadata(self, key:str=None):
        if not hasattr(self, "_metadata"):
            return None
        if not key:
            return self._metadata
        if not key in self._metadata:
            return None
        return self._metadata[key]

    def set_metadata(self, key:str, value):
        self._metadata[key] = value

    def get_metaname(self):
        if not hasattr(self, "_metaname"):
            return None
        return self._metaname

    def set_metaname(self, name:str):
        self._metaname = name

    def get_metatype(self):
        if not hasattr(self, "_metatype"):
            return None
        return self._metatype

    def set_metatype(self, type:str):
        self._metatype = type

def dump(tree:Gio.ListStore, indent:str=""):
    n_items = tree.get_n_items()
    for i in range(0, n_items):
        n = tree.get_item(i)
        if not n:
            break
        i_char1 = "|"
        i_char2 = "|"
        if i == n_items - 1:
            i_char1 = "+"
            i_char2 = " "
        sys.stdout.write("%s%s-%s\n" % (indent, i_char1, n.get_metaname()))
        dump(n.get_child_layer(), indent+i_char2+"  ")
        i += 1
