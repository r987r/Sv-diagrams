#!/usr/bin/env python3
"""
generate_diagram_meta.py

Transforms blockify metadata JSON files into Three.js diagram metadata.
Reads VIP (UVM verification IP) and RTL module metadata from the blockify
repository and generates positioned, connected diagram JSON for the viewer.

Usage:
    python3 scripts/generate_diagram_meta.py [--input-dir DIR] [--output-dir DIR]
"""

import argparse
import json
import math
import os
import sys
import urllib.request


BLOCKIFY_RAW = (
    "https://raw.githubusercontent.com/r987r/blockify/main/src/example_meta"
)

# ── colour palette (hex strings for JSON) ────────────────────────────────
PALETTE = [
    "#42A5F5", "#66BB6A", "#FFA726", "#AB47BC", "#EF5350",
    "#26C6DA", "#EC407A", "#8D6E63", "#78909C", "#D4E157",
    "#5C6BC0", "#29B6F6", "#FFCA28", "#7E57C2", "#26A69A",
]

CLK_COLOR = "#00E676"
RST_COLOR = "#FF5252"
SIGNAL_COLOR = "#FFC107"
TLM_COLOR = "#29B6F6"
BUS_COLOR = "#FFC107"


# ── helpers ───────────────────────────────────────────────────────────────

def _colour(idx):
    return PALETTE[idx % len(PALETTE)]


def _download_json(filename, cache_dir):
    """Download a blockify metadata JSON (with local caching)."""
    cached = os.path.join(cache_dir, filename)
    if os.path.exists(cached):
        with open(cached) as f:
            return json.load(f)
    url = f"{BLOCKIFY_RAW}/{filename}"
    print(f"  Downloading {url} …")
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        os.makedirs(cache_dir, exist_ok=True)
        with open(cached, "w") as f:
            json.dump(data, f)
        return data
    except Exception as exc:
        print(f"  ⚠ Could not download {filename}: {exc}", file=sys.stderr)
        return None


def _layout_grid(items, cols=None, spacing_x=10, spacing_z=8, y=0):
    """Assign grid positions to a list of items.  Returns [(item, x, y, z)]."""
    n = len(items)
    if n == 0:
        return []
    if cols is None:
        cols = max(1, math.ceil(math.sqrt(n)))
    out = []
    for i, item in enumerate(items):
        col = i % cols
        row = i // cols
        x = (col - (cols - 1) / 2) * spacing_x
        z = (row - (math.ceil(n / cols) - 1) / 2) * spacing_z
        out.append((item, x, y, z))
    return out


def _port_summary(ports):
    """Create a compact port summary dict."""
    inputs = [p for p in ports if p.get("direction") == "In"]
    outputs = [p for p in ports if p.get("direction") == "Out"]
    inouts = [p for p in ports if p.get("direction") == "InOut"]
    return {
        "inputs": len(inputs),
        "outputs": len(outputs),
        "inouts": len(inouts),
        "total_bits_in": sum(p.get("width", 1) for p in inputs),
        "total_bits_out": sum(p.get("width", 1) for p in outputs),
        "port_names_in": [p["name"] for p in inputs],
        "port_names_out": [p["name"] for p in outputs],
    }


# ── VIP (UVC) diagram builder ────────────────────────────────────────────

def build_vip_diagram(meta, design_name, description):
    """Build a diagram JSON from a VIP metadata file."""
    modules = {}
    instances = []
    connections = []
    groups = []
    instance_idx = 0

    protocol = meta.get("vip_info", {}).get("protocol", design_name)
    pkgs = meta.get("packages", [])
    ifaces = meta.get("interfaces", [])
    arch = meta.get("architecture", {})

    # ── Build module definitions from packages ────────────────────────
    # Environment-level components
    env_classes = []
    agent_classes = {"master": [], "slave": []}
    seq_classes = []
    test_classes = []
    other_classes = []

    for pkg in pkgs:
        pkg_name = pkg.get("name", "")
        classes = pkg.get("classes", [])
        pkg_lower = pkg_name.lower()
        for cls in classes:
            cls_name = cls.get("name", "")
            base = cls.get("base_class", "")
            role = _classify_uvm_class(cls_name, base, pkg_lower)
            cls["_role"] = role
            cls["_pkg"] = pkg_name
            if role == "env":
                env_classes.append(cls)
            elif role == "agent_master":
                agent_classes["master"].append(cls)
            elif role == "agent_slave":
                agent_classes["slave"].append(cls)
            elif role in ("sequence", "virtual_sequence"):
                seq_classes.append(cls)
            elif role == "test":
                test_classes.append(cls)
            else:
                other_classes.append(cls)

    # ── Create module defs for key UVM components ─────────────────────
    # Testbench
    modules["testbench"] = {
        "description": f"{protocol.upper()} UVC Testbench",
        "color": "#37474F",
        "ports": [],
    }

    # Environment
    env_info = _build_component_module(
        env_classes, "env", f"{protocol} Environment", "#1B5E20"
    )
    modules["env"] = env_info

    # Master agent
    master_info = _build_component_module(
        agent_classes["master"], "master_agent",
        f"{protocol} Master Agent", "#1565C0"
    )
    modules["master_agent"] = master_info

    # Slave agent
    slave_info = _build_component_module(
        agent_classes["slave"], "slave_agent",
        f"{protocol} Slave Agent", "#4A148C"
    )
    modules["slave_agent"] = slave_info

    # Interface
    for iface in ifaces:
        iface_name = iface.get("name", "interface")
        signals = iface.get("signals", [])
        if not signals:
            continue
        mod_key = f"iface_{iface_name}"
        modules[mod_key] = {
            "description": f"Interface: {iface_name}",
            "color": "#E65100",
            "ports": [
                {
                    "name": s.get("name", ""),
                    "direction": "InOut",
                    "width": _parse_width(s.get("range", s.get("type", ""))),
                    "type": s.get("type", "logic"),
                }
                for s in signals
            ],
        }

    # Sequences (grouped)
    if seq_classes:
        modules["sequences"] = {
            "description": f"{protocol} Sequences ({len(seq_classes)} classes)",
            "color": "#F57F17",
            "ports": [],
            "classes": [c["name"] for c in seq_classes[:20]],
            "total_classes": len(seq_classes),
        }

    # Tests (grouped)
    if test_classes:
        modules["tests"] = {
            "description": f"{protocol} Tests ({len(test_classes)} classes)",
            "color": "#880E4F",
            "ports": [],
            "classes": [c["name"] for c in test_classes[:20]],
            "total_classes": len(test_classes),
        }

    # ── Create instances with positions ───────────────────────────────
    # Layout: Testbench contains Environment contains Agents
    # Tests at top, Sequences at sides, Interface at bottom

    # Test block (top)
    if test_classes:
        instances.append({
            "name": "tests",
            "module": "tests",
            "position": {"x": 0, "y": 0, "z": -30},
            "info": {
                "class_count": len(test_classes),
                "classes": [c["name"] for c in test_classes[:15]],
            },
        })

    # Environment
    instances.append({
        "name": "env",
        "module": "env",
        "position": {"x": 0, "y": 0, "z": -16},
        "info": {
            "class_count": len(env_classes),
            "classes": [c["name"] for c in env_classes],
            "description": f"{protocol} UVM Environment",
        },
    })

    # Sequence blocks
    if seq_classes:
        instances.append({
            "name": "sequences",
            "module": "sequences",
            "position": {"x": -28, "y": 0, "z": 0},
            "info": {
                "class_count": len(seq_classes),
                "classes": [c["name"] for c in seq_classes[:15]],
            },
        })

    # Master agent
    instances.append({
        "name": "master_agent",
        "module": "master_agent",
        "position": {"x": -10, "y": 0, "z": 2},
        "info": {
            "class_count": len(agent_classes["master"]),
            "classes": [c["name"] for c in agent_classes["master"]],
            "description": f"{protocol} Master Agent",
        },
    })

    # Slave agent
    instances.append({
        "name": "slave_agent",
        "module": "slave_agent",
        "position": {"x": 10, "y": 0, "z": 2},
        "info": {
            "class_count": len(agent_classes["slave"]),
            "classes": [c["name"] for c in agent_classes["slave"]],
            "description": f"{protocol} Slave Agent",
        },
    })

    # Interfaces with signals
    iface_x = -12
    for iface in ifaces:
        iface_name = iface.get("name", "")
        signals = iface.get("signals", [])
        if not signals:
            continue
        mod_key = f"iface_{iface_name}"
        instances.append({
            "name": iface_name,
            "module": mod_key,
            "position": {"x": iface_x, "y": 0, "z": 20},
            "info": {
                "signal_count": len(signals),
                "signals": [
                    {"name": s.get("name", ""), "type": s.get("type", "")}
                    for s in signals
                ],
                "description": f"Interface: {iface_name}",
            },
        })
        iface_x += 14

    # ── Build connections ─────────────────────────────────────────────
    # Tests → Environment
    connections.append({
        "id": "test_to_env",
        "type": "hierarchy",
        "color": "#CE93D8",
        "from": {"instance": "tests", "port": "env"},
        "to": {"instance": "env", "port": "create"},
        "signals": [{"name": "UVM hierarchy", "width": 1}],
        "description": "Test creates and configures environment",
    })

    # Environment → Master Agent
    connections.append({
        "id": "env_to_master",
        "type": "tlm",
        "color": TLM_COLOR,
        "from": {"instance": "env", "port": "master_agent"},
        "to": {"instance": "master_agent", "port": "parent"},
        "signals": [{"name": "agent_handle", "width": 1}],
        "description": "Environment instantiates master agent",
    })

    # Environment → Slave Agent
    connections.append({
        "id": "env_to_slave",
        "type": "tlm",
        "color": TLM_COLOR,
        "from": {"instance": "env", "port": "slave_agent"},
        "to": {"instance": "slave_agent", "port": "parent"},
        "signals": [{"name": "agent_handle", "width": 1}],
        "description": "Environment instantiates slave agent",
    })

    # Sequences → Master Agent
    if seq_classes:
        connections.append({
            "id": "seq_to_master",
            "type": "tlm",
            "color": "#FFC107",
            "from": {"instance": "sequences", "port": "seq_item_port"},
            "to": {"instance": "master_agent", "port": "sequencer"},
            "signals": [{"name": "seq_item_port", "width": 1}],
            "description": "Sequences drive transactions via sequencer",
        })

    # TLM connections from architecture
    tlm_conns = arch.get("tlm_connections", [])
    for i, tlm in enumerate(tlm_conns):
        src = tlm.get("from_component", tlm.get("source", ""))
        dst = tlm.get("to_component", tlm.get("target", ""))
        src_inst = _map_component_to_instance(src)
        dst_inst = _map_component_to_instance(dst)
        if src_inst and dst_inst and src_inst != dst_inst:
            conn_id = f"tlm_{i}"
            port_name = tlm.get("port_name", tlm.get("from_port", f"port_{i}"))
            connections.append({
                "id": conn_id,
                "type": "tlm",
                "color": TLM_COLOR,
                "from": {"instance": src_inst, "port": port_name},
                "to": {"instance": dst_inst, "port": port_name},
                "signals": [{"name": port_name, "width": 1}],
                "description": f"TLM: {src} → {dst}",
            })

    # Interface connections (master agent ↔ interface ↔ slave agent)
    for iface in ifaces:
        iface_name = iface.get("name", "")
        signals = iface.get("signals", [])
        if not signals:
            continue
        # Master ↔ Interface
        connections.append({
            "id": f"master_to_{iface_name}",
            "type": "signal",
            "color": SIGNAL_COLOR,
            "from": {"instance": "master_agent", "port": "vif"},
            "to": {"instance": iface_name, "port": "master_side"},
            "signals": [
                {"name": s.get("name", ""), "width": _parse_width(
                    s.get("range", s.get("type", ""))
                )}
                for s in signals
            ],
            "description": f"Master ↔ {iface_name} ({len(signals)} signals)",
        })
        # Interface ↔ Slave
        connections.append({
            "id": f"{iface_name}_to_slave",
            "type": "signal",
            "color": SIGNAL_COLOR,
            "from": {"instance": iface_name, "port": "slave_side"},
            "to": {"instance": "slave_agent", "port": "vif"},
            "signals": [
                {"name": s.get("name", ""), "width": _parse_width(
                    s.get("range", s.get("type", ""))
                )}
                for s in signals
            ],
            "description": f"{iface_name} ↔ Slave ({len(signals)} signals)",
        })

    # ── Build groups ──────────────────────────────────────────────────
    groups.append({
        "name": f"{protocol.upper()} Testbench",
        "instances": [inst["name"] for inst in instances],
        "color": "#37474F",
        "description": f"Top-level {protocol.upper()} UVC testbench",
    })

    env_group_insts = ["env", "master_agent", "slave_agent"]
    if seq_classes:
        env_group_insts.append("sequences")
    groups.append({
        "name": f"{protocol.upper()} Environment",
        "instances": env_group_insts,
        "color": "#1B5E20",
        "description": f"{protocol.upper()} UVM environment with agents",
    })

    # ── Assemble design ──────────────────────────────────────────────
    total_classes = sum(len(p.get("classes", [])) for p in pkgs)
    total_signals = sum(
        len(i.get("signals", []))
        for i in ifaces
        if i.get("signals")
    )

    return {
        "design_name": design_name,
        "version": "1.0",
        "description": description,
        "source_repo": "https://github.com/r987r/blockify",
        "metadata_type": "vip",
        "protocol": protocol,
        "summary": {
            "total_packages": len(pkgs),
            "total_classes": total_classes,
            "total_interfaces": len(ifaces),
            "total_signals": total_signals,
        },
        "testbench": {
            "module_name": "tb_top",
            "global_signals": [
                {"name": "clk", "face": "bottom", "color": CLK_COLOR},
                {"name": "rst_n", "face": "top", "color": RST_COLOR},
            ],
        },
        "modules": modules,
        "instances": instances,
        "connections": connections,
        "groups": groups,
    }


def _classify_uvm_class(name, base, pkg_lower):
    """Classify a UVM class into a role category."""
    name_l = name.lower()
    base_l = base.lower()
    if "test" in base_l or "test" in pkg_lower:
        return "test"
    if "virtual_seq" in pkg_lower or "virtual_sequence" in pkg_lower:
        return "virtual_sequence"
    if "seq" in pkg_lower and "virtual" not in pkg_lower:
        return "sequence"
    if "env" in name_l or "environment" in name_l:
        return "env"
    if "scoreboard" in name_l:
        return "env"
    if "virtual_sequencer" in name_l:
        return "env"
    if "master" in pkg_lower or "main" in pkg_lower or "tx" in pkg_lower:
        return "agent_master"
    if "slave" in pkg_lower or "rx" in pkg_lower:
        return "agent_slave"
    if "env" in pkg_lower:
        return "env"
    return "other"


def _build_component_module(classes, mod_type, description, color):
    """Build a module definition from a list of UVM classes."""
    ports = []
    for cls in classes:
        # Extract properties as pseudo-ports
        for prop in cls.get("properties", []):
            ports.append({
                "name": prop.get("name", ""),
                "direction": "InOut",
                "width": 1,
                "type": prop.get("type", ""),
            })
        # Extract TLM ports
        for tlm in cls.get("tlm_ports", []):
            ports.append({
                "name": tlm.get("name", ""),
                "direction": "Out" if "port" in tlm.get("port_type", "").lower() else "In",
                "width": 1,
                "type": tlm.get("port_type", ""),
            })
    return {
        "description": description,
        "color": color,
        "ports": ports[:30],  # cap for readability
        "classes": [c["name"] for c in classes],
        "class_count": len(classes),
    }


def _parse_width(range_str):
    """Parse a width from a range string like '[31:0]' or 'logic'."""
    if not range_str or range_str in ("logic", "bit", "wire", "reg"):
        return 1
    s = str(range_str).strip()
    if s.startswith("[") and ":" in s:
        try:
            parts = s.strip("[]").split(":")
            return abs(int(parts[0]) - int(parts[1])) + 1
        except (ValueError, IndexError):
            return 1
    return 1


def _map_component_to_instance(component_name):
    """Map a UVM component name to our instance names."""
    c = component_name.lower()
    if "master" in c or "tx" in c:
        if "monitor" in c or "driver" in c or "agent" in c:
            return "master_agent"
    if "slave" in c or "rx" in c:
        if "monitor" in c or "driver" in c or "agent" in c:
            return "slave_agent"
    if "scoreboard" in c or "env" in c:
        return "env"
    return None


# ── RTL (DMA) diagram builder ────────────────────────────────────────────

# Files that compose the DMA AXI32 hierarchy
DMA_AXI32_FILES = [
    "dma_axi_dma_axi32.json",
    "dma_axi_dma_axi32_dual_core.json",
    "dma_axi_dma_axi32_core0.json",
    "dma_axi_dma_axi32_core0_top.json",
    "dma_axi_dma_axi32_core0_arbiter.json",
    "dma_axi_dma_axi32_core0_axim_cmd.json",
    "dma_axi_dma_axi32_core0_axim_rd.json",
    "dma_axi_dma_axi32_core0_axim_rdata.json",
    "dma_axi_dma_axi32_core0_axim_resp.json",
    "dma_axi_dma_axi32_core0_axim_timeout.json",
    "dma_axi_dma_axi32_core0_axim_wdata.json",
    "dma_axi_dma_axi32_core0_axim_wr.json",
    "dma_axi_dma_axi32_core0_ch.json",
    "dma_axi_dma_axi32_core0_channels.json",
    "dma_axi_dma_axi32_core0_channels_mux.json",
    "dma_axi_dma_axi32_core0_ctrl.json",
    "dma_axi_dma_axi32_core0_wdt.json",
    "dma_axi_dma_axi32_reg.json",
    "dma_axi_dma_axi32_apb_mux.json",
]

DMA_AXI64_FILES = [f.replace("axi32", "axi64") for f in DMA_AXI32_FILES]


def build_dma_diagram(cache_dir, files, design_name, description, data_width):
    """Build a diagram JSON from DMA RTL metadata files."""
    modules_meta = {}
    for fname in files:
        meta = _download_json(fname, cache_dir)
        if meta is None:
            continue
        mods = meta.get("modules", [meta]) if "modules" in meta else [meta]
        for mod in mods:
            mod_name = mod.get("module_name", fname.replace(".json", ""))
            if mod_name:
                modules_meta[mod_name] = mod

    # If no modules loaded, create from filenames
    if not modules_meta:
        for fname in files:
            mod_name = fname.replace(".json", "").replace("dma_axi_", "")
            modules_meta[mod_name] = {"module_name": mod_name, "interface": {"ports": []}}

    modules = {}
    instances = []
    connections = []
    groups = []

    # ── Categorize modules into hierarchy levels ──────────────────────
    top_module = None
    core_modules = []
    sub_modules = []
    utility_modules = []

    for mod_name, mod in modules_meta.items():
        depth = mod_name.count("_")
        iface = mod.get("interface", {})
        ports = iface.get("ports", [])

        if mod_name in (f"dma_axi{data_width}", "dma_axi32", "dma_axi64"):
            top_module = (mod_name, mod)
        elif "core0_top" in mod_name or "dual_core" in mod_name:
            core_modules.append((mod_name, mod))
        elif "core0" in mod_name:
            sub_modules.append((mod_name, mod))
        elif mod_name.startswith("dma_axi"):
            # reg, apb_mux at top level
            core_modules.append((mod_name, mod))
        else:
            utility_modules.append((mod_name, mod))

    # ── Build module definitions ──────────────────────────────────────
    colour_idx = 0
    for mod_name, mod in modules_meta.items():
        iface = mod.get("interface", {})
        ports = iface.get("ports", [])
        internals = mod.get("internals", {})
        hierarchy = mod.get("hierarchy", {})
        logic = mod.get("logic_analysis", {})
        fsm = mod.get("fsm_analysis", {})
        compilation = mod.get("compilation", {})

        short_name = _shorten_dma_name(mod_name, data_width)

        modules[short_name] = {
            "description": f"RTL Module: {mod_name}",
            "color": _colour(colour_idx),
            "ports": [
                {
                    "name": p.get("name", ""),
                    "direction": p.get("direction", "In"),
                    "width": p.get("width", 1),
                    "type": p.get("type", "logic"),
                }
                for p in ports
            ],
            "metadata": {
                "num_inputs": iface.get("num_inputs", 0),
                "num_outputs": iface.get("num_outputs", 0),
                "total_input_bits": iface.get("total_input_bits", 0),
                "total_output_bits": iface.get("total_output_bits", 0),
                "num_registers": internals.get("num_registers", 0),
                "num_wires": internals.get("num_wires", 0),
                "num_sequential_blocks": logic.get("num_sequential_blocks", 0),
                "num_combinatorial_blocks": logic.get("num_combinatorial_blocks", 0),
                "has_fsm": fsm.get("has_potential_fsm", False),
                "compilation_status": compilation.get("status", "UNKNOWN"),
                "is_leaf": hierarchy.get("is_leaf", True),
            },
        }
        colour_idx += 1

    # ── Create instances with hierarchical positioning ────────────────
    # Top module at center
    if top_module:
        tn, tm = top_module
        short = _shorten_dma_name(tn, data_width)
        instances.append({
            "name": short,
            "module": short,
            "position": {"x": 0, "y": 0, "z": -20},
            "info": _module_info(tm),
        })

    # Core modules in a ring around center
    core_layout = _layout_grid(
        core_modules, cols=3, spacing_x=14, spacing_z=12, y=0
    )
    for (cn, cm), x, y, z in core_layout:
        short = _shorten_dma_name(cn, data_width)
        instances.append({
            "name": short,
            "module": short,
            "position": {"x": x, "y": y, "z": z - 8},
            "info": _module_info(cm),
        })

    # Sub-modules below
    sub_layout = _layout_grid(
        sub_modules, cols=4, spacing_x=12, spacing_z=10, y=0
    )
    for (sn, sm), x, y, z in sub_layout:
        short = _shorten_dma_name(sn, data_width)
        instances.append({
            "name": short,
            "module": short,
            "position": {"x": x, "y": y, "z": z + 10},
            "info": _module_info(sm),
        })

    # ── Build connections based on port matching ──────────────────────
    inst_names = {inst["name"] for inst in instances}
    inst_ports = {}
    for inst in instances:
        mod = modules.get(inst["module"], {})
        inst_ports[inst["name"]] = {
            p["name"]: p for p in mod.get("ports", [])
        }

    # Connect modules that share signal names (port-matching heuristic)
    connection_set = set()
    inst_list = list(instances)
    for i, inst_a in enumerate(inst_list):
        ports_a = inst_ports.get(inst_a["name"], {})
        for j, inst_b in enumerate(inst_list):
            if j <= i:
                continue
            ports_b = inst_ports.get(inst_b["name"], {})

            # Find matching output→input port names
            shared_signals = []
            for pname, pa in ports_a.items():
                if pname in ports_b:
                    pb = ports_b[pname]
                    if pa["direction"] == "Out" and pb["direction"] == "In":
                        shared_signals.append({
                            "name": pname,
                            "width": pa.get("width", 1),
                        })
                    elif pa["direction"] == "In" and pb["direction"] == "Out":
                        shared_signals.append({
                            "name": pname,
                            "width": pb.get("width", 1),
                        })

            if shared_signals:
                conn_key = (inst_a["name"], inst_b["name"])
                if conn_key not in connection_set:
                    connection_set.add(conn_key)
                    # Separate clock/reset from data signals
                    clk_rst = [s for s in shared_signals if s["name"] in ("clk", "reset", "rst", "rst_n")]
                    data_sigs = [s for s in shared_signals if s["name"] not in ("clk", "reset", "rst", "rst_n")]

                    if data_sigs:
                        connections.append({
                            "id": f"conn_{inst_a['name']}_to_{inst_b['name']}",
                            "type": "signal",
                            "color": SIGNAL_COLOR,
                            "from": {"instance": inst_a["name"], "port": "data"},
                            "to": {"instance": inst_b["name"], "port": "data"},
                            "signals": data_sigs,
                            "description": f"{inst_a['name']} → {inst_b['name']} ({len(data_sigs)} signals)",
                        })

    # Add explicit hierarchical connections for DMA structure
    _add_dma_hierarchy_connections(connections, instances, data_width)

    # ── Build groups ──────────────────────────────────────────────────
    all_inst_names = [inst["name"] for inst in instances]
    groups.append({
        "name": f"DMA AXI{data_width} Design",
        "instances": all_inst_names,
        "color": "#37474F",
        "description": f"DMA AXI {data_width}-bit top-level design",
    })

    # Core group
    core_names = [_shorten_dma_name(cn, data_width) for cn, _ in core_modules]
    core_names = [n for n in core_names if n in inst_names]
    if core_names:
        groups.append({
            "name": "Core Infrastructure",
            "instances": core_names,
            "color": "#1B5E20",
            "description": "Core modules: top, dual_core, registers",
        })

    # AXI master sub-group
    axim_names = [n for n in all_inst_names if "axim" in n]
    if axim_names:
        groups.append({
            "name": "AXI Master Interface",
            "instances": axim_names,
            "color": "#0D47A1",
            "description": "AXI master read/write data path",
        })

    # Channel sub-group
    ch_names = [n for n in all_inst_names if n.startswith("ch") or "channel" in n]
    if ch_names:
        groups.append({
            "name": "DMA Channels",
            "instances": ch_names,
            "color": "#4A148C",
            "description": "DMA channel logic and multiplexing",
        })

    return {
        "design_name": design_name,
        "version": "1.0",
        "description": description,
        "source_repo": "https://github.com/r987r/blockify",
        "metadata_type": "rtl",
        "data_width": data_width,
        "testbench": {
            "module_name": f"dma_axi{data_width}_tb",
            "global_signals": [
                {"name": "clk", "face": "bottom", "color": CLK_COLOR},
                {"name": "reset", "face": "top", "color": RST_COLOR},
            ],
        },
        "modules": modules,
        "instances": instances,
        "connections": connections,
        "groups": groups,
    }


def _shorten_dma_name(name, data_width):
    """Shorten a DMA module name for display."""
    prefix = f"dma_axi{data_width}_"
    alt_prefix = f"dma_axi_dma_axi{data_width}_"
    n = name
    if n.startswith(alt_prefix):
        n = n[len(alt_prefix):]
    elif n.startswith(prefix):
        n = n[len(prefix):]
    elif n.startswith("dma_axi_"):
        n = n[len("dma_axi_"):]
    # Remove redundant core0_ prefix for deep modules
    if n.startswith("core0_"):
        n = n[6:]
    return n if n else name


def _module_info(mod):
    """Extract display info from a module metadata dict."""
    iface = mod.get("interface", {})
    internals = mod.get("internals", {})
    logic = mod.get("logic_analysis", {})
    fsm = mod.get("fsm_analysis", {})
    compilation = mod.get("compilation", {})
    ports = iface.get("ports", [])

    return {
        "module_name": mod.get("module_name", ""),
        "num_ports": len(ports),
        "num_inputs": iface.get("num_inputs", 0),
        "num_outputs": iface.get("num_outputs", 0),
        "total_input_bits": iface.get("total_input_bits", 0),
        "total_output_bits": iface.get("total_output_bits", 0),
        "num_registers": internals.get("num_registers", 0),
        "num_wires": internals.get("num_wires", len(internals.get("nets", []))),
        "clocks": logic.get("clocks", []),
        "resets": logic.get("resets", []),
        "has_fsm": fsm.get("has_potential_fsm", False),
        "compilation": compilation.get("status", "UNKNOWN"),
        "ports": [
            {"name": p.get("name", ""), "dir": p.get("direction", ""),
             "width": p.get("width", 1)}
            for p in ports[:30]
        ],
    }


def _add_dma_hierarchy_connections(connections, instances, data_width):
    """Add explicit hierarchy connections for the DMA design."""
    inst_names = {inst["name"] for inst in instances}
    prefix = f"dma_axi{data_width}"

    # Top → dual_core
    hierarchy = [
        ("top", "dual_core", "AXI master ports"),
        ("top", "channels", "Channel control"),
        ("top", "ctrl", "Control registers"),
        ("top", "wdt", "Watchdog timer"),
        ("dual_core", "arbiter", "Arbitration"),
        ("channels", "channels_mux", "Channel multiplexer"),
        ("axim_cmd", "axim_rd", "Read commands"),
        ("axim_cmd", "axim_wr", "Write commands"),
        ("axim_rd", "axim_rdata", "Read data path"),
        ("axim_wr", "axim_wdata", "Write data path"),
        ("axim_resp", "axim_rd", "Read responses"),
        ("axim_resp", "axim_wr", "Write responses"),
    ]

    for src, dst, desc in hierarchy:
        if src in inst_names and dst in inst_names:
            connections.append({
                "id": f"hier_{src}_to_{dst}",
                "type": "hierarchy",
                "color": "#CE93D8",
                "from": {"instance": src, "port": "out"},
                "to": {"instance": dst, "port": "in"},
                "signals": [{"name": desc, "width": 1}],
                "description": f"{src} → {dst}: {desc}",
            })


# ── main ──────────────────────────────────────────────────────────────────

DESIGNS = [
    {
        "type": "vip",
        "source": "axi4_avip_vip.json",
        "output": "uvc_axi4.json",
        "name": "uvc_axi4",
        "description": "AXI4 UVC – 326 classes, 42 bus signals, full master/slave verification",
    },
    {
        "type": "vip",
        "source": "ahb_avip_vip.json",
        "output": "uvc_ahb.json",
        "name": "uvc_ahb",
        "description": "AHB UVC – 50 classes, 18 bus signals, master/slave verification",
    },
    {
        "type": "vip",
        "source": "apb_avip_vip.json",
        "output": "uvc_apb.json",
        "name": "uvc_apb",
        "description": "APB UVC – 57 classes, 4 bus signals, register-level verification",
    },
    {
        "type": "vip",
        "source": "uart_avip_vip.json",
        "output": "uvc_uart.json",
        "name": "uvc_uart",
        "description": "UART UVC – 45 classes, serial Tx/Rx verification",
    },
    {
        "type": "dma",
        "files": DMA_AXI32_FILES,
        "output": "dma_axi32.json",
        "name": "dma_axi32",
        "description": "DMA AXI 32-bit – multi-channel DMA controller with AXI master & APB slave",
        "data_width": 32,
    },
    {
        "type": "dma",
        "files": DMA_AXI64_FILES,
        "output": "dma_axi64.json",
        "name": "dma_axi64",
        "description": "DMA AXI 64-bit – multi-channel DMA controller with 64-bit data path",
        "data_width": 64,
    },
]


def main():
    parser = argparse.ArgumentParser(description="Generate diagram metadata")
    parser.add_argument(
        "--input-dir", default=None,
        help="Local directory with blockify metadata (skips download)",
    )
    parser.add_argument(
        "--output-dir", default="metadata",
        help="Output directory for diagram JSON files",
    )
    parser.add_argument(
        "--cache-dir", default="/tmp/blockify_meta_cache",
        help="Cache directory for downloaded metadata",
    )
    args = parser.parse_args()

    cache_dir = args.input_dir or args.cache_dir
    out_dir = args.output_dir
    os.makedirs(out_dir, exist_ok=True)

    for design in DESIGNS:
        print(f"\n{'='*60}")
        print(f"Generating: {design['name']}")
        print(f"{'='*60}")

        if design["type"] == "vip":
            meta = _download_json(design["source"], cache_dir)
            if meta is None:
                print(f"  ⚠ Skipping {design['name']} (no metadata)")
                continue
            diagram = build_vip_diagram(
                meta, design["name"], design["description"]
            )
        elif design["type"] == "dma":
            diagram = build_dma_diagram(
                cache_dir, design["files"],
                design["name"], design["description"],
                design["data_width"],
            )
        else:
            continue

        out_path = os.path.join(out_dir, design["output"])
        with open(out_path, "w") as f:
            json.dump(diagram, f, indent=2)
        n_inst = len(diagram.get("instances", []))
        n_conn = len(diagram.get("connections", []))
        print(f"  ✓ Written {out_path}  ({n_inst} instances, {n_conn} connections)")

    # Generate index file listing all designs
    index = {
        "designs": [
            {
                "name": d["name"],
                "file": d["output"],
                "description": d["description"],
                "type": d["type"],
            }
            for d in DESIGNS
        ]
    }
    index_path = os.path.join(out_dir, "index.json")
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)
    print(f"\n✓ Index written to {index_path}")
    print("Done!")


if __name__ == "__main__":
    main()
