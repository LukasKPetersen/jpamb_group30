from pyvis.network import Network
import os
from jpamb import jvm

def visualize_cfg_pyvis(cfg, suite, methodid):
    # net = Network(directed=True, height="750px", width="100%", notebook=False)
    net = Network(directed=True, height="750px", width="100%", notebook=False, 
                  bgcolor="#222222", font_color="white")
    # enable physics so nodes don't overlap
    net.barnes_hut(gravity=-80000, central_gravity=0.3, spring_length=200, spring_strength=0.05, damping=0.09)

    visited = set()

    def dfs(node):
        if node in visited:
            return
        visited.add(node)

        # 2. Add white font color to nodes
        if node.is_final_node():
            net.add_node(id(node),
                label=f"{node}\n{{{node.offsets()}}}\n{node.byte_code}",
                color="lightgreen" if node == cfg.init_node else "lightblue",
                size=25 if node == cfg.init_node else 20,
                font={"size": 16, "color": "white"})
        else:
            net.add_node(id(node),
                label=f"{node}\n{{{node.offsets()}}}",
                color="lightgreen" if node == cfg.init_node else "lightblue",
                size=25 if node == cfg.init_node else 20,
                font={"size": 16, "color": "white"})

        for edge in node.child_edges:
            # Add child nodes with white font as well
            if edge.end_node.is_final_node():
                net.add_node(id(edge.end_node),
                         label=f"{edge.end_node}\n{{{edge.end_node.offsets()}}}\n{str(edge.end_node.byte_code)}",
                         font={"size": 16, "color": "white"}) # Added styling here just in case
            else:        
                net.add_node(id(edge.end_node),
                         label=f"{edge.end_node}\n{{{edge.end_node.offsets()}}}",
                         font={"size": 16, "color": "white"}) # Added styling here just in case
            
            # 3. Add white font color to edges
            if edge.is_fallthrough_edge:
                net.add_edge(id(node), id(edge.end_node),
                         label="split-block edge",
                         font={"size": 20, "align": "top", "color": "white", "strokeWidth": 0.6, "face": "arial"},
                         arrows="to")
            elif edge.eval == None and edge.branch_opcode == None:
                net.add_edge(id(node), id(edge.end_node),
                         label="", 
                         font={"size": 20, "align": "top", "color": "white", "strokeWidth": 0.6, "face": "arial"},
                         arrows="to")
            elif edge.eval == None:
                net.add_edge(id(node), id(edge.end_node),
                         label=f"{str(edge.branch_opcode)}",
                         font={"size": 20, "align": "top", "color": "white", "strokeWidth": 0.6, "face": "arial"},
                         arrows="to")
            else:
                net.add_edge(id(node), id(edge.end_node),
                         label=f"{str(edge.branch_opcode)} : {str(edge.eval)}",
                         font={"size": 20, "align": "top", "color": "white", "strokeWidth": 0.6, "face": "arial"},
                         arrows="to")

            dfs(edge.end_node)

    dfs(cfg.init_node)
    
    # --- File Writing Section ---
    output_folder = "CFG_visuals"
    os.makedirs(output_folder, exist_ok=True)
    file_path = os.path.join(output_folder, f"{str(methodid)}.html")

    net.write_html(file_path, open_browser=True)    
    print(f"Wrote {file_path}")

    # --- Extracting Bytecode ---
    def inspect_return_str(suite, method, format):
        method = jvm.AbsMethodID.decode(method)
        s = ""
        for i, res in enumerate(suite.findmethod(method)["code"]["bytecode"]):
            op = jvm.Opcode.from_json(res)
 
            match format:
                case "pretty":
                    res = str(op)
                case "real":
                    res = op.real()
                case "repr":
                    res = repr(op)
                # case "json":
                    # res = json.dumps(res)
            s += f"{i:03d} | {res}\n"
        return s[:-2] # Remove the last newline

    s = inspect_return_str(suite, str(methodid), "pretty")


    # --- Compute longest line width for auto-sizing the panel ---
    max_line_len = max(len(line) for line in s.split("\n"))
    # Approximate monospace width in pixels (≈8.2px per char)
    panel_width_px = int(max_line_len * 8.2) + 40  # +padding

    # --- Bytecode Panel (toggle-able) ---
    bytecode_html = f"""
    <div id="bytecodePanel" style="
        position: fixed;
        bottom: 10px;
        left: 10px;
        z-index: 9998;
        background-color: rgba(30, 30, 30, 0.95);
        border: 1px solid #555;
        border-radius: 8px;
        padding: 12px;
        width: {panel_width_px}px;
        max-height: 400px;
        overflow-y: auto;
        font-family: 'Courier New', monospace;
        font-size: 13px;
        color: #eee;
        box-shadow: 0 4px 8px rgba(0,0,0,0.5);
    ">

        <!-- Hide button -->
        <button onclick="document.getElementById('bytecodePanel').style.display='none';
                        document.getElementById('bytecodeToggleButton').style.display='block';"
            style="
                position: absolute;
                top: 4px;
                right: 6px;
                background: none;
                border: none;
                color: #bbb;
                cursor: pointer;
                font-size: 18px;
            ">&times;</button>

        <h3 style="margin: 0 0 10px 0; color: #ddd; font-family: Arial, sans-serif;">
            Bytecode
        </h3>

        <pre style="white-space: pre;">{s}</pre>

    </div>
    """

    # Toggle button (hidden initially)
    bytecode_toggle_button = """
    <button id="bytecodeToggleButton"
        onclick="document.getElementById('bytecodePanel').style.display='block';
                this.style.display='none';"
        style="
            position: fixed;
            bottom: 10px;
            left: 10px;
            z-index: 9999;
            background-color: #3A7AFE;
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 5px;
            cursor: pointer;
            display: none;
            font-family: Arial, sans-serif;
            font-weight: bold;
            box-shadow: 0 2px 4px rgba(0,0,0,0.4);
    ">
        Show Bytecode
    </button>
    """

    # --- HTML Injection Section ---
    with open(file_path, "r", encoding="utf-8") as f:
        html = f.read()

    # 1. Create the Header
    header_html = f"<h1 style='text-align:center; color: white; font-family: Arial, sans-serif;'>CFG for {methodid}</h1>"

    # 2. Create the Legend Table (Fixed top-left) - Now includes an 'X' button to hide it.
    legend_html = """
    <div id="cfgLegend" style="
        position: fixed; 
        top: 10px; 
        left: 10px; 
        z-index: 9999; 
        background-color: rgba(50, 50, 50, 0.9); 
        border: 1px solid #777; 
        border-radius: 8px; 
        padding: 15px; 
        color: white; 
        font-family: Arial, sans-serif; 
        font-size: 14px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.5);
        max-width: 300px; /* Limits the width to force wrapping */
    ">
        <!-- Close Button: Hides legend and shows the toggle button -->
        <button onclick="document.getElementById('cfgLegend').style.display = 'none'; document.getElementById('legendToggleButton').style.display = 'block';" style="
            position: absolute; 
            top: 5px; 
            right: 5px; 
            background: none; 
            border: none; 
            color: #ccc; 
            cursor: pointer; 
            font-size: 20px;
            padding: 5px;
        ">&times;</button>

        <h3 style="margin-top: 0; border-bottom: 1px solid #777; padding-bottom: 5px;">CFG info</h3>
        
        <!-- Initial Node -->
        <div style="display: flex; align-items: center; margin-bottom: 10px;">
            <div style="width: 20px; height: 20px; background-color: lightgreen; border-radius: 3px; margin-right: 10px; border: 1px solid white;"></div>
            <span><strong>Initial Node</strong></span>
        </div>

        <!-- Node ID Section -->
        <div style="margin-bottom: 10px;">
            <span style="color: #aaa; font-size: 13px; font-weight: 500;">Each node has an ID label starting with a B</span><br>
            <strong>Node ID:</strong> <span style="color: #ccc;">Node number @ CFG number</span>
        </div>

        <!-- Offsets Section -->
        <div style="margin-bottom: 10px;">
            <span style="color: #aaa; font-size: 13px; font-weight: 500;">Its bytecode coverage is explicitly stated</span><br>
            <strong>Offsets:</strong> <span style="color: #ccc;">{ Start offset - End offset }</span>
        </div>
        
        <!-- Assertion Info Section (Line breaks removed, wraps naturally) -->
        <hr style="border-color: #555; margin: 10px 0;">
        <div style="font-style: italic; margin-top: 10px; font-size: 13px;">
            <span style="color: #ccc;">The bytecode instructions related to assertion enablement are not represented here as edges. All CFGs are built on the assumption that assertions are enabled.</span>
        </div>
    </div>
    """

    # 3. Create a persistent toggle button (initially hidden)
    toggle_button_html = """
    <button id="legendToggleButton" onclick="document.getElementById('cfgLegend').style.display = 'block'; this.style.display = 'none';" style="
        position: fixed; 
        top: 10px; 
        left: 10px; 
        z-index: 10000; 
        background-color: #4CAF50; /* Distinct color */
        color: white; 
        border: none; 
        padding: 8px 15px; 
        border-radius: 5px; 
        cursor: pointer; 
        font-family: Arial, sans-serif;
        font-weight: bold;
        display: none; /* Initially hidden */
        box-shadow: 0 2px 4px rgba(0,0,0,0.4);
    ">
        Show Legend
    </button>
    """

    # --- Inject it into <body> BEFORE your legend panel ---
    html = html.replace(
        "<body>",
        f"<body style='background-color: #222222;'>\n{bytecode_html}\n{bytecode_toggle_button}\n{legend_html}\n{toggle_button_html}\n{header_html}"
    )

    # 4. Inject all components into the Body
    # html = html.replace("<body>", f"<body style='background-color: #222222;'>\n{legend_html}\n{toggle_button_html}\n{header_html}")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html)