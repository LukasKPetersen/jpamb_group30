import jpamb
import jpamb.jvm as jvm
from interpreter.interpreter import Bytecode, PC
import copy
from pyvis.network import Network

# To run commands, it might be necessary to run: export PYTHONPATH=$(pwd)    

class Node:
    def __init__(self, block_name: int, offset_start: int, offset_end: int):
        self.block_name = block_name
        self.offset_start = offset_start
        self.offset_end = offset_end
        self.child_edges = []
        self.byte_code = None # Only present if it is a final node in the graph

    def is_final_node(self):
        if self.byte_code == None:
            return False
        else:
            return True

    def final_node_bytecode_assignment(self, byte_code: jvm.Opcode):
        self.byte_code = byte_code

    def attach_edges(self, edges):
        # Always set the true child at index=0 and false at index=1
        # If there is not two children, then just have index 0
        self.child_edges = edges

    def __str__(self):
        return f"B{self.block_name}"

    def offsets(self):
        return f"{self.offset_start} - {self.offset_end}"

class Edge:
    def __init__(self, start_node: Node, end_node: Node, branch_opcode: jvm.Opcode, eval: bool):
        self.start_node = start_node
        self.end_node = end_node
        self.branch_opcode = branch_opcode
        self.eval = eval

    def __str__(self):
        return f"Edge: {self.start_node} -> {self.end_node}"

class CFG:
    bc_length: int
    nodes: dict[int, Node] # key is the start offset of the block

    def __init__(self, methodid: jvm.AbsMethodID):
        self.nodes = {} 
        self.node_counter = 0
        self.bc = Bytecode(jpamb.Suite(), dict())
        self.methodid = methodid
        self.init_node = self.generate_cfg(self.methodid)

    def new_node_id(self):
        nid = self.node_counter
        self.node_counter += 1
        return nid

    def add_node(self, offset_start, offset_end):
        if offset_start not in self.nodes:
            self.nodes[offset_start] = Node(self.new_node_id(), offset_start, offset_end)           
            return self.nodes[offset_start]
        else:
            return self.nodes[offset_start]
        
    def generate_basic_node(self, offset_start: int, target: int, byte_code: jvm.Opcode, pc: PC):

        node = self.add_node(offset_start, pc.offset)
        # Increment program counter
        pc += 1
        pc_copy = copy.copy(pc)
        pc_copy.set(target)
        # Make the branching nodes
        new_node_1 = self.build(pc, pc.offset)
        new_node_2 = self.build(pc_copy, pc_copy.offset)
        # Edges for graph
        # Note: When a jump is made, that trace satisfied the condition
        edge_1 = Edge(node, new_node_1, byte_code, False)
        edge_2 = Edge(node, new_node_2, byte_code, True)
        # Attach edges to node
        node.attach_edges([edge_1, edge_2])

        return node
    
    def generate_terminating_node(self, offset_start: int, offset_end: int, byte_code: jvm.Opcode):
        node = self.add_node(offset_start, offset_end)
        node.final_node_bytecode_assignment(byte_code)
        return node

    def generate_cfg(self, methodid):
        pc = PC(methodid, 0)
        return self.build(pc)
    
    def check_nodes_valid(self):

        curr_max_offset = -1
        is_not_valid = True

        for node_name, node in self.nodes.items():
            # Find overlapping offsets between nodes
            if node.offset_start <= curr_max_offset: 
                print(f"Block {node} start offset {node.offset_start} overlaps block {self.nodes[node_name-1]}'s end offset {curr_max_offset}")
                is_not_valid = False
            curr_max_offset = node.offset_end

        return is_not_valid



    def build(self, pc, offset_start=0):

        self.bc[pc] # Used to extract the length
        self.bc_length = len(self.bc.methods[methodid])

        while pc.offset < self.bc_length:

            opr = self.bc[pc]
            # avoid duplication of nodes

            match opr:
                case jvm.If(target=t) | jvm.Ifz(target=t):
                    # recursive call must be qualified on the instance (self)
                    node = self.generate_basic_node(offset_start, t, opr, pc)
                    return node
                case jvm.Return():
                    # Final node
                    # No edges here, they are constructed from the parent node
                    node = self.generate_terminating_node(offset_start, pc.offset, opr)
                    # node = self.add_node(offset_start, pc.offset)

                    pc += 1
                    return node
                case jvm.InvokeSpecial(method=method_name):
                    string_method = str(method_name)[:24]
                    assert string_method == "java/lang/AssertionError", f"Only assertion errors are handled so far, not {string_method}"

                    if string_method == "java/lang/AssertionError":
                        # It is guaranteed that it will throw the error. Find the pc offset where it throws
                        while (not isinstance(opr, jvm.Throw)):
                            pc += 1
                            opr = self.bc[pc]
                        
                        node = self.generate_terminating_node(offset_start, pc.offset, opr)
                        return node
                case _:
                    pc += 1

    def _print_line(self):
        print("#" * 80)

    def _print_graph(self, node=None, visited=None):
        if visited == None:
            visited = set()
        if node == None:

            print("Printing graph parameters...")
            print()
            print(f"Total number of nodes in graph is {len(self.nodes)}")
            print()
            print("Node  Block offsets           Edges")
            print("-" * 80)
            node = self.init_node
        if node in visited:
            return
        visited.add(node)

        edges = ", ".join(str(e) for e in node.child_edges)
        print(f"{node}: {{offsets: {node.offset_start} - {node.offset_end}}} ",
              f"{{{edges}}}"
        )

        for i in range(len(node.child_edges)):
            self._print_graph(node.child_edges[i].end_node, visited)

    def print_graph_param(self):
        # Used for debugging to view the graph parameters
        self._print_line()
        self._print_graph()
        self._print_line()

# It just extracts a methodid
methodid = jpamb.extract_methodid()
cfg = CFG(methodid) # Create CFG

cfg.print_graph_param()
if cfg.check_nodes_valid() is False:
    print("Network not valid!")

def visualize_cfg_pyvis(cfg):
    net = Network(directed=True, height="750px", width="100%", notebook=False)
    # enable physics so nodes don't overlap
    net.barnes_hut(gravity=-80000, central_gravity=0.3, spring_length=200, spring_strength=0.05, damping=0.09)

    visited = set()

    def dfs(node):
        if node in visited:
            return
        visited.add(node)

        net.add_node(id(node),
             label=f"{node}\n{{{node.offsets()}}}",
             color="lightgreen" if node == cfg.init_node else "lightblue",
             size=25 if node == cfg.init_node else 20,
             font={"size": 16})
        # net.add_node(id(node),
        #              label=f"{node}\n{{{node.offsets()}}}")

        for edge in node.child_edges:
            if edge.end_node.is_final_node():
                net.add_node(id(edge.end_node),
                         label=f"{edge.end_node}\n{{{edge.end_node.offsets()}}}\n{str(edge.end_node.byte_code)}")
            else:        
                net.add_node(id(edge.end_node),
                         label=f"{edge.end_node}\n{{{edge.end_node.offsets()}}}")
            
            net.add_edge(id(node), id(edge.end_node),
                         label=f"{str(edge.branch_opcode)} : {str(edge.eval)}",
                         font={"size": 20, "align": "top"},
                         arrows="to")

            # net.add_edge(id(node), id(edge.end_node),
            #              label=f"{str(edge.branch_opcode)} : {str(edge.eval)}")
            dfs(edge.end_node)

    dfs(cfg.init_node)

    net.write_html("cfg.html", open_browser=True)
    print("Wrote cfg.html")

visualize_cfg_pyvis(cfg)