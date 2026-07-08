from gui.qt.QtWidgets import QWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QHeaderView
from gui.qt.QtGui import QColor, QBrush

from gui.qt import QT_API

class VariablesPanel(QWidget):
    def __init__(self):
        super().__init__()
        
        self.variables_panel = QTreeWidget()
        self.variables_panel.setHeaderLabels(["Name", "Type", "Value"])
        
        header = self.variables_panel.header()
        if QT_API == "PyQt5":
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.Stretch)
        else:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        
        self.variables_panel.setAlternatingRowColors(True)
        self.variables_panel.setAnimated(True)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.variables_panel)

    def update_vars(self, formatted_vars_list):
        self.variables_panel.clear()
        for var_data in formatted_vars_list:
            self.add_variable_node(self.variables_panel, var_data)

    def add_variable_node(self, parent, var_data):
        """Recursively maps the backend metadata structure into QTreeWidgetItems."""

        item = QTreeWidgetItem()
        item.setText(0, var_data.get("name", ""))
        item.setText(1, var_data.get("type", ""))
        item.setText(2, var_data.get("value", ""))
        
        self.style_tree_item(item, var_data.get("type", ""))

        if isinstance(parent, QTreeWidget):
            parent.addTopLevelItem(item)
            item.setExpanded(False)
        else:
            parent.addChild(item)

        for child_data in var_data.get("children", []):
            self.add_variable_node(item, child_data)

    def style_tree_item(self, item: QTreeWidgetItem, var_type):
        item.setForeground(1, QBrush(QColor("gray")))

        if var_type in ("int", "float", "complex"):
            item.setForeground(2, QBrush(QColor("blue")))
        elif var_type == "str":
            item.setForeground(2, QBrush(QColor("darkRed")))
        elif var_type in ("bool", "NoneType"):
            item.setForeground(2, QBrush(QColor("darkMagenta")))
        elif var_type in ("list", "dict", "tuple", "set"):
            item.setForeground(2, QBrush(QColor("darkCyan")))
        else:
            item.setForeground(2, QBrush(QColor("darkBlue")))
