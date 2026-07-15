"""
Generic SiLA2 device inspector. Loads FDL feature definitions where available;
falls back to feature identifiers from discovery.

Per-feature command/property wire encoding and decoding uses dynamically
constructed protobuf messages (see fdl_types.py) built from the FDL itself,
not guessed from raw bytes. The hand-rolled varint/LEN helpers below
(_collect_values et al.) are kept only to extract the embedded FDL XML string
from SiLAService.GetFeatureDefinition's own response - a fixed, well-known
shape that doesn't need per-feature schema knowledge to read.
"""
from __future__ import annotations

import struct
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element

import grpc
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from ..discovery import DiscoveredServer
from .fdl_types import (
    DataTypeInfo, FeatureMessageBuilder, display_value, format_label,
    resolve_datatype, set_field_value, validate_value,
)

_FDL_NS   = "http://www.sila-standard.org"
_SS_BASE  = "/sila2.org.silastandard.core.silaservice.v1.SiLAService"
_TIMEOUT  = 5.0



def _varint(n: int) -> bytes:
    buf = []
    while n > 0x7f:
        buf.append((n & 0x7f) | 0x80)
        n >>= 7
    buf.append(n & 0x7f)
    return bytes(buf)


def _ldelim(field: int, data: bytes) -> bytes:
    return _varint((field << 3) | 2) + _varint(len(data)) + data


def _encode_sstring(s: str) -> bytes:
    return _ldelim(1, s.encode())


def _encode_fdl_params(feature_id: str) -> bytes:
    return _ldelim(1, _encode_sstring(feature_id))


def _decode_varint(data: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        b = data[pos]; pos += 1
        result |= (b & 0x7f) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7


def _collect_values(data: bytes, out: list[str]) -> None:
    """Recursively extract all human-readable values from a protobuf blob."""
    i = 0
    while i < len(data):
        try:
            tag, i = _decode_varint(data, i)
        except (IndexError, ValueError):
            break
        wt = tag & 0x7
        if wt == 0:  # varint (int, bool)
            try:
                val, i = _decode_varint(data, i)
                out.append("true" if val == 1 else "false" if val == 0 else str(val))
            except (IndexError, ValueError):
                break
        elif wt == 1:  # 64-bit (double)
            if i + 8 <= len(data):
                out.append(f"{struct.unpack_from('<d', data, i)[0]:.6g}")
                i += 8
            else:
                break
        elif wt == 2:  # length-delimited (string or nested message)
            try:
                ln, i = _decode_varint(data, i)
            except (IndexError, ValueError):
                break
            chunk = data[i:i + ln]; i += ln
            try:
                s = chunk.decode("utf-8")
                if s and all(c.isprintable() or c in "\n\r\t" for c in s):
                    out.append(s)
                    continue
            except UnicodeDecodeError:
                pass
            _collect_values(chunk, out)  # recurse as nested message
        elif wt == 5:  # 32-bit (float)
            if i + 4 <= len(data):
                out.append(f"{struct.unpack_from('<f', data, i)[0]:.6g}")
                i += 4
            else:
                break
        else:
            break



def _t(name: str) -> str:
    return f"{{{_FDL_NS}}}{name}"


def _txt(el: Element, tag: str) -> str:
    c = el.find(_t(tag))
    return (c.text or "").strip() if c is not None else ""


def _dtype(el: Element) -> DataTypeInfo:
    dt = el.find(_t("DataType"))
    return resolve_datatype(dt) if dt is not None else DataTypeInfo(kind="unsupported")


def _parse_fdl(xml_str: str, feature_id: str) -> dict:
    """
    Parse FDL into a dict of commands/properties (each param/response/property
    carries both a "type" display label and a "dtype" DataTypeInfo for
    widget-building), plus a "builder" FeatureMessageBuilder with every needed
    message already declared and finalized - ready for get_message_class().
    """
    root = ET.fromstring(xml_str)

    def params(parent: Element, tag: str) -> list[dict]:
        return [
            {
                "id":    _txt(p, "Identifier"),
                "name":  _txt(p, "DisplayName") or _txt(p, "Identifier"),
                "dtype": _dtype(p),
                "type":  format_label(_dtype(p)),
                "desc":  _txt(p, "Description"),
            }
            for p in parent.findall(_t(tag))
        ]

    commands = [
        {
            "id":        _txt(c, "Identifier"),
            "name":      _txt(c, "DisplayName") or _txt(c, "Identifier"),
            "desc":      _txt(c, "Description"),
            "observable": _txt(c, "Observable").lower() == "yes",
            "params":    params(c, "Parameter"),
            "responses": params(c, "Response"),
        }
        for c in root.findall(_t("Command"))
    ]
    properties = [
        {
            "id":         _txt(p, "Identifier"),
            "name":       _txt(p, "DisplayName") or _txt(p, "Identifier"),
            "desc":       _txt(p, "Description"),
            "observable": _txt(p, "Observable").lower() == "yes",
            "dtype":      _dtype(p),
            "type":       format_label(_dtype(p)),
        }
        for p in root.findall(_t("Property"))
    ]

    builder = FeatureMessageBuilder(feature_id)
    for cmd in commands:
        builder.declare_wrapper_message(
            f"{cmd['id']}_Parameters", [(p["id"], p["dtype"]) for p in cmd["params"]]
        )
        builder.declare_wrapper_message(
            f"{cmd['id']}_Responses", [(r["id"], r["dtype"]) for r in cmd["responses"]]
        )
    if any(cmd["observable"] for cmd in commands):
        builder.ensure_observable_command_messages()
    for prop in properties:
        prefix = "Subscribe" if prop["observable"] else "Get"
        builder.declare_wrapper_message(f"{prefix}_{prop['id']}_Responses", [(prop["id"], prop["dtype"])])
    builder.finalize()

    return {
        "name": _txt(root, "DisplayName"),
        "desc": _txt(root, "Description"),
        "commands": commands,
        "properties": properties,
        "builder": builder,
    }


def _rpc_base(feature_id: str) -> str:
    """Feature id to RPC base path, e.g. '.../Gantry/v0' -> '/sila2...gantry.v0.Gantry'."""
    parts = feature_id.split("/")
    if len(parts) < 3:
        return ""
    orig, cat, cls = parts[0], parts[1], parts[2]
    ver = parts[3] if len(parts) > 3 else "v1"
    return f"/sila2.{orig}.{cat}.{cls.lower()}.{ver}.{cls}"



class _FdlFetcher(QThread):
    feature_parsed = Signal(str, dict)
    feature_failed = Signal(str, str)
    done = Signal()

    def __init__(self, server: DiscoveredServer) -> None:
        super().__init__()
        self._server = server

    def run(self) -> None:
        ch = grpc.insecure_channel(f"{self._server.host}:{self._server.port}")
        try:
            for fid in self._server.features:
                if "SiLAService" in fid:
                    continue
                try:
                    raw = ch.unary_unary(f"{_SS_BASE}/GetFeatureDefinition")(
                        _encode_fdl_params(fid), timeout=_TIMEOUT
                    )
                    out = []
                    _collect_values(bytes(raw), out)
                    xml = next((s for s in out if "<Feature" in s), None)
                    if xml:
                        self.feature_parsed.emit(fid, _parse_fdl(xml, fid))
                    else:
                        self.feature_failed.emit(fid, "No FDL in response")
                except Exception as e:
                    self.feature_failed.emit(fid, str(e))
        finally:
            ch.close()
            self.done.emit()


class _PropGetter(QThread):
    result = Signal(str)

    def __init__(
        self, host: str, port: int, feature_id: str, prop_id: str, observable: bool,
        builder: FeatureMessageBuilder, dtype: DataTypeInfo,
    ) -> None:
        super().__init__()
        self._addr       = f"{host}:{port}"
        self._fid        = feature_id
        self._pid        = prop_id
        self._observable = observable
        self._builder    = builder
        self._dtype      = dtype

    def run(self) -> None:
        base = _rpc_base(self._fid)
        ch   = grpc.insecure_channel(self._addr)
        try:
            if self._observable:
                # Server-streaming: Subscribe_X - take only the first update
                path = f"{base}/Subscribe_{self._pid}"
                stream   = ch.unary_stream(path)(b"", timeout=_TIMEOUT)
                raw      = next(iter(stream))
                msg_name = f"Subscribe_{self._pid}_Responses"
            else:
                path = f"{base}/Get_{self._pid}"
                raw  = ch.unary_unary(path)(b"", timeout=_TIMEOUT)
                msg_name = f"Get_{self._pid}_Responses"
            cls = self._builder.get_message_class(msg_name)
            msg = cls()
            msg.ParseFromString(bytes(raw))
            self.result.emit(display_value(self._dtype, getattr(msg, self._pid)))
        except Exception as e:
            self.result.emit(f"Error: {e}")
        finally:
            ch.close()


class _CmdRunner(QThread):
    """Runs a plain (non-observable) command: one request, one response."""
    result = Signal(str)

    def __init__(
        self, host: str, port: int, feature_id: str, cmd_id: str, payload: bytes,
        builder: FeatureMessageBuilder, responses: list[dict],
    ) -> None:
        super().__init__()
        self._addr      = f"{host}:{port}"
        self._fid       = feature_id
        self._cid       = cmd_id
        self._payload   = payload
        self._builder   = builder
        self._responses = responses

    def run(self) -> None:
        path = f"{_rpc_base(self._fid)}/{self._cid}"
        ch = grpc.insecure_channel(self._addr)
        try:
            raw = ch.unary_unary(path)(self._payload, timeout=_TIMEOUT)
            self.result.emit(self._decode_result(bytes(raw)))
        except Exception as e:
            self.result.emit(f"Error: {e}")
        finally:
            ch.close()

    def _decode_result(self, raw: bytes) -> str:
        if not self._responses:
            return "(done)"
        cls = self._builder.get_message_class(f"{self._cid}_Responses")
        msg = cls()
        msg.ParseFromString(raw)
        return ", ".join(
            f"{r['name']}={display_value(r['dtype'], getattr(msg, r['id']))}" for r in self._responses
        )


class _ObservableCmdRunner(QThread):
    """
    Drives a SiLA ObservableCommand: initiate (get a CommandExecutionUUID),
    poll <Cmd>_Info for status/progress until finished, then fetch <Cmd>_Result.
    Wire pattern follows SiLAFramework.proto.
    """
    status = Signal(str)
    result = Signal(str)

    def __init__(
        self, host: str, port: int, feature_id: str, cmd_id: str, payload: bytes,
        builder: FeatureMessageBuilder, responses: list[dict],
    ) -> None:
        super().__init__()
        self._addr      = f"{host}:{port}"
        self._fid       = feature_id
        self._cid       = cmd_id
        self._payload   = payload
        self._builder   = builder
        self._responses = responses

    _STATUS_NAMES = {0: "waiting", 1: "running", 2: "finished", 3: "error"}

    def run(self) -> None:
        base = _rpc_base(self._fid)
        ch = grpc.insecure_channel(self._addr)
        try:
            confirmation_cls = self._builder.get_message_class("CommandConfirmation")
            conf_raw = ch.unary_unary(f"{base}/{self._cid}")(self._payload, timeout=_TIMEOUT)
            confirmation = confirmation_cls()
            confirmation.ParseFromString(bytes(conf_raw))
            uuid_bytes = confirmation.commandExecutionUUID.SerializeToString()

            info_cls = self._builder.get_message_class("ExecutionInfo")
            finished_error = False
            for raw in ch.unary_stream(f"{base}/{self._cid}_Info")(uuid_bytes, timeout=None):
                info = info_cls()
                info.ParseFromString(bytes(raw))
                status_name = self._STATUS_NAMES.get(info.commandStatus, str(info.commandStatus))
                progress = info.progressInfo.value
                self.status.emit(f"{status_name} ({progress:.0%})" if progress else status_name)
                if info.commandStatus in (2, 3):
                    finished_error = info.commandStatus == 3
                    break

            if finished_error:
                self.result.emit("Command finished with an error")
                return

            result_raw = ch.unary_unary(f"{base}/{self._cid}_Result")(uuid_bytes, timeout=_TIMEOUT)
            self.result.emit(self._decode_result(bytes(result_raw)))
        except Exception as e:
            self.result.emit(f"Error: {e}")
        finally:
            ch.close()

    def _decode_result(self, raw: bytes) -> str:
        if not self._responses:
            return "(done)"
        cls = self._builder.get_message_class(f"{self._cid}_Responses")
        msg = cls()
        msg.ParseFromString(raw)
        return ", ".join(
            f"{r['name']}={display_value(r['dtype'], getattr(msg, r['id']))}" for r in self._responses
        )



class _PropertyRow(QWidget):
    def __init__(
        self, host: str, port: int, feature_id: str, prop: dict, t: dict,
        builder: FeatureMessageBuilder, parent=None
    ) -> None:
        super().__init__(parent)
        self._host = host; self._port = port
        self._fid  = feature_id; self._prop = prop
        self._builder = builder
        self._worker: _PropGetter | None = None

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(8)

        dot = QLabel("◆")
        dot.setStyleSheet(f"color: {t['accent']}; font-size: 9pt;")
        dot.setFixedWidth(14)
        row.addWidget(dot)

        name = QLabel(prop["name"])
        name.setStyleSheet(f"color: {t['text']}; font-size: 10pt;")
        name.setMinimumWidth(140)
        row.addWidget(name)

        typ = QLabel(prop["type"])
        typ.setStyleSheet(f"color: {t['text_muted']}; font-size: 9pt;")
        typ.setFixedWidth(80)
        row.addWidget(typ)

        if prop["observable"]:
            badge = QLabel("observable")
            badge.setStyleSheet(
                f"color: {t['accent']}; font-size: 8pt; border: 1px solid {t['accent']};"
                " border-radius: 3px; padding: 0 4px;"
            )
            row.addWidget(badge)

        self._get_btn = QPushButton("Get")
        self._get_btn.setFixedSize(44, 22)
        self._get_btn.setStyleSheet(self._btn_ss(t))
        self._get_btn.clicked.connect(self._get)
        row.addWidget(self._get_btn)

        self._val_lbl = QLabel("")
        self._val_lbl.setStyleSheet(f"color: {t['text_muted']}; font-size: 9pt;")
        self._val_lbl.setWordWrap(True)
        row.addWidget(self._val_lbl, 1)

    @staticmethod
    def _btn_ss(t: dict) -> str:
        return (
            f"QPushButton {{ background: {t['bg_hover']}; color: {t['text']};"
            f" border: 1px solid {t['border']}; border-radius: 4px; font-size: 9pt; }}"
            f"QPushButton:hover {{ border-color: {t['accent']}; }}"
        )

    def _get(self) -> None:
        self._get_btn.setEnabled(False)
        self._val_lbl.setText("…")
        self._worker = _PropGetter(
            self._host, self._port, self._fid,
            self._prop["id"], self._prop["observable"],
            self._builder, self._prop["dtype"],
        )
        self._worker.result.connect(self._on_result)
        self._worker.start()

    def _on_result(self, text: str) -> None:
        self._val_lbl.setText(text)
        self._get_btn.setEnabled(True)


class _ParamInput(QWidget):
    """
    Input control(s) for one parameter, built from its DataTypeInfo:
    enum-constrained -> QComboBox, range-constrained numeric -> QSpinBox/
    QDoubleSpinBox, everything else basic -> QLineEdit. Structure recurses
    into a labeled sub-form; List renders a repeatable, addable/removable
    group of sub-forms for its element type.
    """

    def __init__(self, dtype: DataTypeInfo, t: dict, parent=None) -> None:
        super().__init__(parent)
        self._dtype = dtype
        self._t = t
        self._widget: QWidget | None = None
        self._children: list[tuple[str, "_ParamInput"]] = []  # structure: (element_id, input)
        self._list_rows: list["_ParamInput"] = []              # list: repeated inputs
        self._list_rows_layout: QVBoxLayout | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        if dtype.kind == "basic":
            self._widget = self._build_basic_widget(dtype, t)
            layout.addWidget(self._widget)
        elif dtype.kind == "structure":
            for elem_id, name, elem_dtype in dtype.elements:
                row = QHBoxLayout()
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(6)
                lbl = QLabel(name)
                lbl.setStyleSheet(f"color: {t['text_dim']}; font-size: 8pt;")
                lbl.setFixedWidth(70)
                row.addWidget(lbl)
                child = _ParamInput(elem_dtype, t)
                row.addWidget(child, 1)
                self._children.append((elem_id, child))
                layout.addLayout(row)
        elif dtype.kind == "list":
            rows_container = QWidget()
            self._list_rows_layout = QVBoxLayout(rows_container)
            self._list_rows_layout.setContentsMargins(0, 0, 0, 0)
            self._list_rows_layout.setSpacing(3)
            layout.addWidget(rows_container)

            add_btn = QPushButton("+ item")
            add_btn.setStyleSheet(
                f"QPushButton {{ background: {t['bg_hover']}; color: {t['text_muted']};"
                f" border: 1px solid {t['border']}; border-radius: 3px; font-size: 8pt; }}"
            )
            add_btn.clicked.connect(self._add_list_row)
            layout.addWidget(add_btn, alignment=Qt.AlignLeft)
        else:
            note = QLabel(dtype.unsupported_reason or "Unsupported type")
            note.setStyleSheet(f"color: {t['text_dim']}; font-size: 8pt;")
            layout.addWidget(note)

    def _build_basic_widget(self, dtype: DataTypeInfo, t: dict) -> QWidget:
        input_ss = (
            f"background: {t['bg']}; color: {t['text']}; border: 1px solid {t['border']};"
            f" border-radius: 4px; padding: 2px 6px; font-size: 9pt;"
        )
        if dtype.allowed:
            combo = QComboBox()
            combo.addItems(dtype.allowed)
            combo.setStyleSheet(input_ss)
            return combo
        if dtype.basic == "Boolean":
            combo = QComboBox()
            combo.addItems(["true", "false"])
            combo.setStyleSheet(input_ss)
            return combo
        if dtype.basic == "Integer" and (dtype.min_value is not None or dtype.max_value is not None):
            spin = QSpinBox()
            spin.setRange(
                int(float(dtype.min_value)) if dtype.min_value is not None else -2_147_483_648,
                int(float(dtype.max_value)) if dtype.max_value is not None else 2_147_483_647,
            )
            spin.setStyleSheet(input_ss)
            return spin
        if dtype.basic == "Real" and (dtype.min_value is not None or dtype.max_value is not None):
            spin = QDoubleSpinBox()
            spin.setDecimals(6)
            spin.setRange(
                float(dtype.min_value) if dtype.min_value is not None else -1e15,
                float(dtype.max_value) if dtype.max_value is not None else 1e15,
            )
            spin.setStyleSheet(input_ss)
            return spin
        line = QLineEdit()
        line.setPlaceholderText(dtype.basic or "")
        line.setStyleSheet(
            f"QLineEdit {{ {input_ss} }}"
            f"QLineEdit:focus {{ border-color: {t['accent']}; }}"
        )
        return line

    def _add_list_row(self) -> None:
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        child = _ParamInput(self._dtype.inner, self._t)
        row_layout.addWidget(child, 1)

        remove_btn = QPushButton("×")
        remove_btn.setFixedWidth(22)
        remove_btn.setStyleSheet(
            f"QPushButton {{ background: {self._t['bg_hover']}; color: {self._t['text_dim']};"
            f" border: 1px solid {self._t['border']}; border-radius: 3px; }}"
        )
        row_layout.addWidget(remove_btn)

        self._list_rows_layout.addWidget(row_widget)
        self._list_rows.append(child)

        def _remove() -> None:
            self._list_rows.remove(child)
            row_widget.setParent(None)
            row_widget.deleteLater()

        remove_btn.clicked.connect(_remove)

    def get_value(self):
        """Return a plain Python value: str/float/bool for basics, dict for
        structure (keyed by element id), list for list."""
        if self._dtype.kind == "basic":
            w = self._widget
            if isinstance(w, QComboBox):
                return w.currentText()
            if isinstance(w, (QSpinBox, QDoubleSpinBox)):
                return w.value()
            return w.text()
        if self._dtype.kind == "structure":
            return {elem_id: child.get_value() for elem_id, child in self._children}
        if self._dtype.kind == "list":
            return [row.get_value() for row in self._list_rows]
        return None

    def validate(self) -> str | None:
        """Return an error message (for display) if the current value is invalid, else None."""
        if self._dtype.kind == "basic":
            return validate_value(self._dtype, self.get_value())
        if self._dtype.kind == "structure":
            for elem_id, child in self._children:
                err = child.validate()
                if err:
                    return f"{elem_id}: {err}"
            return None
        if self._dtype.kind == "list":
            for i, row in enumerate(self._list_rows):
                err = row.validate()
                if err:
                    return f"item {i}: {err}"
            return None
        return None


class _CommandPanel(QWidget):
    def __init__(
        self, host: str, port: int, feature_id: str, cmd: dict, t: dict,
        builder: FeatureMessageBuilder, parent=None
    ) -> None:
        super().__init__(parent)
        self._host = host; self._port = port
        self._fid  = feature_id; self._cmd = cmd
        self._t    = t
        self._builder = builder
        self._worker: _CmdRunner | _ObservableCmdRunner | None = None
        self._inputs: list[tuple[str, _ParamInput]] = []  # (param_id, input)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 4, 0, 4)
        layout.setSpacing(4)

        # header
        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        arrow = QLabel("▶")
        arrow.setStyleSheet(f"color: {t['text_muted']}; font-size: 9pt;")
        arrow.setFixedWidth(14)
        hdr.addWidget(arrow)
        name = QLabel(cmd["name"])
        name.setStyleSheet(f"color: {t['text']}; font-size: 10pt; font-weight: bold;")
        hdr.addWidget(name)
        if cmd.get("observable"):
            badge = QLabel("observable")
            badge.setStyleSheet(
                f"color: {t['accent']}; font-size: 8pt; border: 1px solid {t['accent']};"
                " border-radius: 3px; padding: 0 4px;"
            )
            hdr.addWidget(badge)
        hdr.addStretch()
        layout.addLayout(hdr)

        if cmd.get("desc"):
            desc = QLabel(cmd["desc"])
            desc.setStyleSheet(f"color: {t['text_muted']}; font-size: 9pt;")
            desc.setWordWrap(True)
            desc.setContentsMargins(14, 0, 0, 0)
            layout.addWidget(desc)

        can_run = True
        for param in cmd.get("params", []):
            prow = QHBoxLayout()
            prow.setContentsMargins(14, 0, 0, 0)
            prow.setSpacing(8)

            plbl = QLabel(param["name"])
            plbl.setStyleSheet(f"color: {t['text_muted']}; font-size: 9pt;")
            plbl.setFixedWidth(120)
            plbl.setAlignment(Qt.AlignTop)
            prow.addWidget(plbl)

            tlbl = QLabel(param["type"])
            tlbl.setStyleSheet(f"color: {t['text_dim']}; font-size: 8pt;")
            tlbl.setFixedWidth(70)
            tlbl.setAlignment(Qt.AlignTop)
            prow.addWidget(tlbl)

            inp = _ParamInput(param["dtype"], t)
            prow.addWidget(inp, 1)
            self._inputs.append((param["id"], inp))
            if param["dtype"].kind == "unsupported":
                can_run = False

            layout.addLayout(prow)

        # run button + output
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(14, 2, 0, 0)
        btn_row.setSpacing(8)

        self._run_btn = QPushButton("Run")
        self._run_btn.setFixedSize(54, 24)
        self._run_btn.setEnabled(can_run)
        self._run_btn.setStyleSheet(
            f"QPushButton {{ background: {t['accent']}; color: {t['accent_text']};"
            f" border: none; border-radius: 4px; font-size: 9pt; font-weight: bold; }}"
            f"QPushButton:hover {{ background: #e06010; }}"
            f"QPushButton:disabled {{ background: {t['bg_hover']}; color: {t['text_dim']}; }}"
        )
        self._run_btn.clicked.connect(self._run)
        btn_row.addWidget(self._run_btn)

        self._out_lbl = QLabel("")
        self._out_lbl.setStyleSheet(f"color: {t['text_muted']}; font-size: 9pt;")
        self._out_lbl.setWordWrap(True)
        btn_row.addWidget(self._out_lbl, 1)
        layout.addLayout(btn_row)

        # response schema
        for resp in cmd.get("responses", []):
            rlbl = QLabel(f"  → {resp['name']}: {resp['type']}")
            rlbl.setStyleSheet(f"color: {t['text_dim']}; font-size: 8pt;")
            rlbl.setContentsMargins(14, 0, 0, 0)
            layout.addWidget(rlbl)

    def _run(self) -> None:
        for param_id, inp in self._inputs:
            err = inp.validate()
            if err:
                self._out_lbl.setText(f"{param_id}: {err}")
                return

        if self._inputs:
            params_cls = self._builder.get_message_class(f"{self._cmd['id']}_Parameters")
            params_msg = params_cls()
            for param in self._cmd["params"]:
                inp = next(i for pid, i in self._inputs if pid == param["id"])
                set_field_value(param["dtype"], getattr(params_msg, param["id"]), inp.get_value())
            payload = params_msg.SerializeToString()
        else:
            payload = b""

        self._run_btn.setEnabled(False)
        responses = self._cmd.get("responses", [])
        if self._cmd.get("observable"):
            self._out_lbl.setText("Starting…")
            self._worker = _ObservableCmdRunner(
                self._host, self._port, self._fid, self._cmd["id"], payload, self._builder, responses
            )
            self._worker.status.connect(lambda s: self._out_lbl.setText(f"Status: {s}"))
        else:
            self._out_lbl.setText("Running…")
            self._worker = _CmdRunner(
                self._host, self._port, self._fid, self._cmd["id"], payload, self._builder, responses
            )
        self._worker.result.connect(self._on_result)
        self._worker.start()

    def _on_result(self, text: str) -> None:
        self._out_lbl.setText(text)
        self._run_btn.setEnabled(True)


class _FeatureSection(QWidget):
    def __init__(
        self, host: str, port: int, feature_id: str, t: dict, parent=None
    ) -> None:
        super().__init__(parent)
        self._host = host; self._port = port
        self._fid  = feature_id; self._t = t

        parts  = feature_id.split("/")
        cls    = parts[2] if len(parts) > 2 else feature_id
        ver    = parts[3] if len(parts) > 3 else ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # collapsible header
        self._toggle = QToolButton()
        self._toggle.setArrowType(Qt.DownArrow)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(True)
        self._toggle.setStyleSheet("QToolButton { border: none; }")
        self._toggle.toggled.connect(self._on_toggle)

        self._hdr_frame = QFrame()
        self._hdr_frame.setObjectName("FeatHeader")
        self._hdr_frame.setStyleSheet(
            f"QFrame#FeatHeader {{ background: {t['bg_raised']};"
            f" border: 1px solid {t['border']}; border-radius: 6px; }}"
        )
        hdr_layout = QHBoxLayout(self._hdr_frame)
        hdr_layout.setContentsMargins(10, 6, 10, 6)
        hdr_layout.setSpacing(8)
        hdr_layout.addWidget(self._toggle)

        self._name_lbl = QLabel(cls)
        self._name_lbl.setStyleSheet(
            f"color: {t['text']}; font-size: 11pt; font-weight: bold;"
        )
        hdr_layout.addWidget(self._name_lbl)

        self._id_lbl = QLabel(feature_id)
        self._id_lbl.setStyleSheet(f"color: {t['text_dim']}; font-size: 8pt;")
        hdr_layout.addWidget(self._id_lbl)
        hdr_layout.addStretch()

        self._ver_lbl: QLabel | None = None
        if ver:
            self._ver_lbl = QLabel(ver)
            self._ver_lbl.setStyleSheet(f"color: {t['text_muted']}; font-size: 9pt;")
            hdr_layout.addWidget(self._ver_lbl)

        self._status_lbl = QLabel("Loading…")
        self._status_lbl.setStyleSheet(f"color: {t['text_dim']}; font-size: 8pt;")
        hdr_layout.addWidget(self._status_lbl)

        outer.addWidget(self._hdr_frame)

        # expandable content area
        self._content = QFrame()
        self._content.setObjectName("FeatContent")
        self._content.setStyleSheet(
            f"QFrame#FeatContent {{ background: {t['bg_surface']};"
            f" border: 1px solid {t['border']}; border-top: none;"
            f" border-radius: 0 0 6px 6px; }}"
        )
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(12, 8, 12, 10)
        self._content_layout.setSpacing(4)
        outer.addWidget(self._content)

    def set_theme(self, t: dict) -> None:
        self._t = t
        self._hdr_frame.setStyleSheet(
            f"QFrame#FeatHeader {{ background: {t['bg_raised']};"
            f" border: 1px solid {t['border']}; border-radius: 6px; }}"
        )
        self._content.setStyleSheet(
            f"QFrame#FeatContent {{ background: {t['bg_surface']};"
            f" border: 1px solid {t['border']}; border-top: none;"
            f" border-radius: 0 0 6px 6px; }}"
        )
        self._name_lbl.setStyleSheet(f"color: {t['text']}; font-size: 11pt; font-weight: bold;")
        self._id_lbl.setStyleSheet(f"color: {t['text_dim']}; font-size: 8pt;")
        self._status_lbl.setStyleSheet(f"color: {t['text_dim']}; font-size: 8pt;")
        if self._ver_lbl:
            self._ver_lbl.setStyleSheet(f"color: {t['text_muted']}; font-size: 9pt;")
        # Update dynamically-added content children
        for lbl in self._content.findChildren(QLabel):
            ss = lbl.styleSheet()
            if "font-size: 9pt" in ss:
                lbl.setStyleSheet(f"color: {t['text_muted']}; font-size: 9pt;")
            elif "font-size: 8pt" in ss:
                lbl.setStyleSheet(f"color: {t['text_dim']}; font-size: 8pt;")
            elif "font-weight: bold" in ss:
                lbl.setStyleSheet(f"color: {t['text_muted']}; font-size: 9pt; font-weight: bold;")
            else:
                lbl.setStyleSheet(f"color: {t['text']}; font-size: 10pt;")
        for btn in self._content.findChildren(QPushButton):
            btn.setStyleSheet(
                f"QPushButton {{ background: {t['bg_hover']}; color: {t['text']};"
                f" border: 1px solid {t['border']}; border-radius: 4px; font-size: 9pt; }}"
                f"QPushButton:hover {{ border-color: {t['accent']}; }}"
            )
        for inp in self._content.findChildren(QLineEdit):
            inp.setStyleSheet(
                f"QLineEdit {{ background: {t['bg']}; color: {t['text']};"
                f" border: 1px solid {t['border']}; border-radius: 3px; padding: 2px 4px; }}"
            )

    def _on_toggle(self, checked: bool) -> None:
        self._content.setVisible(checked)
        self._toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)

    def set_unavailable(self, reason: str) -> None:
        self._status_lbl.setText("definition unavailable")
        note = QLabel(f"Feature introspection not supported by this server.\n{reason}")
        note.setStyleSheet(f"color: {self._t['text_dim']}; font-size: 9pt;")
        note.setWordWrap(True)
        self._content_layout.addWidget(note)

    def populate(self, info: dict) -> None:
        self._status_lbl.setText("")
        t = self._t

        if info.get("desc"):
            desc = QLabel(info["desc"])
            desc.setStyleSheet(f"color: {t['text_muted']}; font-size: 9pt;")
            desc.setWordWrap(True)
            self._content_layout.addWidget(desc)
            self._content_layout.addSpacing(4)

        builder = info["builder"]

        if info.get("commands"):
            self._section_label("Commands")
            sep = QFrame(); sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet(f"color: {t['border']};")
            self._content_layout.addWidget(sep)
            for cmd in info["commands"]:
                self._content_layout.addWidget(
                    _CommandPanel(self._host, self._port, self._fid, cmd, t, builder)
                )

        if info.get("properties"):
            if info.get("commands"):
                self._content_layout.addSpacing(4)
            self._section_label("Properties")
            sep = QFrame(); sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet(f"color: {t['border']};")
            self._content_layout.addWidget(sep)
            for prop in info["properties"]:
                self._content_layout.addWidget(
                    _PropertyRow(self._host, self._port, self._fid, prop, t, builder)
                )

        if not info.get("commands") and not info.get("properties"):
            note = QLabel("No commands or properties defined.")
            note.setStyleSheet(f"color: {t['text_dim']}; font-size: 9pt;")
            self._content_layout.addWidget(note)

    def _section_label(self, text: str) -> None:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {self._t['text_muted']}; font-size: 9pt; font-weight: bold;"
        )
        self._content_layout.addWidget(lbl)



class GenericDeviceWidget(QWidget):
    """Generic SiLA2 server inspector panel, used when no dedicated widget exists."""

    def __init__(self, server: DiscoveredServer, t: dict, parent=None) -> None:
        super().__init__(parent)
        self._server  = server
        self._t       = t
        self._sections: dict[str, _FeatureSection] = {}
        self._fetcher: _FdlFetcher | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header(server, t))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner = QWidget()
        self._feat_layout = QVBoxLayout(inner)
        self._feat_layout.setContentsMargins(12, 12, 12, 12)
        self._feat_layout.setSpacing(8)

        for fid in server.features:
            if "SiLAService" in fid:
                continue
            sec = _FeatureSection(server.host, server.port, fid, t)
            self._sections[fid] = sec
            self._feat_layout.addWidget(sec)

        self._feat_layout.addStretch()
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        self._status_bar = QLabel("Fetching feature definitions…")
        self._status_bar.setContentsMargins(12, 4, 12, 4)
        self._status_bar.setStyleSheet(
            f"color: {t['text_dim']}; font-size: 8pt;"
            f" background: {t['bg_raised']}; border-top: 1px solid {t['border']};"
        )
        root.addWidget(self._status_bar)

        self._start_fetch()

    @staticmethod
    def _build_header(server: DiscoveredServer, t: dict) -> QFrame:
        frame = QFrame()
        frame.setObjectName("DeviceHeader")
        frame.setStyleSheet(
            f"QFrame#DeviceHeader {{ background: {t['bg_raised']};"
            f" border-bottom: 1px solid {t['border']}; }}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(3)

        name = QLabel(server.name)
        name.setStyleSheet(
            f"color: {t['text']}; font-size: 13pt; font-weight: bold;"
        )
        layout.addWidget(name)

        addr = QLabel(f"{server.host}:{server.port}")
        addr.setStyleSheet(f"color: {t['text_muted']}; font-size: 9pt;")
        layout.addWidget(addr)

        if server.uuid:
            uuid = QLabel(f"UUID  {server.uuid}")
            uuid.setStyleSheet(f"color: {t['text_dim']}; font-size: 8pt;")
            layout.addWidget(uuid)

        if server.description:
            desc = QLabel(server.description)
            desc.setStyleSheet(f"color: {t['text_muted']}; font-size: 9pt;")
            desc.setWordWrap(True)
            layout.addWidget(desc)

        return frame

    def _start_fetch(self) -> None:
        self._fetcher = _FdlFetcher(self._server)
        self._fetcher.feature_parsed.connect(self._on_feature_parsed)
        self._fetcher.feature_failed.connect(self._on_feature_failed)
        self._fetcher.done.connect(self._on_fetch_done)
        self._fetcher.start()

    def _on_feature_parsed(self, fid: str, info: dict) -> None:
        if fid in self._sections:
            self._sections[fid].populate(info)

    def _on_feature_failed(self, fid: str, reason: str) -> None:
        if fid in self._sections:
            self._sections[fid].set_unavailable(reason)

    def _on_fetch_done(self) -> None:
        n = len(self._sections)
        self._status_bar.setText(
            f"{n} feature{'s' if n != 1 else ''} • {self._server.host}:{self._server.port}"
        )

    def set_theme(self, t: dict) -> None:
        """Replace the active theme dict and propagate it to all feature sections."""
        self._t = t
        self._status_bar.setStyleSheet(
            f"color: {t['text_dim']}; font-size: 8pt;"
            f" background: {t['bg_raised']}; border-top: 1px solid {t['border']};"
        )
        # Update header labels via findChildren (no stored refs - it's a static method)
        for lbl in self.findChildren(QLabel):
            ss = lbl.styleSheet()
            if "font-size: 8pt" in ss:
                lbl.setStyleSheet(f"color: {t['text_dim']}; font-size: 8pt;")
            elif "font-size: 9pt" in ss:
                lbl.setStyleSheet(f"color: {t['text_muted']}; font-size: 9pt;")
            elif "font-size: 13pt" in ss or "font-weight: bold" in ss:
                lbl.setStyleSheet(f"color: {t['text']}; font-size: 13pt; font-weight: bold;")
        # Update all feature sections
        for sec in self._sections.values():
            sec.set_theme(t)
