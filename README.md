# SV Diagrams – 3D Hardware Visualization

Interactive 3D diagrams of SystemVerilog RTL modules and UVM verification components, built with [Three.js](https://threejs.org/).  Diagrams maintain **hierarchy and composition** — parent blocks visually contain their children, groups nest properly, and Y-axis levels encode design depth.

## Designs

| Design | Type | Instances | Groups | Y-Levels | Description |
|--------|------|-----------|--------|----------|-------------|
| **UVC AXI4** | VIP | 14 | 4 | 6 | 326 classes, 42 bus signals – AXI4 master/slave |
| **UVC AHB** | VIP | 14 | 4 | 6 | 50 classes, 18 bus signals – AHB master/slave |
| **UVC APB** | VIP | 14 | 4 | 6 | 57 classes, 4 bus signals – APB register-level |
| **UVC UART** | VIP | 18 | 4 | 6 | 45 classes, serial Tx/Rx |
| **DMA AXI 32** | RTL | 19 | 4 | 3 | 32-bit multi-channel DMA controller |
| **DMA AXI 64** | RTL | 19 | 4 | 3 | 64-bit multi-channel DMA controller |

## Hierarchy & Composition

### UVC (Verification IP) — 6 Y-Axis Levels

```
Y = 20   ┌─────────────────────────────────────────┐
         │  tests                                   │  ← test classes
Y = 14   │  sequences                               │  ← virtual sequences
         │  ┌─────────────────────────────────────┐  │
Y =  8   │  │  env / scoreboard                   │  │  ← UVM environment
         │  │  ┌───────────┐     ┌───────────┐    │  │
Y =  0   │  │  │master_agent│    │ slave_agent│    │  │  ← agent containers
         │  │  │  ┌─┐┌─┐┌─┐│    │  ┌─┐┌─┐┌─┐│    │  │
Y = -6   │  │  │  │S││D││M││    │  │S││D││M││    │  │  ← sequencer, driver,
         │  │  │  └─┘└─┘└─┘│    │  └─┘└─┘└─┘│    │  │    monitor, coverage
         │  │  └───────────┘     └───────────┘    │  │
         │  └─────────────────────────────────────┘  │
Y = -14  │  ┌────────────────────────────────────┐   │
         │  │  interfaces / BFMs (HDL layer)     │   │  ← bus signals
         │  └────────────────────────────────────┘   │
         └─────────────────────────────────────────┘
         ← Testbench group (outermost) →
```

### RTL (DMA) — 3 Y-Axis Levels

```
Y = 12   ┌──────────────────────────────────────┐
         │  dma_axi32 (top-level)               │  ← top module
         │  ┌──────────────────────────────┐    │
Y =  6   │  │  dual_core / top / reg / mux │    │  ← core infrastructure
         │  └──────────────────────────────┘    │
         │  ┌──────────────┐  ┌─────────────┐  │
Y =  0   │  │ axim_cmd ...  │  │ ch / chans  │  │  ← sub-modules
         │  │ (AXI master)  │  │ (DMA chans) │  │
         │  └──────────────┘  └─────────────┘  │
         └──────────────────────────────────────┘
```

## Features

- **Cuboid blocks** for RTL modules / UVM classes, dynamically sized by port count and fan-out
- **Bundled signal cylinders** — signals sharing endpoints are grouped into a single cylinder (radius ∝ signal count)
- **Nested hierarchical groups** — dashed enclosures with per-group padding, sorted inner-to-outer for correct nesting
- **Click-to-inspect** — click any block for a popup with ports, classes, signals, and connections
- **Connection highlighting** — clicking a block highlights all connected blocks and paths
- **Y-axis hierarchy** — vertical position encodes design depth (tests → env → agents → internals → interfaces)
- **Design selector** — switch between all six designs from the dropdown
- **Overview panel** — click ℹ for design summary, module table, full connection list
- **Scalable architecture** — metadata-driven; add new designs via [blockify](https://github.com/r987r/blockify)
- **Clock/reset rails** — global signals shown as dashed green/red rails

## Quick Start

### Local (Python HTTP server)

```bash
# 1. (Optional) Re-generate diagram metadata from blockify
python3 scripts/generate_diagram_meta.py

# 2. Serve locally
cd viewer && python3 -m http.server 8080
# Open http://localhost:8080
```

> **Note:** The `viewer/metadata` symlink points to `../metadata`. When serving from `viewer/`, this ensures the metadata files are accessible.

### Docker (recommended)

```bash
# Build and run
docker build -t sv-diagrams .
docker run -d -p 8080:80 --name sv-diagrams sv-diagrams

# Open http://localhost:8080
```

### Docker Compose

```bash
# Build and start
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

### Deployment (production)

1. **Build the image:**
   ```bash
   docker build -t sv-diagrams:latest .
   ```

2. **Push to a registry:**
   ```bash
   docker tag sv-diagrams:latest your-registry/sv-diagrams:latest
   docker push your-registry/sv-diagrams:latest
   ```

3. **Run on a server:**
   ```bash
   docker run -d \
     -p 80:80 \
     --restart unless-stopped \
     --name sv-diagrams \
     your-registry/sv-diagrams:latest
   ```

4. **With a reverse proxy (nginx/Caddy):**
   - Point your domain to the server
   - Proxy `/` to `http://localhost:8080` (or whichever port you mapped)
   - Add TLS via Let's Encrypt

5. **Render.com / Fly.io / Railway:**
   - Connect your GitHub repo
   - The Dockerfile is auto-detected
   - Set port to `80`

## Architecture

```
Sv-diagrams/
├── viewer/                        # Three.js viewer (no build step)
│   ├── index.html                 # Entry point with ES module import map
│   ├── style.css                  # Dark theme styling
│   ├── main.js                    # Scene builder, interaction, rendering
│   └── vendor/three/              # Vendored Three.js r0.160.0
│       ├── build/three.module.js
│       └── examples/jsm/
│           ├── controls/OrbitControls.js
│           └── renderers/CSS2DRenderer.js
├── metadata/                      # Generated diagram JSON files
│   ├── index.json                 # Design catalog
│   ├── uvc_axi4.json             # AXI4 UVC (14 instances, 12 connections)
│   ├── uvc_ahb.json              # AHB UVC (14 instances, 12 connections)
│   ├── uvc_apb.json              # APB UVC (14 instances, 12 connections)
│   ├── uvc_uart.json             # UART UVC (18 instances, 20 connections)
│   ├── dma_axi32.json            # DMA AXI32 (19 instances, 62 connections)
│   └── dma_axi64.json            # DMA AXI64 (19 instances, 62 connections)
├── scripts/
│   └── generate_diagram_meta.py   # Metadata transformer (blockify → diagram JSON)
├── Dockerfile                     # nginx:alpine container
├── docker-compose.yml             # Docker Compose for easy deployment
└── README.md
```

### Viewer (`viewer/main.js`)

| Function | Purpose |
|----------|---------|
| `buildScene(designPath)` | Loads JSON, creates instances, groups, connections |
| `instanceCuboid(inst, hex, scale)` | Renders a cuboid with wireframe edges and label |
| `bundleCylinder(from, to, color, n)` | Renders a signal bundle cylinder |
| `dashedBox(cx, cy, cz, w, h, d, color)` | Renders a hierarchical group enclosure |
| `routeConnection(...)` | L-shaped routing with obstacle avoidance |
| `computeBounds(positions, pad)` | Bounding box calculation for groups |
| `makeLabel(html, className)` | CSS2D text label |

### Metadata Generator (`scripts/generate_diagram_meta.py`)

| Function | Purpose |
|----------|---------|
| `build_vip_diagram(meta, ...)` | VIP (UVC) metadata → diagram JSON |
| `build_dma_diagram(cache, ...)` | DMA RTL metadata → diagram JSON |
| `_classify_uvm_class(...)` | Classifies UVM class → role (test/env/agent/seq) |
| `_classify_agent_sub(cls, bucket)` | Sub-classifies agent class → driver/monitor/etc. |
| `_add_agent_instances(...)` | Positions agent and sub-component instances |
| `_layout_grid(items, cols, ...)` | Grid layout with centered positioning |

## Diagram JSON Schema

```json
{
  "design_name": "uvc_axi4",
  "metadata_type": "vip",
  "modules": {
    "<type>": {
      "description": "...",
      "color": "#1565C0",
      "ports": [{"name": "AWADDR", "direction": "Out", "width": 32}],
      "classes": ["axi4_master_driver", "axi4_master_monitor"]
    }
  },
  "instances": [
    {
      "name": "master_driver",
      "module": "master_driver",
      "position": {"x": -18, "y": -6, "z": 0},
      "info": {"class_count": 5, "classes": [...]}
    }
  ],
  "connections": [
    {
      "id": "sqr_to_drv",
      "type": "tlm",
      "color": "#42A5F5",
      "from": {"instance": "master_sequencer", "port": "seq_item_port"},
      "to": {"instance": "master_driver", "port": "seq_item_export"},
      "signals": [{"name": "seq_item_port", "width": 1}]
    }
  ],
  "groups": [
    {
      "name": "AXI4 Master Agent",
      "instances": ["master_agent", "master_sequencer", "master_driver", "master_monitor", "master_coverage"],
      "color": "#1565C0",
      "padding": 1.0
    },
    {
      "name": "AXI4 Environment",
      "instances": ["env", "master_agent", "master_sequencer", "...", "sequences"],
      "color": "#1B5E20",
      "padding": 2.0
    }
  ]
}
```

### Group Nesting via Overlapping Membership

Groups nest visually because inner groups are **subsets** of outer groups:

```
Master Agent (5 members, padding=1.0)  ⊂  Environment (12 members, padding=2.0)  ⊂  Testbench (14 members, padding=3.0)
```

The viewer sorts groups by member count (ascending) and renders inner groups first, so dashed boxes nest correctly.

## Data Pipeline

```
blockify (RTL/VIP parsing via slang)
    ↓
JSON metadata (classes, ports, signals, hierarchy)
    ↓
generate_diagram_meta.py (positioning, connections, groups)
    ↓
Diagram JSON (instances, connections, groups with padding)
    ↓
Three.js viewer (3D rendering, interaction)
```

## Adding a New Design

1. Generate metadata using [blockify](https://github.com/r987r/blockify)
2. Add the design to the `DESIGNS` list in `scripts/generate_diagram_meta.py`
3. Run `python3 scripts/generate_diagram_meta.py`
4. The new design appears in the dropdown automatically

## Related Repositories

- [r987r/blockify](https://github.com/r987r/blockify) – RTL/VIP metadata generation
- [r987r/Hdl-tool-compiles](https://github.com/r987r/Hdl-tool-compiles) – Pre-compiled slang binaries
- [r987r/Diagram-gen](https://github.com/r987r/Diagram-gen) – Original 3D diagram generator (inspiration)