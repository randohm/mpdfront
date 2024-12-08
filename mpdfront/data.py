import sys
import logging
import gi
from gi.repository import GObject, GLib, Gio
from .constants import Constants

log = logging.getLogger(__name__)

class ContentTreeLayer(Gio.ListStore):
    _by_name:dict = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._by_name = {}

    def append(self, node:GObject.GObject):
        #log.debug("adding node with metadata: %s" % node.metadata)
        super().append(node)
        if node.get_name() in self._by_name.keys():
            log.info("node by name '%s' already exists" % node.get_name())
        else:
            self._by_name[node.get_name()] = node

    def get_node_names(self):
        return self._by_name.keys()

    def get_node(self, name:str):
        if name in self._by_name.keys():
            return self._by_name[name]
        return None

class ContentTreeNode(GObject.GObject):
    _child_layer:ContentTreeLayer = None
    _name:str = None
    metadata:dict = None

    def __init__(self, metadata:dict, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.metadata = metadata
        self._child_layer = ContentTreeLayer()
        if 'name' in metadata.keys():
            self._name = metadata['name']
        if 'type' in metadata.keys():
            self._type = metadata['name']

    def get_child_layer(self):
        return self._child_layer

    def get_name(self):
        return self._name

    def set_name(self, name:str):
        self._name = name

    def get_type(self):
        return self._type

    def set_type(self, type:str):
        self._type = type


class ContentTree:
    _layer:ContentTreeLayer = None

    def __init__(self):
        self._layer = ContentTreeLayer()

    def __init__(self, metadata_list:list):
        self._layer = LayerFactory.create_layer(metadata_list)

    def get_top_layer(self):
        return self._layer

class LayerFactory:
    def create_layer(metadata_list:list):
        layer = ContentTreeLayer()
        for m in metadata_list:
            try:
                layer.append(ContentTreeNode(m))
            except Exception as e:
                log.error("could not create node: %s" % e)
        return layer

class Dumper:
    def dump(tree:ContentTreeLayer, indent:str=""):
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
            sys.stdout.write("%s%s-%s\n" % (indent, i_char1, n.get_name()))
            Dumper.dump(n.get_child_layer(), indent+i_char2+"  ")
            i += 1
