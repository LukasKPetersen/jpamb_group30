import jpamb
import jpamb.jvm as jvm
from interpreter import Bytecode, PC
import copy
from pyvis.network import Network

# To run commands, it might be necessary to run: export PYTHONPATH=$(pwd)    

class Node:
    def __init__(self, block_name: int, offset_start: int, offset_end: int | None, cfg_id: int):
        self.cfg_id = cfg_id
        self.block_name = block_name
        self.offset_start = offset_start
        self.offset_end = offset_end
        self.child_edges = []
        self.byte_code = None # Only present if it is a final node in the graph

        self.split_child = None

    # Helper to find the true end of this block chain
    def get_active_tail(self):
        curr = self
        while curr.split_child is not None:
            curr = curr.split_child
        return curr

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
        return f"B{self.block_name}@{self.cfg_id}"

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
    registry: dict[jvm.AbsMethodID, "CFG"] = {}
    cfg_global_counter = 0
    global_method_cache = {}

    bc_length: int
    nodes: dict[int, Node] # key is the start offset of the block

    def __init__(self, suite, methodid: jvm.AbsMethodID):
        self.suite = suite
        self.methodid = methodid
        self.cfg_id = CFG.next_cfg_id()
        self.nodes = {} 
        self.node_counter = 0
        self.bc = Bytecode(suite, CFG.global_method_cache)
        self.init_node = None
        self.building = False
        self.pending_continuations: list[Node] = []
        # register early to allow recursive calls to find this CFG
        CFG.registry[methodid] = self

        # Now actually build
        self.generate_cfg(self.methodid)

    @classmethod
    def next_cfg_id(cls):
        cid = cls.cfg_global_counter
        cls.cfg_global_counter += 1
        return cid

    def new_node_id(self):
        nid = self.node_counter
        self.node_counter += 1
        return nid

    def add_node(self, offset_start, offset_end):
        n = self.nodes.get(offset_start)
        if n is None:
            n = Node(self.new_node_id(), offset_start, offset_end, self.cfg_id)
            self.nodes[offset_start] = n
            return n
        # node already exists — update end if we now have a real end
        if offset_end is not None:
            # update only if previously unknown OR if we want to keep the largest end
            if n.offset_end is None or offset_end > n.offset_end:
                n.offset_end = offset_end
        return n
        # if offset_start not in self.nodes:
        #     self.nodes[offset_start] = Node(self.new_node_id(), offset_start, offset_end, self.cfg_id)           
        #     return self.nodes[offset_start]
        # else:
        #     return self.nodes[offset_start]
        
    def generate_basic_node(self, offset_start: int, target: int, byte_code: jvm.Opcode, pc: PC, branching: bool):
        node = self.add_node(offset_start, pc.offset)

        # We collect the edges first, then attach them to the correct node at the end
        edges_to_attach = []

        if branching and isinstance(byte_code, jvm.InvokeStatic):
            pc += 1
            new_node = self.build(pc, pc.offset)
            edges_to_attach = [Edge(node, new_node, None, None)]
            
        elif branching:
            pc += 1
            pc_copy = copy.copy(pc)
            pc_copy.set(target)

            new_node_1 = self.build(pc, pc.offset, target)
            new_node_2 = self.build(pc_copy, pc_copy.offset)

            edge_1 = Edge(node, new_node_1, byte_code, False)
            edge_2 = Edge(node, new_node_2, byte_code, True)
            edges_to_attach = [edge_1, edge_2]
            
        else:
            # Unconditional Jump / Loop
            if pc.offset > target:
                # Backward Jump Handling
                pc.set(target)
                target_node = None
                
                if target in self.nodes:
                    target_node = self.nodes[target]
                else:
                    # Find and split the existing block
                    for start_off, n in sorted(self.nodes.items()):
                        if n.offset_start < target <= n.offset_end:
                            
                            # 1. Create lower half
                            lower_half = self.add_node(target, n.offset_end)
                            
                            # 2. Truncate upper half
                            n.offset_end = target - 1
                            
                            # 3. Transfer existing edges/bytecode
                            lower_half.child_edges = n.child_edges
                            n.child_edges = [] 
                            
                            if n.is_final_node():
                                lower_half.final_node_bytecode_assignment(n.byte_code)
                                n.byte_code = None

                            # 4. Set the forwarding pointer!
                            n.split_child = lower_half

                            # 5. Link upper to lower
                            fallthrough_edge = Edge(n, lower_half, None, None)
                            n.child_edges.append(fallthrough_edge) # Attach directly to n
                            
                            target_node = lower_half
                            break
                
                assert target_node is not None, f"Could not resolve backward jump to {target}"
                edges_to_attach = [Edge(node, target_node, byte_code, None)]
            else:
                # Forward Jump
                pc.set(target)
                new_node = self.build(pc, pc.offset)
                edges_to_attach = [Edge(node, new_node, byte_code, None)]

        # CRITICAL FIX:
        # If 'node' was split during the recursive build calls above,
        # 'node' now refers to the top half (e.g., 8-18). 
        # But the instructions we just processed (the branches) belong to the bottom half (19-21).
        # We must attach the edges to the *active tail* of the node chain.
        active_node = node.get_active_tail()
        active_node.attach_edges(edges_to_attach)

        return node
    
    def generate_terminating_node(self, offset_start: int, offset_end: int, byte_code: jvm.Opcode):
        node = self.add_node(offset_start, offset_end)
        node.final_node_bytecode_assignment(byte_code)
        return node
    
    def find_return_nodes(self):
        return [n for n in self.nodes.values() if n.is_final_node() and isinstance(n.byte_code, jvm.Return)]

    def finalize_pending_continuations(self):
        # find all return nodes, attach edges to each pending continuation
        returns = self.find_return_nodes()
        visited_cont = set()

        for cont_node in self.pending_continuations:
            if cont_node not in visited_cont:
                visited_cont.add(cont_node)
            else:
                continue
            for r in returns:
                # create edge r -> cont_node (note: branch_opcode can be Return() or None)

                e = Edge(r, cont_node, r.byte_code, None)
                r.child_edges.append(e)
        # clear pending list
        self.pending_continuations.clear()

    def generate_cfg(self, methodid):
        entry = self.add_node(0, None)      # end unknown yet
        self.init_node = entry

        self.building = True
        self.init_node = self.build(PC(methodid, 0), offset_start=0)
        self.building = False
        # Now the CFG is built, satisfy any pending continuations
        self.resolve_overlapping_blocks()

        self.finalize_pending_continuations()


        return self.init_node
    
    def check_nodes_valid(self):
        is_valid = True

        for _, cfg in CFG.registry.items():
            # sort nodes by offset_start
            sorted_nodes = sorted(cfg.nodes.values(), key=lambda n: n.offset_start)
            curr_max_offset = -1

            for node in sorted_nodes:
                if node.offset_start <= curr_max_offset:
                    print(f"Block {node} start offset {node.offset_start} "
                        f"overlaps previous block's end offset {curr_max_offset}")
                    is_valid = False
                curr_max_offset = node.offset_end

        return is_valid
            # for node_name, node in self.nodes.items():
            #     # Find overlapping offsets between nodes
            #     if node.offset_start <= curr_max_offset and node.cfg_id : 
            #         print(f"Block {node} start offset {node.offset_start} overlaps block {self.nodes[node_name-1]}'s end offset {curr_max_offset}")
            #         is_not_valid = False
            #     curr_max_offset = node.offset_end



    def build(self, pc, offset_start=0, cut_off_offset=None):

        self.bc[pc] # Used to extract the length
        self.bc_length = len(self.bc.methods[self.methodid])

        while pc.offset < self.bc_length:

            opr = self.bc[pc]
            # avoid duplication of nodes
            # if self.cfg_id == 1:
                # print(f"offset {pc.offset}, opr: {opr}")
                # print(f"bc_length: {self.bc_length}")
                #for m in self.bc.methods[method]
            match opr:
                case jvm.If(target=t) | jvm.Ifz(target=t):
                    # recursive call must be qualified on the instance (self)
                    node = self.generate_basic_node(offset_start, t, opr, pc, branching=True)
                    return node
                case jvm.Goto(target=t):
                   node = self.generate_basic_node(offset_start, t, opr, pc, branching=False)
                   return node
                case jvm.Return():
                    # Final node
                    # No edges here, they are constructed from the parent node
                    node = self.generate_terminating_node(offset_start, pc.offset, opr)
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
                case jvm.InvokeStatic(method=callee_methodid):
                    if self.methodid.methodid.name == callee_methodid.methodid.name:
                        
                        callsite_node = self.add_node(offset_start, pc.offset)

                        pc += 1
                        continuation_node = self.build(pc, pc.offset)

                        # callee_cfg = CFG.registry.get(callee_methodid)

                        # A recursive call always points back to entry
                        #continuation_edge = Edge(callsite_node, continuation_node, None, None)
                        rec_edge = Edge(callsite_node, self.init_node, opr, None)

                        #callsite_node.child_edges.append(continuation_edge)
                        callsite_node.child_edges.append(rec_edge)

                        # When fib returns, control continues at continuation
                        if not self.building:
                            # callee finished: attach return edges now
                            for r in self.find_return_nodes():

                                e = Edge(r, continuation_node, r.byte_code, None)
                                r.child_edges.append(e)
                            rec_edge = Edge()
                        else:
                            # defer continuation
                            if continuation_node not in self.pending_continuations:
                                self.pending_continuations.append(continuation_node)

                        return callsite_node
                    else:
                        # print(f"Offset {pc.offset} and method invoked: {callee_methodid}")
                        # ---- CALL SITE handling ----
                        # 1) create call-site node covering offset_start..pc.offset (include invoke)
                        callsite_node = self.add_node(offset_start, pc.offset)
                        # print(f"Invokation: {callee_methodid}")
                        # 2) create continuation node for next offset (pc+1)

                        pc += 1
                        continuation_node = self.build(pc, pc.offset)
                        # continuation_node = self.add_node(pc.offset + 1, pc.offset + 1)  # you may expand this later

                        # 3) ensure callee CFG exists (register-only if recursive)
                        # Ensure CFG exists exactly once
                        if callee_methodid not in CFG.registry:
                            CFG(self.suite, callee_methodid)

                        callee_cfg = CFG.registry[callee_methodid]
                        # 4) add call edge callsite -> callee.entry
                        call_edge = Edge(callsite_node, callee_cfg.init_node, opr, None)
                        callsite_node.child_edges.append(call_edge)

                        # 5) do NOT create callsite -> continuation edge; instead let callee returns -> continuation
                        # If callee already finished, attach its return nodes now:
                        if not callee_cfg.building: # if finished building
                            for r in callee_cfg.find_return_nodes():
                                e = Edge(r, continuation_node, r.byte_code, None)
                                r.child_edges.append(e)
                        else:
                            # callee still building (or recursive). record continuation so callee will attach it later.
                            callee_cfg.pending_continuations.append(continuation_node)

                        # After handling call, we must return the callsite node (this ends the block)
                        return callsite_node
                case _:
                    pc += 1

        return self.add_node(offset_start, pc.offset)
    
    def resolve_overlapping_blocks(self):
        """
        Post-processing step to handle cases where a block (B1) overlaps with 
        a subsequent block (B2) that starts in the middle of B1's range.
        """
        # 1. Sort nodes by their start offset
        sorted_nodes = sorted(self.nodes.values(), key=lambda n: n.offset_start)

        for i in range(len(sorted_nodes) - 1):
            current_node = sorted_nodes[i]
            next_node = sorted_nodes[i+1]

            # 2. Check for overlap
            # Example: current (44-47), next (45-47). 
            # 47 >= 45, so they overlap.
            if current_node.offset_end >= next_node.offset_start:
                
                # Debug print to confirm it's working
                # print(f"Splitting overlapping blocks: {current_node} and {next_node}")

                # 3. Truncate the current block
                # Its new end is immediately before the next block starts.
                current_node.offset_end = next_node.offset_start - 1

                # 4. Handle the edges
                # The edges currently attached to 'current_node' were calculated based on 
                # the instruction at the *original* offset_end (e.g., 47). 
                # Since we have cut this block short, it no longer contains that instruction.
                # The logic for offset 47 now resides in 'next_node' (or its successors).
                # Therefore, we strictly clear the old edges.
                current_node.child_edges = []
                
                # If the node was marked as a final node (e.g. Return), but we truncated
                # it before it reached that instruction, it is no longer a final node.
                if current_node.is_final_node():
                    current_node.byte_code = None

                # 5. Connect current -> next
                # As requested: Edge with bytecode=None, eval=None (pure fall-through)
                fallthrough_edge = Edge(current_node, next_node, None, None)
                current_node.attach_edges([fallthrough_edge])

    def _print_graph(self, node=None, visited=None):
        if visited == None:
            visited = set()
        if node == None:
            total_n_nodes = 0
            for _, cfg in CFG.registry.items():
                total_n_nodes += len(cfg.nodes)
            print("Printing graph parameters...")
            print()
            print(f"Total number of nodes in graph is {total_n_nodes}")
            print(f"Total number of CFG's are {len(self.registry)}")
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
        print("#" * 80)
        self._print_graph()
        print("#" * 80)

# It just extracts a methodid
methodid = jpamb.extract_methodid()
suite = jpamb.Suite()

cfg = CFG(suite, methodid) # Create CFG

cfg.print_graph_param()

if cfg.check_nodes_valid() is False:
    print(" ** Network not valid! ** ")

def visualize_cfg_pyvis(cfg):
    net = Network(directed=True, height="750px", width="100%", notebook=False)
    # enable physics so nodes don't overlap
    net.barnes_hut(gravity=-80000, central_gravity=0.3, spring_length=200, spring_strength=0.05, damping=0.09)

    visited = set()

    def dfs(node):
        if node in visited:
            return
        visited.add(node)

        if node.is_final_node():
            net.add_node(id(node),
                label=f"{node}\n{{{node.offsets()}}}\n{node.byte_code}",
                color="lightgreen" if node == cfg.init_node else "lightblue",
                size=25 if node == cfg.init_node else 20,
                font={"size": 16})
        else:
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
                
            if edge.eval == None and edge.branch_opcode == None:
                net.add_edge(id(node), id(edge.end_node),
                         label="", #TODO: should there be text here?
                         font={"size": 20, "align": "top"},
                         arrows="to")
            elif edge.eval == None:
                net.add_edge(id(node), id(edge.end_node),
                         label=f"{str(edge.branch_opcode)}",
                         font={"size": 20, "align": "top"},
                         arrows="to")
            else:
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