import sys
import logging
import gi
from gi.repository import GObject, GLib, Gio
from .constants import Constants

log = logging.getLogger(__name__)

class ContentTreeLayer:
    None

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

    def get_child_layer(self):
        return self._child_layer

    def get_name(self):
        return self._name

    def set_name(self, name:str):
        self._name = name

class ContentTreeLayer:
    _nodes:list = None
    _by_name:dict = None

    def __init__(self):
        self._nodes = []
        self._by_name = {}

    def add_node(self, node:ContentTreeNode):
        #log.debug("adding node with metadata: %s" % node.metadata)
        self._nodes.append(node)
        if node.get_name() in self._by_name.keys():
            log.error("node by name '%s' already exists" % node.get_name())
        self._by_name[node.get_name()] = node

    def get_node_list(self):
        return self._nodes

    def get_node_names(self):
        return self._by_name.keys()

    def get_node(self, name:str):
        if name in self._by_name.keys():
            return self._by_name[name]
        return None

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
                layer.add_node(ContentTreeNode(m))
            except Exception as e:
                log.error("could not create node: %s" % e)
        return layer

class Dumper:
    def dump(tree:ContentTreeLayer, indent:str=""):
        node_list = tree.get_node_list()
        for n in node_list:
            i_char1 = "|"
            i_char2 = "|"
            if n == node_list[-1]:
                i_char1 = "+"
                i_char2 = " "
            sys.stdout.write("%s%s-%s\n" % (indent, i_char1, n.get_name()))
            Dumper.dump(n.get_child_layer(), indent+i_char2+"  ")
