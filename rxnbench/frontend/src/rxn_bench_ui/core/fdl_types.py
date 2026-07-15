"""
Dynamic protobuf construction from SiLA FDL data types.

The generic device widget (generic_device.py) talks to devices whose schema
isn't known until runtime, so there are no compiled protobuf stubs to import.
This module builds typed protobuf message classes on the fly - one per feature,
from its FDL - using google.protobuf's descriptor_pool and message_factory, so
fields get exact types (int64 vs bool vs enum) instead of guessing from raw
wire bytes.

Wire shapes follow SiLAFramework.proto (ships with unitelabs-cdk / sila2) and
were verified against a running mock server (see docs/ai/CURRENT_STATE.md
section 9):

- Every SiLA Basic type is a one-field wrapper message
  (e.g. Real{double value=1}, String{string value=1}).
- A Structure is a flat message with one field per element at sequential field
  numbers from 1, each a wrapper type or nested Structure. No extra indirection.
- Integer is plain proto3 int64, not zigzag/sint64.
- There is no "UInteger" SiLA basic type; the real Basic types are String,
  Integer, Real, Boolean, Binary, Date, Time, Timestamp, and Any.
"""
from __future__ import annotations

import dataclasses
import re

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from google.protobuf.message import Message

_FDL_NS = "http://www.sila-standard.org"


def _t(name: str) -> str:
    return f"{{{_FDL_NS}}}{name}"


def _txt(el, tag: str) -> str:
    c = el.find(_t(tag))
    return (c.text or "").strip() if c is not None else ""


# Structured data type info

@dataclasses.dataclass
class DataTypeInfo:
    """Parsed FDL <DataType>, structured enough to build a protobuf message and
    a Qt input widget, not just a display label."""

    kind: str  # "basic" | "structure" | "list" | "unsupported"
    basic: str | None = None                    # SiLA basic type name (kind == "basic")
    allowed: list[str] | None = None             # enum constraint values, if any
    min_value: str | None = None
    max_value: str | None = None
    min_exclusive: bool = False
    max_exclusive: bool = False
    elements: list[tuple[str, str, "DataTypeInfo"]] | None = None  # (id, display_name, dtype), kind == "structure"
    inner: "DataTypeInfo | None" = None          # element type, kind == "list"
    unsupported_reason: str | None = None        # kind == "unsupported"


_BASIC_TYPES = {"String", "Integer", "Real", "Boolean", "Date", "Time", "Timestamp", "Binary", "Any"}


def resolve_datatype(dt) -> DataTypeInfo:
    """Parse an FDL <DataType> element into a DataTypeInfo tree."""
    basic = dt.find(_t("Basic"))
    if basic is not None and basic.text:
        name = basic.text.strip()
        if name in _BASIC_TYPES:
            return DataTypeInfo(kind="basic", basic=name)
        return DataTypeInfo(kind="unsupported", unsupported_reason=f"Unknown basic type {name!r}")

    constrained = dt.find(_t("Constrained"))
    if constrained is not None:
        inner_dt = constrained.find(_t("DataType"))
        base = resolve_datatype(inner_dt) if inner_dt is not None else DataTypeInfo(kind="unsupported")
        constraints = constrained.find(_t("Constraints"))
        if constraints is not None:
            allowed = [v.text for v in constraints.findall(_t("Set") + "/" + _t("Value")) if v.text]
            if allowed:
                base.allowed = allowed
            min_v = constraints.findtext(_t("MinimalInclusive"))
            min_x = constraints.findtext(_t("MinimalExclusive"))
            max_v = constraints.findtext(_t("MaximalInclusive"))
            max_x = constraints.findtext(_t("MaximalExclusive"))
            if min_v or min_x:
                base.min_value = min_v or min_x
                base.min_exclusive = min_x is not None
            if max_v or max_x:
                base.max_value = max_v or max_x
                base.max_exclusive = max_x is not None
        return base

    structure = dt.find(_t("Structure"))
    if structure is not None:
        elements = []
        for el in structure.findall(_t("Element")):
            el_dt = el.find(_t("DataType"))
            elements.append((
                _txt(el, "Identifier"),
                _txt(el, "DisplayName") or _txt(el, "Identifier"),
                resolve_datatype(el_dt) if el_dt is not None else DataTypeInfo(kind="unsupported"),
            ))
        return DataTypeInfo(kind="structure", elements=elements)

    lst = dt.find(_t("List"))
    if lst is not None:
        inner_dt = lst.find(_t("DataType"))
        inner = resolve_datatype(inner_dt) if inner_dt is not None else DataTypeInfo(kind="unsupported")
        return DataTypeInfo(kind="list", inner=inner)

    return DataTypeInfo(kind="unsupported", unsupported_reason="No recognized DataType child")


def format_label(info: DataTypeInfo) -> str:
    """Human-readable type label, e.g. 'Real [0...100]' or 'String (mid | low | high | clear)'."""
    if info.kind == "unsupported":
        return info.unsupported_reason or "Unsupported"
    if info.kind == "structure":
        return "Structure"
    if info.kind == "list":
        return f"List of {format_label(info.inner)}"

    base = info.basic or "Any"
    if info.allowed:
        return f"{base} ({' | '.join(info.allowed)})"
    if info.min_value or info.max_value:
        return f"{base} [{info.min_value or ''}...{info.max_value or ''}]"
    return base


# Basic-type wrapper message shapes (from SiLAFramework.proto)

FD = descriptor_pb2.FieldDescriptorProto

_SCALAR_BASIC_FIELDS: dict[str, tuple[int, str]] = {
    # basic type name -> (proto field type, field name)
    "String":  (FD.TYPE_STRING, "value"),
    "Integer": (FD.TYPE_INT64,  "value"),
    "Real":    (FD.TYPE_DOUBLE, "value"),
    "Boolean": (FD.TYPE_BOOL,   "value"),
}

# Compound basic wrapper shapes: message name -> [(field_name, proto_type)]
_TIMEZONE_FIELDS = [("hours", FD.TYPE_INT32), ("minutes", FD.TYPE_UINT32)]
_COMPOUND_BASIC_FIELDS: dict[str, list[tuple[str, int, str | None]]] = {
    # field_name, proto_type, nested_type_name (None if scalar)
    "Date":      [("day", FD.TYPE_UINT32, None), ("month", FD.TYPE_UINT32, None),
                  ("year", FD.TYPE_UINT32, None), ("timezone", FD.TYPE_MESSAGE, "Timezone")],
    "Time":      [("second", FD.TYPE_UINT32, None), ("minute", FD.TYPE_UINT32, None),
                  ("hour", FD.TYPE_UINT32, None), ("timezone", FD.TYPE_MESSAGE, "Timezone"),
                  ("millisecond", FD.TYPE_UINT32, None)],
    "Timestamp": [("second", FD.TYPE_UINT32, None), ("minute", FD.TYPE_UINT32, None),
                  ("hour", FD.TYPE_UINT32, None), ("day", FD.TYPE_UINT32, None),
                  ("month", FD.TYPE_UINT32, None), ("year", FD.TYPE_UINT32, None),
                  ("timezone", FD.TYPE_MESSAGE, "Timezone"), ("millisecond", FD.TYPE_UINT32, None)],
    "Binary":    [("value", FD.TYPE_BYTES, None), ("binaryTransferUUID", FD.TYPE_STRING, None)],
    "Any":       [("type", FD.TYPE_STRING, None), ("payload", FD.TYPE_BYTES, None)],
}


def _sanitize_package(feature_id: str) -> str:
    """Turn a SiLA feature identifier into a valid, unique proto package name."""
    return "fdl_dynamic." + re.sub(r"[^A-Za-z0-9_]", "_", feature_id)


class FeatureMessageBuilder:
    """
    Builds a FileDescriptorProto for one feature's commands and properties,
    registers it in a private DescriptorPool, and returns message classes keyed
    by SiLA RPC message name (e.g. "MoveTo_Parameters").

    Use one instance per (server, feature) fetch; message/package names are only
    unique within that scope.
    """

    def __init__(self, feature_id: str) -> None:
        self._feature_id = feature_id
        self._package = _sanitize_package(feature_id)
        self._pool = descriptor_pool.DescriptorPool()
        self._file = descriptor_pb2.FileDescriptorProto()
        self._file.name = f"{self._package}.proto"
        self._file.package = self._package
        self._file.syntax = "proto3"
        self._defined: set[str] = set()
        self._structure_names: dict[int, str] = {}  # id(elements) -> message name, for de-dup
        self._next_anon_id = 0
        self._finalized = False

    # Basic wrapper messages, built lazily on first use

    def _ensure_basic_message(self, basic: str) -> str:
        name = basic
        if name in self._defined:
            return name
        msg = self._file.message_type.add()
        msg.name = name
        if basic in _SCALAR_BASIC_FIELDS:
            ftype, fname = _SCALAR_BASIC_FIELDS[basic]
            self._add_field(msg, fname, 1, ftype)
        elif basic in _COMPOUND_BASIC_FIELDS:
            if basic in ("Date", "Time", "Timestamp"):
                self._ensure_timezone_message()
            for i, (fname, ftype, nested) in enumerate(_COMPOUND_BASIC_FIELDS[basic], start=1):
                type_name = f".{self._package}.{nested}" if nested else None
                self._add_field(msg, fname, i, ftype, type_name)
        else:
            raise ValueError(f"Unknown basic type {basic!r}")
        self._defined.add(name)
        return name

    def _ensure_timezone_message(self) -> str:
        name = "Timezone"
        if name in self._defined:
            return name
        msg = self._file.message_type.add()
        msg.name = name
        for i, (fname, ftype) in enumerate(_TIMEZONE_FIELDS, start=1):
            self._add_field(msg, fname, i, ftype)
        self._defined.add(name)
        return name

    @staticmethod
    def _add_field(msg, name: str, number: int, ftype: int, type_name: str | None = None) -> None:
        f = msg.field.add()
        f.name = name
        f.number = number
        f.type = ftype
        f.label = FD.LABEL_OPTIONAL
        if type_name:
            f.type_name = type_name

    # Structure/list message construction

    def _ensure_structure_message(self, info: DataTypeInfo, hint_name: str) -> str:
        """Build (or reuse) a message type for a Structure DataTypeInfo, return its local name."""
        key = id(info.elements)
        if key in self._structure_names:
            return self._structure_names[key]

        name = self._unique_name(hint_name)
        msg = self._file.message_type.add()
        msg.name = name
        for i, (elem_id, _display, elem_type) in enumerate(info.elements, start=1):
            self._add_typed_field(msg, elem_id, i, elem_type, hint_name=f"{name}_{elem_id}")
        self._structure_names[key] = name
        return name

    def _unique_name(self, hint: str) -> str:
        base = re.sub(r"[^A-Za-z0-9_]", "_", hint) or "Msg"
        name = base
        while name in self._defined:
            self._next_anon_id += 1
            name = f"{base}_{self._next_anon_id}"
        self._defined.add(name)
        return name

    def _add_typed_field(self, msg, field_name: str, number: int, info: DataTypeInfo, hint_name: str) -> None:
        """Add a field of arbitrary DataTypeInfo (basic/structure/list) to msg."""
        if info.kind == "basic":
            type_name = self._ensure_basic_message(info.basic)
            self._add_field(msg, field_name, number, FD.TYPE_MESSAGE, f".{self._package}.{type_name}")
        elif info.kind == "structure":
            type_name = self._ensure_structure_message(info, hint_name)
            self._add_field(msg, field_name, number, FD.TYPE_MESSAGE, f".{self._package}.{type_name}")
        elif info.kind == "list":
            inner = info.inner
            if inner.kind == "basic":
                type_name = self._ensure_basic_message(inner.basic)
            elif inner.kind == "structure":
                type_name = self._ensure_structure_message(inner, hint_name + "_Item")
            else:
                raise ValueError(f"Unsupported list element type: {inner.kind}")
            f = msg.field.add()
            f.name = field_name
            f.number = number
            f.type = FD.TYPE_MESSAGE
            f.type_name = f".{self._package}.{type_name}"
            f.label = FD.LABEL_REPEATED
        else:
            raise ValueError(f"Cannot build a field for unsupported type: {info.unsupported_reason}")

    # Observable-command framework messages (SiLAFramework.proto)

    def ensure_observable_command_messages(self) -> None:
        """
        Declare the fixed framework messages needed to drive an
        ObservableCommand: CommandExecutionUUID, CommandConfirmation, Duration,
        and ExecutionInfo (with its CommandStatus enum). The flow is: initiate
        -> get a CommandExecutionUUID -> poll <Cmd>_Info for ExecutionInfo ->
        fetch <Cmd>_Result.
        """
        if "ExecutionInfo" in self._defined:
            return

        self._ensure_basic_message("Real")

        uuid_msg = self._file.message_type.add()
        uuid_msg.name = "CommandExecutionUUID"
        self._add_field(uuid_msg, "value", 1, FD.TYPE_STRING)
        self._defined.add("CommandExecutionUUID")

        duration_msg = self._file.message_type.add()
        duration_msg.name = "Duration"
        self._add_field(duration_msg, "seconds", 1, FD.TYPE_INT64)
        self._add_field(duration_msg, "nanos", 2, FD.TYPE_INT32)
        self._defined.add("Duration")

        confirmation_msg = self._file.message_type.add()
        confirmation_msg.name = "CommandConfirmation"
        self._add_field(confirmation_msg, "commandExecutionUUID", 1, FD.TYPE_MESSAGE,
                         f".{self._package}.CommandExecutionUUID")
        self._add_field(confirmation_msg, "lifetimeOfExecution", 2, FD.TYPE_MESSAGE,
                         f".{self._package}.Duration")
        self._defined.add("CommandConfirmation")

        exec_info_msg = self._file.message_type.add()
        exec_info_msg.name = "ExecutionInfo"
        status_enum = exec_info_msg.enum_type.add()
        status_enum.name = "CommandStatus"
        for i, label in enumerate(("waiting", "running", "finishedSuccessfully", "finishedWithError")):
            v = status_enum.value.add()
            v.name = label
            v.number = i
        self._add_field(exec_info_msg, "commandStatus", 1, FD.TYPE_ENUM,
                         f".{self._package}.ExecutionInfo.CommandStatus")
        self._add_field(exec_info_msg, "progressInfo", 2, FD.TYPE_MESSAGE, f".{self._package}.Real")
        self._add_field(exec_info_msg, "estimatedRemainingTime", 3, FD.TYPE_MESSAGE, f".{self._package}.Duration")
        self._add_field(exec_info_msg, "updatedLifetimeOfExecution", 4, FD.TYPE_MESSAGE, f".{self._package}.Duration")
        self._defined.add("ExecutionInfo")

    # Top-level command/property wrapper messages

    def declare_wrapper_message(self, name: str, fields: list[tuple[str, DataTypeInfo]]) -> None:
        """
        Register a top-level message named *name*, one field per
        (field_name, DataTypeInfo) pair at sequential field numbers from 1,
        matching SiLA's Parameters/Responses convention.

        Call finalize() once all messages are declared, then
        get_message_class() to retrieve the class.
        """
        if name in self._defined:
            return
        msg = self._file.message_type.add()
        msg.name = name
        for i, (field_name, dtype) in enumerate(fields, start=1):
            self._add_typed_field(msg, field_name, i, dtype, hint_name=f"{name}_{field_name}")
        self._defined.add(name)

    def finalize(self) -> None:
        """Register the built FileDescriptorProto with the pool. Call exactly once,
        after all declare_wrapper_message() calls; a pool file can't be mutated afterward."""
        if self._finalized:
            return
        self._pool.Add(self._file)
        self._finalized = True

    def get_message_class(self, name: str) -> type[Message]:
        """Look up a message declared via declare_wrapper_message(). Requires finalize() first."""
        descriptor = self._pool.FindMessageTypeByName(f"{self._package}.{name}")
        return message_factory.GetMessageClass(descriptor)


# Value <-> message bridge (Qt-independent; generic_device.py's widgets sit on top)

def display_value(info: DataTypeInfo, field_msg) -> str:
    """Convert a decoded wrapper-message field into a human-readable string."""
    if info.kind == "basic":
        b = info.basic
        if b in ("String", "Integer", "Real", "Boolean"):
            return str(field_msg.value)
        if b == "Date":
            return f"{field_msg.year:04d}-{field_msg.month:02d}-{field_msg.day:02d}"
        if b == "Time":
            return (f"{field_msg.hour:02d}:{field_msg.minute:02d}:{field_msg.second:02d}"
                    f".{field_msg.millisecond:03d}")
        if b == "Timestamp":
            return (f"{field_msg.year:04d}-{field_msg.month:02d}-{field_msg.day:02d} "
                    f"{field_msg.hour:02d}:{field_msg.minute:02d}:{field_msg.second:02d}"
                    f".{field_msg.millisecond:03d}")
        if b == "Binary":
            return (f"<binary {len(field_msg.value)} bytes>" if field_msg.value
                    else f"<binary transfer {field_msg.binaryTransferUUID}>")
        if b == "Any":
            return f"<Any type={field_msg.type!r} {len(field_msg.payload)} bytes>"
        return "(unsupported)"
    if info.kind == "structure":
        parts = [f"{name}={display_value(dtype, getattr(field_msg, elem_id))}"
                 for elem_id, name, dtype in info.elements]
        return "{" + ", ".join(parts) + "}"
    if info.kind == "list":
        return "[" + ", ".join(display_value(info.inner, item) for item in field_msg) + "]"
    return info.unsupported_reason or "(unsupported)"


def set_field_value(info: DataTypeInfo, field_msg, value) -> None:
    """Set a wrapper-message field from a plain Python value (as produced by
    a Qt input widget: str/float/bool for basics, dict for structure,
    list for list)."""
    if info.kind == "basic":
        b = info.basic
        if b == "String":
            field_msg.value = str(value)
        elif b == "Integer":
            field_msg.value = int(value)
        elif b == "Real":
            field_msg.value = float(value)
        elif b == "Boolean":
            field_msg.value = bool(value)
        else:
            raise ValueError(f"Encoding {b!r} input is not supported in the generic UI yet")
        return
    if info.kind == "structure":
        for elem_id, _name, dtype in info.elements:
            set_field_value(dtype, getattr(field_msg, elem_id), value[elem_id])
        return
    if info.kind == "list":
        for item_value in value:
            set_field_value(info.inner, field_msg.add(), item_value)
        return
    raise ValueError(f"Cannot encode unsupported type: {info.unsupported_reason}")


def validate_value(info: DataTypeInfo, value) -> str | None:
    """Return an error message if *value* violates info's constraints, else None."""
    if info.kind != "basic":
        return None
    if info.allowed is not None and value not in info.allowed:
        return f"Must be one of: {', '.join(info.allowed)}"
    if info.basic in ("Integer", "Real") and (info.min_value is not None or info.max_value is not None):
        try:
            n = float(value)
        except (TypeError, ValueError):
            return "Must be a number"
        if info.min_value is not None:
            lo = float(info.min_value)
            if n < lo or (info.min_exclusive and n == lo):
                return f"Must be {'>' if info.min_exclusive else '>='} {info.min_value}"
        if info.max_value is not None:
            hi = float(info.max_value)
            if n > hi or (info.max_exclusive and n == hi):
                return f"Must be {'<' if info.max_exclusive else '<='} {info.max_value}"
    return None
