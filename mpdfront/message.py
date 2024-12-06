class QueueMessage:
    _type = ""
    _item = ""
    _data = ""
    def __init__(self, type:str, item:str, data=None):
        if not type or not item:
            raise ValueError("type, item are required arguments")
        self._type = type
        self._item = item
        self._data = data

    def get_type(self):
        return self._type

    def get_item(self):
        return self._item

    def get_data(self):
        return self._data
