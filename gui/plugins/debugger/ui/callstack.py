from gui.qt.QtWidgets import (
    QWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, 
    QHeaderView, QAbstractItemView
)
from gui.qt.QtGui import QColor, QBrush
from gui.qt import QT_API

class CallStackPanel(QWidget):
    def __init__(self):
        super().__init__()
        
        self.call_stack_widget = QTreeWidget()
        self.call_stack_widget.setHeaderLabels(["Frame / Variable", "File / Type", "Line / Value"])
        
        header = self.call_stack_widget.header()
        if QT_API == "PyQt5":
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.Interactive) 
            header.setSectionResizeMode(2, QHeaderView.Stretch)
        else:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        self.call_stack_widget.setAlternatingRowColors(True)
        self.call_stack_widget.setAnimated(True)
        self.call_stack_widget.setRootIsDecorated(True)
        self.call_stack_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.call_stack_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.call_stack_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.call_stack_widget.setToolTip("Shows the current call stack and frame-local variables.")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.call_stack_widget)

    def update_call_stack(self, stack_data):
        self.call_stack_widget.clear()

        for frame in stack_data:
            func = frame.get("function", "?")
            file = frame.get("file", "?")
            line = frame.get("line", "?")
            locals_list = frame.get("locals", [])  # This is a list now!

            parts = file.replace("\\", "/").split("/")
            short_file = "/".join(parts[-3:]) if len(parts) > 3 else file

            top = QTreeWidgetItem([
                f"{func}()", 
                short_file, 
                str(line)
            ])
            
            font = top.font(0)
            font.setBold(True)
            for col in range(3):
                top.setFont(col, font)

            self.call_stack_widget.addTopLevelItem(top)

            for var_data in locals_list:
                self.add_variable_node(top, var_data)

            top.setExpanded(False)

    def add_variable_node(self, parent, var_data):
        """Recursively maps the pre-formatted backend structure into the tree."""
        item = QTreeWidgetItem()
        item.setText(0, str(var_data.get("name", "")))
        item.setText(1, str(var_data.get("type", "")))
        item.setText(2, str(var_data.get("value", "")))
        
        self.style_tree_item(item, var_data.get("type", ""))

        if isinstance(parent, QTreeWidget):
            parent.addTopLevelItem(item)
        else:
            parent.addChild(item)

        for child_data in var_data.get("children", []):
            self.add_variable_node(item, child_data)

    def style_tree_item(self, item: QTreeWidgetItem, var_type: str):
        """Matches the exact coloring logic of the VariablesPanel."""
        item.setForeground(1, QBrush(QColor("gray")))

        if var_type in ("int", "float", "complex"):
            item.setForeground(2, QBrush(QColor("blue")))
        elif var_type == "str":
            item.setForeground(2, QBrush(QColor("darkRed")))
        elif var_type in ("bool", "NoneType"):
            item.setForeground(2, QBrush(QColor("darkMagenta")))
        elif var_type in ("list", "dict", "tuple", "set") or "items" in item.text(2):
            item.setForeground(2, QBrush(QColor("darkCyan")))
        elif var_type == "circular_ref" or "Circular" in item.text(2):
            item.setForeground(2, QBrush(QColor("red")))
        else:
            item.setForeground(2, QBrush(QColor("darkBlue")))
