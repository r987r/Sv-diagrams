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
    """Build a diagram JSON from a VIP metadata file.

    Creates a hierarchical composition layout:
      tb_top (outermost)
        └─ environment
             ├─ master_agent
             │    ├─ master_sequencer
             │    ├─ master_driver
             │    ├─ master_monitor
             │    └─ master_coverage
             ├─ slave_agent
             │    ├─ slave_sequencer
             │    ├─ slave_driver
             │    ├─ slave_monitor
             │    └─ slave_coverage
             └─ scoreboard
        ├─ tests
        ├─ sequences
        └─ interfaces (HDL layer)
    """
    modules = {}
    instances = []
    connections = []
    groups = []

    protocol = meta.get("vip_info", {}).get("protocol", design_name)
    pkgs = meta.get("packages", [])
    ifaces = meta.get("interfaces", [])
    arch = meta.get("architecture", {})
    proto_upper = protocol.upper()

    # ── Classify all classes ──────────────────────────────────────────
    env_classes = []
    master_classes = {"agent": [], "driver": [], "monitor": [],
                      "sequencer": [], "coverage": [], "config": [],
                      "transaction": [], "converter": [], "other": []}
    slave_classes = {"agent": [], "driver": [], "monitor": [],
                     "sequencer": [], "coverage": [], "config": [],
                     "transaction": [], "converter": [], "other": []}
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
                _classify_agent_sub(cls, master_classes)
            elif role == "agent_slave":
                _classify_agent_sub(cls, slave_classes)
            elif role in ("sequence", "virtual_sequence"):
                seq_classes.append(cls)
            elif role == "test":
                test_classes.append(cls)
            else:
                other_classes.append(cls)

    # ── Module definitions ────────────────────────────────────────────
    # Testbench
    modules["testbench"] = {
        "description": f"{proto_upper} UVC Testbench",
        "color": "#37474F", "ports": [],
    }

    # Environment
    modules["env"] = _build_component_module(
        env_classes, "env", f"{protocol} Environment", "#1B5E20")

    # Master agent sub-components
    _add_agent_modules(modules, master_classes, "master", protocol, "#1565C0")

    # Slave agent sub-components
    _add_agent_modules(modules, slave_classes, "slave", protocol, "#4A148C")

    # Interfaces
    for iface in ifaces:
        iface_name = iface.get("name", "interface")
        signals = iface.get("signals", [])
        if not signals:
            continue
        modules[f"iface_{iface_name}"] = {
            "description": f"Interface: {iface_name}",
            "color": "#E65100",
            "ports": [
                {"name": s.get("name", ""), "direction": "InOut",
                 "width": _parse_width(s.get("range", s.get("type", ""))),
                 "type": s.get("type", "logic")}
                for s in signals
            ],
        }

    # Sequences
    if seq_classes:
        modules["sequences"] = {
            "description": f"{protocol} Sequences ({len(seq_classes)} classes)",
            "color": "#F57F17", "ports": [],
            "classes": [c["name"] for c in seq_classes[:20]],
            "total_classes": len(seq_classes),
        }

    # Tests
    if test_classes:
        modules["tests"] = {
            "description": f"{protocol} Tests ({len(test_classes)} classes)",
            "color": "#880E4F", "ports": [],
            "classes": [c["name"] for c in test_classes[:20]],
            "total_classes": len(test_classes),
        }

    # ── Hierarchical Y-axis layout ────────────────────────────────────
    # Y=20  Tests (top-level stimulus)
    # Y=14  Sequences (virtual sequences)
    # Y=8   Scoreboard / Env config (environment level)
    # Y=0   Master/Slave agents (agent containers)
    # Y=-6  Sequencer, Driver, Monitor, Coverage (agent internals)
    # Y=-14 Interfaces / BFMs (HDL layer)

    # Tests
    if test_classes:
        instances.append({
            "name": "tests", "module": "tests",
            "position": {"x": 0, "y": 20, "z": 0},
            "info": {"class_count": len(test_classes),
                     "classes": [c["name"] for c in test_classes[:15]]},
        })

    # Sequences
    if seq_classes:
        instances.append({
            "name": "sequences", "module": "sequences",
            "position": {"x": -24, "y": 14, "z": 0},
            "info": {"class_count": len(seq_classes),
                     "classes": [c["name"] for c in seq_classes[:15]]},
        })

    # Environment
    instances.append({
        "name": "env", "module": "env",
        "position": {"x": 0, "y": 8, "z": 0},
        "info": {"class_count": len(env_classes),
                 "classes": [c["name"] for c in env_classes],
                 "description": f"{protocol} UVM Environment"},
    })

    # Master agent (container) and its sub-components
    master_x = -14
    _add_agent_instances(instances, master_classes, "master", protocol,
                         x_center=master_x, y_agent=0, y_sub=-6)

    # Slave agent (container) and its sub-components
    slave_x = 14
    _add_agent_instances(instances, slave_classes, "slave", protocol,
                         x_center=slave_x, y_agent=0, y_sub=-6)

    # Interfaces (HDL layer – bottom)
    iface_x = -16
    for iface in ifaces:
        iface_name = iface.get("name", "")
        signals = iface.get("signals", [])
        if not signals:
            continue
        instances.append({
            "name": iface_name, "module": f"iface_{iface_name}",
            "position": {"x": iface_x, "y": -14, "z": 0},
            "info": {"signal_count": len(signals),
                     "signals": [{"name": s.get("name", ""), "type": s.get("type", "")}
                                 for s in signals],
                     "description": f"Interface: {iface_name}"},
        })
        iface_x += 12

    # ── Connections ───────────────────────────────────────────────────
    # Tests → Environment
    connections.append({
        "id": "test_to_env", "type": "hierarchy", "color": "#CE93D8",
        "from": {"instance": "tests", "port": "env"},
        "to": {"instance": "env", "port": "create"},
        "signals": [{"name": "UVM hierarchy", "width": 1}],
        "description": "Test creates and configures environment",
    })

    # Environment → Master Agent
    connections.append({
        "id": "env_to_master", "type": "hierarchy", "color": "#CE93D8",
        "from": {"instance": "env", "port": "master_agent"},
        "to": {"instance": "master_agent", "port": "parent"},
        "signals": [{"name": "agent_handle", "width": 1}],
        "description": "Environment instantiates master agent",
    })

    # Environment → Slave Agent
    connections.append({
        "id": "env_to_slave", "type": "hierarchy", "color": "#CE93D8",
        "from": {"instance": "env", "port": "slave_agent"},
        "to": {"instance": "slave_agent", "port": "parent"},
        "signals": [{"name": "agent_handle", "width": 1}],
        "description": "Environment instantiates slave agent",
    })

    # Sequences → Master Sequencer
    if seq_classes:
        sqr_name = "master_sequencer"
        if sqr_name not in {i["name"] for i in instances}:
            sqr_name = "master_agent"
        connections.append({
            "id": "seq_to_master_sqr", "type": "tlm", "color": TLM_COLOR,
            "from": {"instance": "sequences", "port": "seq_item_port"},
            "to": {"instance": sqr_name, "port": "seq_item_export"},
            "signals": [{"name": "seq_item_port", "width": 1}],
            "description": "Sequences drive transactions via sequencer",
        })

    # Agent internal connections (sequencer → driver, monitor → scoreboard)
    for side in ("master", "slave"):
        inst_set = {i["name"] for i in instances}
        sqr = f"{side}_sequencer"
        drv = f"{side}_driver"
        mon = f"{side}_monitor"
        cov = f"{side}_coverage"
        agt = f"{side}_agent"

        if sqr in inst_set and drv in inst_set:
            connections.append({
                "id": f"{side}_sqr_to_drv", "type": "tlm", "color": TLM_COLOR,
                "from": {"instance": sqr, "port": "seq_item_port"},
                "to": {"instance": drv, "port": "seq_item_export"},
                "signals": [{"name": "seq_item_port", "width": 1}],
                "description": f"{side} sequencer → driver (TLM)",
            })
        if mon in inst_set:
            connections.append({
                "id": f"{side}_mon_to_env", "type": "tlm", "color": TLM_COLOR,
                "from": {"instance": mon, "port": "analysis_port"},
                "to": {"instance": "env", "port": "analysis_export"},
                "signals": [{"name": "analysis_port", "width": 1}],
                "description": f"{side} monitor → scoreboard (TLM)",
            })
        if cov in inst_set and mon in inst_set:
            connections.append({
                "id": f"{side}_mon_to_cov", "type": "tlm", "color": TLM_COLOR,
                "from": {"instance": mon, "port": "cov_port"},
                "to": {"instance": cov, "port": "analysis_export"},
                "signals": [{"name": "coverage_port", "width": 1}],
                "description": f"{side} monitor → coverage (TLM)",
            })

    # Interface connections (driver/monitor ↔ interface via virtual interface)
    for iface in ifaces:
        iface_name = iface.get("name", "")
        signals = iface.get("signals", [])
        if not signals:
            continue
        sig_list = [{"name": s.get("name", ""),
                     "width": _parse_width(s.get("range", s.get("type", "")))}
                    for s in signals]
        inst_set = {i["name"] for i in instances}

        # Master driver/monitor → interface
        for comp in ("master_driver", "master_monitor", "master_agent"):
            if comp in inst_set:
                connections.append({
                    "id": f"{comp}_to_{iface_name}", "type": "signal",
                    "color": SIGNAL_COLOR,
                    "from": {"instance": comp, "port": "vif"},
                    "to": {"instance": iface_name, "port": "master_side"},
                    "signals": sig_list,
                    "description": f"{comp} ↔ {iface_name} ({len(signals)} signals)",
                })
                break

        # Slave driver/monitor → interface
        for comp in ("slave_driver", "slave_monitor", "slave_agent"):
            if comp in inst_set:
                connections.append({
                    "id": f"{iface_name}_to_{comp}", "type": "signal",
                    "color": SIGNAL_COLOR,
                    "from": {"instance": iface_name, "port": "slave_side"},
                    "to": {"instance": comp, "port": "vif"},
                    "signals": sig_list,
                    "description": f"{iface_name} ↔ {comp} ({len(signals)} signals)",
                })
                break

    # ── Nested hierarchical groups ────────────────────────────────────
    # Inner groups first (rendered first), outer groups last
    all_names = [i["name"] for i in instances]

    # Master agent sub-group (tight padding)
    master_members = [n for n in all_names
                      if n.startswith("master_")]
    if master_members:
        groups.append({
            "name": f"{proto_upper} Master Agent",
            "instances": master_members,
            "color": "#1565C0", "padding": 1.0,
            "description": f"{proto_upper} master agent (sequencer, driver, monitor, coverage)",
        })

    # Slave agent sub-group (tight padding)
    slave_members = [n for n in all_names
                     if n.startswith("slave_")]
    if slave_members:
        groups.append({
            "name": f"{proto_upper} Slave Agent",
            "instances": slave_members,
            "color": "#4A148C", "padding": 1.0,
            "description": f"{proto_upper} slave agent (sequencer, driver, monitor, coverage)",
        })

    # Environment group (contains agents + env + sequences)
    env_members = ["env"] + master_members + slave_members
    if seq_classes:
        env_members.append("sequences")
    groups.append({
        "name": f"{proto_upper} Environment",
        "instances": env_members,
        "color": "#1B5E20", "padding": 2.0,
        "description": f"{proto_upper} UVM environment with agents and scoreboard",
    })

    # Testbench (outermost – all instances)
    groups.append({
        "name": f"{proto_upper} Testbench",
        "instances": all_names,
        "color": "#37474F", "padding": 3.0,
        "description": f"Top-level {proto_upper} UVC testbench (tb_top)",
    })

    # ── Assemble ──────────────────────────────────────────────────────
    total_classes = sum(len(p.get("classes", [])) for p in pkgs)
    total_signals = sum(len(i.get("signals", []))
                        for i in ifaces if i.get("signals"))

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


def _classify_agent_sub(cls, bucket):
    """Sub-classify a class within an agent into driver/monitor/etc."""
    name = cls.get("name", "").lower()
    base = cls.get("base_class", "").lower()
    if "driver" in name or "driver" in base:
        bucket["driver"].append(cls)
    elif "monitor" in name or "monitor" in base:
        bucket["monitor"].append(cls)
    elif "sequencer" in name or "sequencer" in base:
        bucket["sequencer"].append(cls)
    elif "coverage" in name or "coverage" in base:
        bucket["coverage"].append(cls)
    elif "config" in name or "agent_config" in name:
        bucket["config"].append(cls)
    elif "transaction" in name or "seq_item" in base or "_tx" in name:
        bucket["transaction"].append(cls)
    elif "converter" in name:
        bucket["converter"].append(cls)
    elif "agent" in name or "agent" in base:
        bucket["agent"].append(cls)
    else:
        bucket["other"].append(cls)


def _add_agent_modules(modules, agent_cls, side, protocol, base_color):
    """Add module definitions for agent sub-components."""
    colors = {
        "master": {"agent": "#1565C0", "sequencer": "#1976D2",
                    "driver": "#1E88E5", "monitor": "#2196F3",
                    "coverage": "#42A5F5"},
        "slave":  {"agent": "#4A148C", "sequencer": "#6A1B9A",
                    "driver": "#7B1FA2", "monitor": "#8E24AA",
                    "coverage": "#AB47BC"},
    }
    col = colors.get(side, colors["master"])

    # Agent container
    all_classes = []
    for v in agent_cls.values():
        all_classes.extend(v)
    modules[f"{side}_agent"] = _build_component_module(
        agent_cls["agent"] + agent_cls["config"],
        f"{side}_agent", f"{protocol} {side.title()} Agent", col["agent"])

    # Sub-components (only if there are classes)
    for role in ("sequencer", "driver", "monitor", "coverage"):
        cls_list = agent_cls[role]
        if cls_list:
            modules[f"{side}_{role}"] = _build_component_module(
                cls_list, f"{side}_{role}",
                f"{protocol} {side.title()} {role.title()}", col[role])


def _add_agent_instances(instances, agent_cls, side, protocol,
                         x_center, y_agent, y_sub):
    """Add positioned instances for an agent and its sub-components."""
    # Agent container
    instances.append({
        "name": f"{side}_agent", "module": f"{side}_agent",
        "position": {"x": x_center, "y": y_agent, "z": 0},
        "info": {"description": f"{protocol} {side.title()} Agent",
                 "class_count": sum(len(v) for v in agent_cls.values()),
                 "classes": [c["name"] for c in agent_cls["agent"][:5]]},
    })

    # Sub-components laid out horizontally under the agent
    sub_roles = ["sequencer", "driver", "monitor", "coverage"]
    active_roles = [r for r in sub_roles if agent_cls[r]]
    n = len(active_roles)
    if n == 0:
        return
    spacing = 8
    start_x = x_center - (n - 1) * spacing / 2
    for i, role in enumerate(active_roles):
        cls_list = agent_cls[role]
        instances.append({
            "name": f"{side}_{role}", "module": f"{side}_{role}",
            "position": {"x": start_x + i * spacing, "y": y_sub, "z": 0},
            "info": {"description": f"{protocol} {side.title()} {role.title()}",
                     "class_count": len(cls_list),
                     "classes": [c["name"] for c in cls_list[:5]]},
        })


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
    # Y=12  Top module (top-level container)
    # Y=6   Core modules (dual_core, top, reg, apb_mux)
    # Y=0   Sub-modules (axim_*, channels, ctrl, wdt)

    # Top module
    if top_module:
        tn, tm = top_module
        short = _shorten_dma_name(tn, data_width)
        instances.append({
            "name": short,
            "module": short,
            "position": {"x": 0, "y": 12, "z": 0},
            "info": _module_info(tm),
        })

    # Core modules at Y=6
    core_layout = _layout_grid(
        core_modules, cols=3, spacing_x=16, spacing_z=14, y=6
    )
    for (cn, cm), x, y, z in core_layout:
        short = _shorten_dma_name(cn, data_width)
        instances.append({
            "name": short,
            "module": short,
            "position": {"x": x, "y": y, "z": z},
            "info": _module_info(cm),
        })

    # Sub-modules at Y=0
    sub_layout = _layout_grid(
        sub_modules, cols=4, spacing_x=14, spacing_z=12, y=0
    )
    for (sn, sm), x, y, z in sub_layout:
        short = _shorten_dma_name(sn, data_width)
        instances.append({
            "name": short,
            "module": short,
            "position": {"x": x, "y": y, "z": z},
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

    # AXI master sub-group (inner, tight)
    axim_names = [n for n in all_inst_names if "axim" in n]
    if axim_names:
        groups.append({
            "name": "AXI Master Interface",
            "instances": axim_names,
            "color": "#0D47A1", "padding": 1.0,
            "description": "AXI master read/write data path",
        })

    # Channel sub-group (inner, tight)
    ch_names = [n for n in all_inst_names if n.startswith("ch") or "channel" in n]
    if ch_names:
        groups.append({
            "name": "DMA Channels",
            "instances": ch_names,
            "color": "#4A148C", "padding": 1.0,
            "description": "DMA channel logic and multiplexing",
        })

    # Core group (middle)
    core_names = [_shorten_dma_name(cn, data_width) for cn, _ in core_modules]
    core_names = [n for n in core_names if n in inst_names]
    if core_names:
        groups.append({
            "name": "Core Infrastructure",
            "instances": core_names,
            "color": "#1B5E20", "padding": 1.5,
            "description": "Core modules: top, dual_core, registers",
        })

    # Top-level (outermost)
    groups.append({
        "name": f"DMA AXI{data_width} Design",
        "instances": all_inst_names,
        "color": "#37474F", "padding": 3.0,
        "description": f"DMA AXI {data_width}-bit top-level design",
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
