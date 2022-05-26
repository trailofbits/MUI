import os
from typing import Callable, List, Optional, Final, Set
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


@dataclass()
class MUIStateData:
    id: int
    pc: Optional[int]
    parent_id: Optional[int]
    children_ids: Set[int]


def navigate_to_state(bv: BinaryView, state_data: MUIStateData) -> None:
    """Navigate to the current instruction of a given state"""

    if state_data.pc is not None:
        bv.navigate(bv.view, state_data.pc)
    else:
        show_message_box(
            "[MUI] No instruction information available",
            f"State {state_data.id} doesn't contain any instruction information.",
            MessageBoxButtonSet.OKButtonSet,
            MessageBoxIcon.ErrorIcon,
        )


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
    func: Callable


def get_function_models() -> List[MUIFunctionModel]:
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
