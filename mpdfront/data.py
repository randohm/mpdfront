import sys
import logging
import gi
from .constants import Constants
from gi.repository import GObject, Gio

log = logging.getLogger(__name__)

class ContentTreeNode(GObject.GObject):
    def __init__(self, metadata:dict, previous=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._metadata = metadata
        self._child_layer = Gio.ListStore()
        if 'name' in metadata:
            self._metaname = metadata['name']
        else:
            self._metaname = None
        if 'type' in metadata:
            self._metatype = metadata['type']
        else:
            self._metatype = None
        if previous:
            self._previous = previous
        if 'previous_type' in metadata:
            self._previous_type = metadata['previous_type']
        if 'next_type' in metadata:
            self._next_type = metadata['next_type']

    def get_child_layer(self):
        if not hasattr(self, "_child_layer"):
            return None
        return self._child_layer

    def get_metadata(self, key:str=None):
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
    metaname = property(fget=get_metaname, fset=set_metaname)

    def get_metatype(self):
        if not hasattr(self, "_metatype"):
            return None
        return self._metatype
    def set_metatype(self, metatype:str):
        self._metatype = metatype
    metatype = property(fget=get_metatype, fset=set_metatype)

    def get_previous(self):
        if not hasattr(self, "_previous"):
            return None
        return self._previous
    def set_previous(self, previous):
        self._previous = previous
    previous = property(fget=get_previous, fset=set_previous)

    def get_next_type(self):
        if not hasattr(self, "_next_type"):
            return None
        return self._next_type
    def set_next_type(self, next_type:str):
        self._next_type = next_type
    next_type = property(fget=get_next_type, fset=set_next_type)

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
