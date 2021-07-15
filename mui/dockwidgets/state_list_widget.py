from typing import Dict, Final, Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout, QTreeWidgetItem, QTreeWidget
from binaryninja import BinaryView
from binaryninjaui import DockContextHandler, ViewFrame
from manticore.core.plugin import StateDescriptor
from manticore.utils.enums import StateStatus


class StateListWidget(QWidget, DockContextHandler):

    NAME: Final[str] = "Manticore State"

    def __init__(self, name: str, parent: ViewFrame, data: BinaryView):
        QWidget.__init__(self, parent)
        DockContextHandler.__init__(self, self, name)

        tree_widget = QTreeWidget()
        tree_widget.setColumnCount(1)
        tree_widget.headerItem().setText(0, "State List")
        self.tree_widget = tree_widget

        self.active_states = QTreeWidgetItem(None, ["Active"])
        self.waiting_states = QTreeWidgetItem(None, ["Waiting"])
        self.complete_states = QTreeWidgetItem(None, ["Complete"])
        self.error_states = QTreeWidgetItem(None, ["Errored"])

        self.state_lists = [
            self.active_states,
            self.waiting_states,
            self.complete_states,
            self.error_states,
        ]
        tree_widget.insertTopLevelItems(0, self.state_lists)
        for state_list in self.state_lists:
            tree_widget.expandItem(state_list)

        layout = QVBoxLayout()
        layout.addWidget(tree_widget)
        self.setLayout(layout)

        self.state_status_mapping = [
            (self.active_states, [StateStatus.running]),
            (self.waiting_states, [StateStatus.waiting_for_worker, StateStatus.waiting_for_solver]),
            (self.complete_states, [StateStatus.stopped]),
            (self.error_states, [StateStatus.destroyed]),
        ]

        self.states: Dict[int, StateDescriptor] = {}
        self.state_items: Dict[int, QTreeWidgetItem] = {}

    def notifyStatesChanged(self, new_states: Dict[int, StateDescriptor]):
        """Updates the UI to reflect new_states, clears everything if an empty dict is provided"""
        old_states = self.states

        # add/update new states
        for state_id, state in new_states.items():
            if state_id in self.state_items:
                item = self.state_items[state_id]
                self._update_item(item, state)
            else:
                item = self._create_item(state)
                self.state_items[state_id] = item

        # remove old states
        for removed_state_id in set(old_states.keys()) - set(new_states.keys()):
            item = self.state_items[removed_state_id]
            item.parent().removeChild(item)
            del self.state_items[removed_state_id]

        # update list counts
        self._refresh_list_counts()

        # update the states reference
        self.states = new_states

    def _update_item(self, item: QTreeWidgetItem, state: StateDescriptor):
        """Updates a single item based on its new state"""
        switch_to_list = None

        for state_list, status_list in self.state_status_mapping:
            if state.status in status_list and item.parent() is not state_list:
                switch_to_list = state_list
                break

        if switch_to_list is not None:
            item.parent().removeChild(item)
            switch_to_list.addChild(item)

    def _create_item(self, state: StateDescriptor) -> QTreeWidgetItem:
        """Creates a new item that represents a given state"""
        for state_list, status_list in self.state_status_mapping:
            if state.status in status_list:
                return QTreeWidgetItem(state_list, [f"State {state.state_id}"])

        raise ValueError(f"Unknown status {state.status}")

    def _refresh_list_counts(self):
        """Refreshes all the state counts"""
        total_count = 0

        # update count for each individual list
        for state_list in self.state_lists:
            child_count = state_list.childCount()
            state_list.setText(0, f'{state_list.text(0).split(" ")[0]} ({child_count})')

            total_count += child_count

        header_item = self.tree_widget.headerItem()

        title_without_count = header_item.text(0)
        # strip previous count from title
        if title_without_count[-1] == ")":
            title_without_count = title_without_count[: title_without_count.rfind("(") - 1]

        header_item.setText(0, f"{title_without_count} ({total_count})")
