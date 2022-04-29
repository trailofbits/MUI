import os
import typing
import grpc
import json
from pathlib import Path
from datetime import datetime
from inspect import getmembers, isfunction
from dataclasses import dataclass

from binaryninja import (
    BinaryView,
    show_message_box,
    MessageBoxButtonSet,
    MessageBoxIcon,
    HighlightStandardColor,
    HighlightColor,
)
from manticore.core.plugin import StateDescriptor
from manticore.native import models

from muicore.MUICore_pb2_grpc import ManticoreUIStub


class MUIState:
    def __init__(self, bv: BinaryView):
        self.bv = bv
        self.states: typing.Dict[int, StateDescriptor] = {}
        self.state_change_listeners: typing.List[
            typing.Callable[
                [typing.Dict[int, StateDescriptor], typing.Dict[int, StateDescriptor]], None
            ]
        ] = []

    def get_state(self, state_id: int) -> typing.Optional[StateDescriptor]:
        """Get the state descriptor for a given id"""
        if state_id in self.states:
            return self.states[state_id]
        else:
            return None

    def get_state_address(self, state_id: int) -> typing.Optional[int]:
        """Get the current instruction address of a given state"""
        state = self.get_state(state_id)

        if state is None:
            return None

        if isinstance(state.pc, int):
            return state.pc
        elif isinstance(state.last_pc, int):
            # use last_pc as a fallback
            return state.last_pc
        else:
            return None

    def navigate_to_state(self, state_id: int) -> None:
        """Navigate to the current instruction of a given state"""
        addr = self.get_state_address(state_id)

        if addr is not None:
            self.bv.navigate(self.bv.view, addr)
        else:
            show_message_box(
                "[MUI] No instruction information available",
                f"State {state_id} doesn't contain any instruction information.",
                MessageBoxButtonSet.OKButtonSet,
                MessageBoxIcon.ErrorIcon,
            )

    def on_state_change(
        self,
        callback: typing.Callable[
            [typing.Dict[int, StateDescriptor], typing.Dict[int, StateDescriptor]], None
        ],
    ) -> None:
        """Register an event listener for state changes"""
        self.state_change_listeners.append(callback)

    def notify_states_changed(self, new_states: typing.Dict[int, StateDescriptor]) -> None:
        """Updates internal states and invokes listeners"""
        old_states = self.states

        for callback in self.state_change_listeners:
            callback(old_states, new_states)

        self.states = new_states


def highlight_instr(bv: BinaryView, addr: int, color: HighlightStandardColor) -> None:
    """Highlight instruction at a given address"""
    blocks = bv.get_basic_blocks_at(addr)
    for block in blocks:
        block.set_auto_highlight(HighlightColor(color, alpha=128))
        block.function.set_auto_instr_highlight(addr, color)


def clear_highlight(bv: BinaryView, addr: int) -> None:
    """Remove instruction highlight"""
    blocks = bv.get_basic_blocks_at(addr)
    for block in blocks:
        block.set_auto_highlight(HighlightColor(HighlightStandardColor.NoHighlightColor))
        block.function.set_auto_instr_highlight(addr, HighlightStandardColor.NoHighlightColor)


def get_default_solc_path():
    """Attempt to find the path for the solc binary"""

    possible_paths = [Path(x) for x in os.environ["PATH"].split(":")]
    possible_paths.extend([Path(os.path.expanduser("~"), ".local/bin").resolve()])

    for path in possible_paths:
        if Path(path, "solc").is_file():
            return str(Path(path, "solc"))

    return ""


def print_timestamp(*args, **kw):
    """Print with timestamp prefixed (local timezone)"""
    timestamp = datetime.now().astimezone()
    print(f"[{timestamp}]", *args, **kw)


@dataclass
class MUIFunctionModel:
    name: str
    func: typing.Callable


def get_function_models() -> typing.List[MUIFunctionModel]:
    """
    Returns available function models
    ref: https://github.com/trailofbits/manticore/blob/master/docs/native.rst#function-models
    """

    # Functions only
    functions = filter(lambda x: isfunction(x[1]), getmembers(models))
    func_models = [MUIFunctionModel(name, func) for name, func in functions]

    # Manually remove non-function model functions
    def is_model(model: MUIFunctionModel) -> bool:
        blacklist = set(["isvariadic", "variadic", "must_be_NULL", "cannot_be_NULL", "can_be_NULL"])
        if model.func.__module__ != "manticore.native.models":
            return False
        # Functions starting with '_' assumed to be private
        if model.name.startswith("_"):
            return False
        if model.name in blacklist:
            return False
        return True

    func_models = list(filter(is_model, func_models))

    return func_models


def function_model_analysis_cb(bv: BinaryView) -> None:
    """
    Callback when initial analysis completed.
    Tries to match functions with same name as available function models
    """
    models = get_function_models()
    model_names = [model.name for model in models]
    matches = set()
    for func in bv.functions:
        for name in model_names:
            if name.startswith(func.name):
                matches.add(func)

    if matches:
        banner = "\n"
        banner += "###################################\n"
        banner += "# MUI Function Model Analysis     #\n"
        banner += "#                                 #\n"
        banner += f"# {len(matches):02d} function(s) match:           #\n"
        for func in matches:
            s = f"# * {func.start:08x}, {func.name}"
            banner += s.ljust(34, " ") + "#\n"
        banner += "###################################\n"
        banner += "-> Use 'Add Function Model' to hook these functions"

        print(banner)


def create_client_stub() -> ManticoreUIStub:
    return ManticoreUIStub(
        grpc.insecure_channel(
            "localhost:50010",
            options=[
                (
                    "grpc.service_config",
                    json.dumps(
                        {
                            "methodConfig": [
                                {
                                    "name": [{"service": "muicore.ManticoreUI"}],
                                    "retryPolicy": {
                                        "maxAttempts": 5,
                                        "initialBackoff": "1s",
                                        "maxBackoff": "10s",
                                        "backoffMultiplier": 2,
                                        "retryableStatusCodes": ["UNAVAILABLE"],
                                    },
                                }
                            ]
                        }
                    ),
                )
            ],
        )
    )
