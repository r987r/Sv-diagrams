# SV Diagrams – 3D Hardware Visualization

Interactive 3D diagrams of SystemVerilog RTL modules and UVM verification components, built with [Three.js](https://threejs.org/).

## Designs

| Design | Type | Description |
|--------|------|-------------|
| **UVC AXI4** | VIP | 326 classes, 42 bus signals – full AXI4 master/slave verification |
| **UVC AHB** | VIP | 50 classes, 18 bus signals – AHB master/slave verification |
| **UVC APB** | VIP | 57 classes, 4 bus signals – APB register-level verification |
| **UVC UART** | VIP | 45 classes, serial Tx/Rx verification |
| **DMA AXI 32** | RTL | 19 modules – 32-bit multi-channel DMA controller |
| **DMA AXI 64** | RTL | 19 modules – 64-bit multi-channel DMA controller |

## Features

- **Cuboid blocks** for RTL modules and UVM verification classes, dynamically sized by port count and connectivity
- **Bundled signal cylinders** connecting blocks – signals going between the same two points are grouped to reduce clutter
- **Click-to-inspect** – click any block to see a popup with ports, classes, signals, and connection details
- **Connection highlighting** – clicking a block highlights all connected blocks and paths
- **Hierarchical groups** – dashed enclosures show design hierarchy (testbench → environment → agents)
- **Design selector** – switch between all six designs from the dropdown
- **Scalable architecture** – metadata-driven; add new designs by generating JSON from [blockify](https://github.com/r987r/blockify)

## Quick Start

### Local (Python HTTP server)

```bash
# Generate diagram metadata from blockify
python3 scripts/generate_diagram_meta.py

# Serve locally
cd viewer && python3 -m http.server 8080
# Open http://localhost:8080
```

> **Note:** The viewer loads metadata from the `metadata/` directory relative to the viewer. When serving with `python3 -m http.server` from the `viewer/` directory, create a symlink: `ln -s ../metadata metadata`

### Docker

```bash
docker build -t sv-diagrams .
docker run -p 8080:80 sv-diagrams
# Open http://localhost:8080
```

## Architecture

```
Sv-diagrams/
├── viewer/              # Three.js viewer (HTML + CSS + JS)
│   ├── index.html       # Entry point with import map for Three.js
│   ├── style.css        # Dark theme styling
│   └── main.js          # Scene builder, interaction, rendering
├── metadata/            # Generated diagram JSON files
│   ├── index.json       # Design index
│   ├── uvc_axi4.json   # AXI4 UVC diagram
│   ├── uvc_ahb.json    # AHB UVC diagram
│   ├── uvc_apb.json    # APB UVC diagram
│   ├── uvc_uart.json   # UART UVC diagram
│   ├── dma_axi32.json  # DMA AXI 32-bit diagram
│   └── dma_axi64.json  # DMA AXI 64-bit diagram
├── scripts/
│   └── generate_diagram_meta.py  # Metadata transformer
├── Dockerfile           # nginx container
└── README.md
```

## Data Pipeline

1. **[blockify](https://github.com/r987r/blockify)** parses RTL/VIP repos using [slang](https://github.com/r987r/Hdl-tool-compiles) and generates detailed JSON metadata (ports, signals, classes, hierarchy)
2. **`generate_diagram_meta.py`** transforms blockify metadata into diagram JSON with positions, connections, and groups
3. **Three.js viewer** renders the diagram JSON as an interactive 3D scene

## Related Repositories

- [r987r/blockify](https://github.com/r987r/blockify) – RTL/VIP metadata generation
- [r987r/Hdl-tool-compiles](https://github.com/r987r/Hdl-tool-compiles) – Pre-compiled slang binaries
- [r987r/Diagram-gen](https://github.com/r987r/Diagram-gen) – Original 3D diagram generator (inspiration)