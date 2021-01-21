################################################################################
##############      This library has been created by      ######################
##############            Md Mahabubul Alam               ###################### 
############## https://mahabubul-alam.github.io/Personal/ ######################
##############         Graduate Student (Ph.D.)           ######################
##############   Department of Electrical Engineering     ######################
##############      Pennsylvania State University         ######################
##############         University Park, PA, USA           ###################### 
##############               mxa890@psu.edu               ######################
################################################################################

import json
import networkx as nx
from qiskit.circuit import Parameter
from qiskit import *
import math
import re


class Compile_QAOA_Qiskit:
    def __init__(self, Circuit_json=None, QC_json=None, Config_json=None, Out_Circuit_File_Name='QAOA.qasm'):
        """ """
        self.Load_Config(Config_json)
        self.Output_File_Name = Out_Circuit_File_Name
        self.Extract_QC_Data(QC_json)
        self.Layer_ZZ_Assignments = {}
        self.ZZ_graph = self.QAOA_ZZ_graph(Circuit_json)
        self.Initial_Layout = list(range(len(self.ZZ_graph.nodes())))

    def Load_Config(self,Config_json=None):
        """ """
        with open(Config_json) as f:
            self.Config = json.load(f)

        if 'Target_p' in self.Config.keys(): self.Target_p = int(self.Config['Target_p'])
        else: self.Target_p = 1
        if 'Packing_Limit' in self.Config.keys(): self.Packing_Limit = float(self.Config['Packing_Limit'])
        else: self.Packing_Limit = 10e10
        if 'Route_Method' in self.Config.keys(): self.Route_Method = self.Config['Route_Method']
        else: self.Route_Method = 'sabre'
        if 'Trans_Seed' in self.Config.keys(): self.Trans_Seed = int(self.Config['Trans_Seed'])
        else: self.Trans_Seed = 0
        if 'Opt_Level' in self.Config.keys(): self.Opt_Level = int(self.Config['Opt_Level'])
        else: self.Opt_Level = 1
    
    def set_IterC_Target(self,Target='GC_2Q'):
        """ """
        self.IterC_Target = Target

    def set_IncrC_VarAwareness(self,Variation_Aware=False):
        """ """
        self.IncrC_VarAwareness = Variation_Aware


    def Extract_QC_Data(self,QC_file=None):
        """ """

        with open(QC_file) as f:
            self.QC_DATA = json.load(f)

        self.Native_2Q = eval(self.QC_DATA['2Q'].strip('"'))
        self.Native_1Q = eval(self.QC_DATA['1Q'].strip('"'))
        self.Basis_Gates = self.Native_2Q + self.Native_1Q
        
        self.Coupling_Map = []
        for key in self.QC_DATA[str(self.Native_2Q[0])].keys():
            n1, n2 = eval(key)[0], eval(key)[1]
            if [n1,n2] not in self.Coupling_Map:
                self.Coupling_Map.append([n1,n2])
            if [n2,n1] not in self.Coupling_Map:
                self.Coupling_Map.append([n2,n1])
        
        self.Calc_QQ_Distances()

    def Calc_QQ_Distances(self):
        """ """

        self.Unweighted_Undirected_Coupling_Graph = nx.Graph()
        self.Weighted_Undirected_Coupling_Graph = nx.Graph()

        for key, value in self.QC_DATA[str(self.Native_2Q[0])].items():
            n1, n2, sp = eval(key)[0], eval(key)[1], float(value)
            self.Unweighted_Undirected_Coupling_Graph.add_edge(n1,n2)
            self.Weighted_Undirected_Coupling_Graph.add_edge(n1,n2,weight=1/sp)
        
        self.QQ_Distances = nx.floyd_warshall(self.Unweighted_Undirected_Coupling_Graph)
        self.Noise_Aware_QQ_Distances = nx.floyd_warshall(self.Weighted_Undirected_Coupling_Graph)


    
    @staticmethod
    def QAOA_ZZ_graph(circ_json=None):
        """ """
        #print(circ_json)
        with open(circ_json) as f:
            data = json.loads(f.read())

        ZZ_graph = nx.Graph()
        for key, val in data.items():
            nodes = eval(val)
            ZZ_graph.add_edge(nodes[0],nodes[1])
        return ZZ_graph
    
    def find_final_mapping_IC(self,qiskit_ckt_object):
        
        qiskit_ckt_object.qasm(filename='tempfile')
        os.system('grep measure tempfile | awk \'{print $2, $4}\' > temp')
        qreg_creg_map = open('temp','r').readlines()

        FMAP = {}


        for line in qreg_creg_map:

            elements = line.split(' ')
            physical_qs = elements[0]
            logical_qs = str(elements[1]).split(';')[0]

            physical_q = re.search('\[.*\]',physical_qs).group()
            physical_q = re.sub('\[|\]','',physical_q)

            logical_q = re.search('\[.*\]',logical_qs).group()
            logical_q = re.sub('\[|\]','',logical_q)

            FMAP[logical_q[0:]] = int(physical_q[0:])

        final_map = []
        
        for i in range(len(self.ZZ_graph.nodes())):
            final_map.append(FMAP[str(i)])
        
        os.system('rm temp')
        os.system('rm tempfile')
        
        return final_map


    
    def _set_Initial_Layout(self,target_layout=None):
        """ """
        if target_layout:
            self.Initial_Layout = target_layout

    def sort_zz_by_QQ_distances(self,Unsorted_ops=None):
        """ """
        Sorted_ops = []
        Swap_distances_ops = {}

        for op in Unsorted_ops:
            _physical_q1 = self.Initial_Layout[op[0]]
            _physical_q2 = self.Initial_Layout[op[1]]
            if not self.IncrC_VarAwareness:
                swap_dist = self.QQ_Distances[_physical_q1][_physical_q2]
            else:
                swap_dist = self.Noise_Aware_QQ_Distances[_physical_q1][_physical_q2]

            Swap_distances_ops[op] = swap_dist

        for op in Unsorted_ops:

            if not Sorted_ops:
                Sorted_ops.append(op)
                continue

            i = 0
            for sop in Sorted_ops:
                if Swap_distances_ops[op] < Swap_distances_ops[sop]:
                    Sorted_ops.insert(i,op)
                    break
                i = i + 1

            if i == len(Sorted_ops):
                Sorted_ops.append(op)

        return Sorted_ops

    def construct_single_layer_ckt_IC(self,p):
        """ """

        #print('Single_Layer_Constr: {}'.format(self.Initial_Layout))
        n = len(self.ZZ_graph.nodes())
        qc = QuantumCircuit(n, n)

        for zz in self.Layer_ZZ_Assignments['L0']:
            n1 = zz[0]
            n2 = zz[1]
            gamma = Parameter('g{}_{}_{}'.format(p,n1,n2))
            qc.cx(n1, n2)
            qc.rz(gamma, n2)
            qc.cx(n1, n2)

        qc.measure(range(n), range(n))


        trans_ckt = transpile(qc, coupling_map = self.Coupling_Map, \
                basis_gates = self.Basis_Gates, initial_layout = self.Initial_Layout, \
                optimization_level = self.Opt_Level, seed_transpiler = self.Trans_Seed, routing_method = self.Route_Method)

        return trans_ckt

    def Incremental_Compilation(self):
        """ """
        logical_n = len(self.ZZ_graph.nodes())
        physical_n = len(self.Unweighted_Undirected_Coupling_Graph.nodes())
        IncrC_qc = QuantumCircuit(physical_n, logical_n)

        for i in range(logical_n):
            IncrC_qc.h(self.Initial_Layout[i])

        for p in range(1,self.Target_p+1):

            Remaining_ops = self.ZZ_graph.edges()

            while Remaining_ops:

                Sorted_ops = self.sort_zz_by_QQ_distances(Remaining_ops)
                self.Instruction_Parallelization(Sorted_ops,Single_Layer=True)
            
                Remaining_ops = self.Layer_ZZ_Assignments['R']

                new_ckt_segment = self.construct_single_layer_ckt_IC(p)
                final_map = self.find_final_mapping_IC(new_ckt_segment)
                self._set_Initial_Layout(final_map)

                new_ckt_segment.remove_final_measurements(inplace=True)
                IncrC_qc = IncrC_qc + new_ckt_segment
            
            beta = Parameter('b{}'.format(p))
            for node in range(logical_n):
                IncrC_qc.rx(beta,self.Initial_Layout[node])

            IncrC_qc.barrier()

        for i in range(logical_n):
            IncrC_qc.measure(self.Initial_Layout[i],i)

        IncrC_qc.qasm(self.Output_File_Name)
        return IncrC_qc


    
    def Instruction_Parallelization(self,Sorted_Edges=None,Single_Layer=False):
        """ """
        Logical_qubits = self.ZZ_graph.nodes()
        if Sorted_Edges:
            Remaining_edges = Sorted_Edges.copy()
        else:
            Remaining_edges = list(self.ZZ_graph.edges())
        
        Current_layer = 'L0'
        Layer_occupancy = {Current_layer: list()}
        for qubit in Logical_qubits:
            Layer_occupancy[Current_layer].insert(len(Layer_occupancy[Current_layer]),[qubit,'FREE'])
        self.Layer_ZZ_Assignments[Current_layer] = list()

        while True:
            Unallocated_edges = list()
            allocated_op_count_in_this_layer = 0
            for edge in Remaining_edges:
                if allocated_op_count_in_this_layer >= self.Packing_Limit:
                    Unallocated_edges.insert(len(Unallocated_edges),edge)
                    continue

                n1, n2 = edge[0], edge[1]
                Free_among_the_two = 0

                for Occupancy_info_list in Layer_occupancy[Current_layer]:
                    if Occupancy_info_list[0] in edge:
                        if Occupancy_info_list[1] == 'OCCUPIED':
                            Unallocated_edges.insert(len(Unallocated_edges),edge)
                            break
                        else:
                            Free_among_the_two = Free_among_the_two + 1
                    if Free_among_the_two == 2:
                        n1_indx = Layer_occupancy[Current_layer].index([n1,'FREE'])
                        n2_indx = Layer_occupancy[Current_layer].index([n2,'FREE'])
                        Layer_occupancy[Current_layer][n1_indx] = [n1,'OCCUPIED']
                        Layer_occupancy[Current_layer][n2_indx] = [n2,'OCCUPIED']
                        self.Layer_ZZ_Assignments[Current_layer].insert(len(Layer_occupancy[Current_layer]),edge)
                        allocated_op_count_in_this_layer = allocated_op_count_in_this_layer + 1
                        break

            Remaining_edges = Unallocated_edges

            if Single_Layer:
                #print('Single layer formed!')
                self.Layer_ZZ_Assignments['R'] = list()
                for edge in Remaining_edges:
                    self.Layer_ZZ_Assignments['R'].insert(0,edge)
                break
            elif len(Remaining_edges) != 0:
                Next_layer = int(Current_layer[1:])+1
                Current_layer = 'L' + str(Next_layer)
                Layer_occupancy[Current_layer] = list()
                self.Layer_ZZ_Assignments[Current_layer] = list()
                for qubit in Logical_qubits:
                    Layer_occupancy[Current_layer].insert(len(Layer_occupancy[Current_layer]),[qubit,'FREE'])
            else:
                #print('All layers formed!')
                break

    def Iterative_Compilation(self):
        """ """
        interchange = []
        LOO = []
        for L in self.Layer_ZZ_Assignments.keys():
            LOO.append(L)

        opt_target = 10e10
        opt_ckt = None

        while True:
            for layer_1 in range(len(LOO)):
                for layer_2 in range(layer_1+1,len(LOO)):
                    Temp = LOO.copy()
                    Temp[layer_1], Temp[layer_2] = Temp[layer_2], Temp[layer_1]
                    trial_ckt = self.Construct_Circuit_IterC(Temp)
                    trial_target = self.Calc_Cost(trial_ckt)

                    if trial_target < opt_target:
                        interchange = [layer_1, layer_2]
                        opt_target = trial_target
                        opt_ckt = trial_ckt

            if not interchange:
                opt_ckt.qasm(self.Output_File_Name)
                return opt_ckt
            else:
                layer_1 = interchange[0]
                layer_2 = interchange[1]
                LOO[layer_1], LOO[layer_2] = LOO[layer_2], LOO[layer_1]
                #print('Interchanged: %s, %s, Cost: %s\n' % (layer_1, layer_2, opt_target))
                interchange = []
    
    
    def Calc_Cost(self,circ=None):
        if self.IterC_Target == 'GC_2Q':
            return circ.count_ops()[self.Native_2Q[0]]
        elif self.IterC_Target == 'D':
            return circ.depth()
        elif self.IterC_Target == 'ESP':
            return self.Estimate_SP(circ)

    def Estimate_SP(self, circ=None):
        ESP = 1
        while True:
            if circ._data:
                k = circ._data.pop()
                GATE = k[0].__dict__['name']
                if GATE not in self.Basis_Gates:
                    continue
                QUB = []
                for i in range(len(k[1])):
                    QUB.append(k[1][i].index)
                if len(QUB) == 1:
                    ESP = ESP*float(self.QC_DATA[GATE][str(QUB[0])])
                else:
                    ESP = ESP*float(self.QC_DATA[GATE]['({},{})'.format(QUB[0],QUB[1])])
            else:
                break
        return -math.log(ESP)


    def Construct_Circuit_IterC(self,LO=None):
        """ """

        n = len(self.ZZ_graph.nodes())
        qc = QuantumCircuit(n, n)

        # superposition state applying hadamard to all the qubits
        for node in self.ZZ_graph.nodes():
            qc.h(node)

        # change based on the mixing and phase separation layer architectures
        for p in range(1,self.Target_p+1):
            for L in LO:
                # phase seperation depends on the number of edges
                for edge in self.Layer_ZZ_Assignments[L]:
                    n1 = edge[0]
                    n2 = edge[1]
                    gamma = Parameter('g{}_{}_{}'.format(p,n1,n2)) 
                    qc.cx(n1, n2)
                    qc.rz(gamma, n2)
                    qc.cx(n1, n2)

            # mixing depends on the number of nodes rx gates
            beta = Parameter('b{}'.format(p))
            for node in self.ZZ_graph.nodes():
                qc.rx(beta,node)

            qc.barrier()

        qc.measure(range(n),range(n))

        trans_ckt = transpile(qc, coupling_map = self.Coupling_Map, \
                basis_gates = self.Basis_Gates, initial_layout = self.Initial_Layout, \
                optimization_level = self.Opt_Level, seed_transpiler = self.Trans_Seed, routing_method = self.Route_Method)

        return trans_ckt

    def run_IP(self):
        """ """
        self.Instruction_Parallelization()
        LO = self.Layer_ZZ_Assignments.keys()
        ckt = self.Construct_Circuit_IterC(LO)
        ckt.qasm(self.Output_File_Name)
        return ckt


    def run_IterC(self,Target='D'):
        """ """
        self.set_IterC_Target(Target)
        self.Instruction_Parallelization()
        ckt = self.Iterative_Compilation()
        return ckt

    def run_IncrC(self,Variation_Aware=False):
        """ """
        self.set_IncrC_VarAwareness(Variation_Aware)
        ckt = self.Incremental_Compilation()
        return ckt








#obj = Compile_QAOA_Qiskit('small.json','QC.json','Config.json')
#ckt1 = obj.run_IP()
#ckt2 = obj.run_IterC()
#ckt3 = obj.run_IncrC()


