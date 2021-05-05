from topological_codes import (
    _Stabilizer,
    LatticeError,
    _TopologicalLattice,
    TopologicalQubit,
)
from qiskit import QuantumRegister, QuantumCircuit, ClassicalRegister, execute
from qiskit.circuit.quantumregister import Qubit
from typing import Dict, List, Tuple, Optional

TQubit = Tuple[float, float, float]


class _XXXX(_Stabilizer):
    """
    X-syndrome plaquette of the rotated surface code.
    """

    def entangle(self) -> None:
        """
        Traverse in reverse "Z" pattern
        """
        syndrome = self.qubit_indices[0]
        top_l = self.qubit_indices[1]
        top_r = self.qubit_indices[2]
        bot_l = self.qubit_indices[3]
        bot_r = self.qubit_indices[4]

        if (top_r and not top_l) or (bot_r and not bot_l):
            raise LatticeError("Inconsistent X syndrome connections")

        self.circ.h(syndrome)
        if top_r:
            self.circ.cx(syndrome, top_r)
            self.circ.cx(syndrome, top_l)
        if bot_r:
            self.circ.cx(syndrome, bot_r)
            self.circ.cx(syndrome, bot_l)
        self.circ.h(syndrome)


class _ZZZZ(_Stabilizer):
    """
    Z-syndrome plaquette of the rotated surface code.
    """

    def entangle(self) -> None:
        """
        Traverse in reverse "N" pattern
        """
        syndrome = self.qubit_indices[0]
        top_l = self.qubit_indices[1]
        top_r = self.qubit_indices[2]
        bot_l = self.qubit_indices[3]
        bot_r = self.qubit_indices[4]

        if (top_r and not bot_r) or (top_l and not bot_l):
            raise LatticeError("Inconsistent Z syndrome connections")

        if top_r:
            self.circ.cx(top_r, syndrome)
            self.circ.cx(bot_r, syndrome)
        if top_l:
            self.circ.cx(top_l, syndrome)
            self.circ.cx(bot_l, syndrome)


class _XXZZLattice(_TopologicalLattice[TQubit]):
    """
    This class contains all the lattice geometry specifications regarding the XXZZ (CSS) Rotated Surface Code.
    """

    def __init__(self, params: Dict[str, int], name: str, circ: QuantumCircuit) -> None:
        """
        Initializes this Topological Lattice class.
        
        Args:
            params (Dict[str,int]): 
                Contains params such as d, where d is the number of physical "data" qubits lining a row or column of the lattice. 
                Only odd d is possible!
            name (str):
                Useful when combining multiple TopologicalQubits together. Prepended to all registers.
            circ (QuantumCircuit):
                QuantumCircuit on top of which the topological qubit is built. This is often shared amongst multiple TQubits.
        """

        # validation
        required_params = ["d"]
        for required_param in required_params:
            if required_param not in params:
                raise LatticeError(f"Please include a {required_param} param.")
        if params["d"] % 2 != 1:
            raise LatticeError("Surface code distance must be odd!")

        # calculated params
        params["T"] = -1  # -1 until a stabilizer round is added!
        params["num_readout"] = -1  # -1 until a logical readout is performed!
        params["num_lattice_readout"] = -1  # -1 until a lattice readout is performed!
        params["num_data"] = params["d"] ** 2
        params["num_syn"] = (params["d"] ** 2 - 1) // 2

        # create registers
        qregisters: Dict[str, QuantumRegister] = {}  # quantum
        qregisters["data"] = QuantumRegister(params["num_data"], name=name + "_data")
        # We use name=name (that we initialize the lattice with) + "_data" 
        # so that each qubit inside each register will have a unique name
        # i.e. treg_0_data_0, treg_0_data_1, treg_0_data_2...
        qregisters["mz"] = QuantumRegister(params["num_syn"], name=name + "_mz")
        qregisters["mx"] = QuantumRegister(params["num_syn"], name=name + "_mx")
        qregisters["ancilla"] = QuantumRegister(1, name=name + "_ancilla")

        cregisters: Dict[str, ClassicalRegister] = {}  # classical

        self.stabilizer_shortnames = {"mx": _XXXX, "mz": _ZZZZ}

        super().__init__(circ, qregisters, cregisters, params, name)

    def _geometry(self):
        """
        Construct the lattice geometry for reuse across this class.
        Returns:
            geometry (Dict[str, List[List[int]]]): 
                key: syndrome/plaquette type
                value: List of lists of qubit indices comprising one plaquette.
        """
        geometry = {"mx": [], "mz": []}

        d = self.params["d"]
        per_row_x = (d - 1) // 2
        per_row_z = (d + 1) // 2
        # mx geometry
        for syn in range(self.params["num_syn"]):
            row = syn // per_row_x
            offset = syn % per_row_x
            start = (row - 1) * d
            row_parity = row % 2

            if row == 0:  # First row
                top_l, top_r = None, None
                bot_l = syn * 2
                bot_r = syn * 2 + 1
            elif row == d:  # Last row
                bot_l, bot_r = None, None
                top_l = syn * 2 + 1
                top_r = syn * 2 + 2
            else:
                top_l = start + (offset * 2) + row_parity
                top_r = start + (offset * 2) + row_parity + 1
                bot_l = start + d + (offset * 2) + row_parity
                bot_r = start + d + (offset * 2) + row_parity + 1

            geometry["mx"].append([syn, top_l, top_r, bot_l, bot_r])

        for syn in range(self.params["num_syn"]):
            row = syn // per_row_z
            offset = syn % per_row_z
            start = row * d
            row_parity = row % 2

            top_l = start + (offset * 2) - row_parity
            top_r = start + (offset * 2) - row_parity + 1
            bot_l = start + d + (offset * 2) - row_parity
            bot_r = start + d + (offset * 2) - row_parity + 1

            # Overwrite edge column syndromes
            if row_parity == 0 and offset == per_row_z - 1:  # Last column
                top_r, bot_r = None, None
            elif row_parity == 1 and offset == 0:  # First column
                top_l, bot_l = None, None

            geometry["mz"].append([syn, top_l, top_r, bot_l, bot_r])
        return geometry

    def gen_qubit_indices_and_stabilizers(self):
        """
        Generates lattice blueprint for rotated surface code lattice with our
        chosen layout and numbering.
        Returns:
            qubit_indices (List[List[Qubit]]):
                List of lists of Qubits that comprise each plaquette.
            stabilizers (List[_Stabilizer]):
                List of stabilizers for each plaquette.
        """
        self.geometry = self._geometry()

        qubit_indices = []
        stabilizers = []
        for stabilizer, idx_lists in self.geometry.items():
            stabilizer_cls = self.stabilizer_shortnames[stabilizer]
            for idx_list in idx_lists:
                syn = self.qregisters[stabilizer][idx_list[0]]
                plaquette = [
                    self.qregisters["data"][idx] if idx != None else None
                    for idx in idx_list[1:]
                ]
                plaquette = [syn,] + plaquette
                qubit_indices.append(plaquette)
                stabilizers.append(stabilizer_cls)
        return qubit_indices, stabilizers

    def entangle_x(self):
        """
        Build/entangle just the X Syndrome circuit.
        """
        num_x = len(self.qregisters["mx"])
        self.entangle(self.qubit_indices[:num_x], self.stabilizers[:num_x])

    def entangle_z(self):
        """
        Build/entangle just the Z Syndrome circuit.
        """
        num_x = len(self.qregisters["mx"])
        self.entangle(self.qubit_indices[num_x:], self.stabilizers[num_x:])

    def extract_final_stabilizer_and_logical_readout_x(
        self, final_readout_string: str, previous_syndrome_string: str
    ) -> Tuple[int, str]:
        """
        Extract final X syndrome measurements and logical X readout from 
        lattice readout along the X syndrome graph.
        Args:
            final_readout_string (str):
                readout string of length equal to the number of data qubits
                contains the readout values of each data qubit measured along
                axes specified by the X syndrome graph
            
            previous_syndrome_string (str):
                syndrome readout string form the previous round 
                of syndrome/stabilizer measurements
        Returns:
            logical_readout (int):
                logical readout value
            
            stabilizer_str (str):
                returns a string of the form 
                "X_{N}X_{N-1}...X_{0}Z_{N}Z_{N-1}...Z_{0}", 
                where Z_{N}Z_{N-1}...Z_{0} is copied from the previous Z syndrome 
                readout stored in previous_syndrome_string
        """
        readout_values = [int(q) for q in final_readout_string]
        readout_values = readout_values[::-1]  # [q_0,q_1,...,q_24]

        x_stabilizer = ""  # "X_{N}X_{N-1}..X_{0}"

        for idx_list in self.geometry["mx"]:
            stabilizer_val = (
                sum(
                    [readout_values[idx] if idx != None else 0 for idx in idx_list[1:]]
                )  # [mx, top_l, top_r, bot_l, bot_r]
                % 2
            )
            x_stabilizer = str(stabilizer_val) + x_stabilizer

        stabilizer_str = (
            x_stabilizer + previous_syndrome_string[self.params["num_syn"] :]
        )  # X_{N}X_{N-1}...X_{0}Z_{N}Z_{N-1}...Z_{0}, where Z_{N}Z_{N-1}...Z_{0} is copied from penultimate

        logical_readout = 0
        for idx in range(0, self.params["num_data"], self.params["d"]):
            logical_readout = (logical_readout + readout_values[idx]) % 2

        return logical_readout, stabilizer_str

    def extract_final_stabilizer_and_logical_readout_z(
        self, final_readout_string: str, previous_syndrome_string: str
    ) -> Tuple[int, str]:
        """
        Extract final Z syndrome measurements and logical Z readout from 
        lattice readout along the Z syndrome graph.
        Args:
            final_readout_string (str):
                readout string of length equal to the number of data qubits
                contains the readout values of each data qubit measured along
                axes specified by the Z syndrome graph
            
            previous_syndrome_string (str):
                syndrome readout string form the previous round 
                of syndrome/stabilizer measurements
        Returns:
            logical_readout (int):
                logical readout value
            
            stabilizer_str (str):
                returns a string of the form 
                "X_{N}X_{N-1}...X_{0}Z_{N}Z_{N-1}...Z_{0}", 
                where X_{N}X_{N-1}...X_{0} is copied from the previous X syndrome 
                readout stored in previous_syndrome_string
        """
        readout_values = [int(q) for q in final_readout_string]
        readout_values = readout_values[::-1]  # [q_0,q_1,...,q_24]

        z_stabilizer = ""  # "Z_{N}Z_{N-1}..Z_{0}"

        for idx_list in self.geometry["mz"]:
            stabilizer_val = (
                sum(
                    [readout_values[idx] if idx != None else 0 for idx in idx_list[1:]]
                )  # [mx, top_l, top_r, bot_l, bot_r]
                % 2
            )
            z_stabilizer = str(stabilizer_val) + z_stabilizer

        stabilizer_str = (
            previous_syndrome_string[: self.params["num_syn"]] + z_stabilizer
        )  # X_{N}X_{N-1}...X_{0}Z_{N}Z_{N-1}...Z_{0}, where X_{N}X_{N-1}...X_{0} is copied from penultimate

        logical_readout = 0
        for id in range(self.params["d"]):
            logical_readout = (logical_readout + readout_values[id]) % 2

        return logical_readout, stabilizer_str

    def extract_final_stabilizer_and_logical_readout(
        self,
        final_readout_string: str,
        previous_syndrome_string: str,
        readout_type: str,
    ):
        """
        Wrapper on extract_final_stabilizer_and_logical_readout_x/z.
        """
        if readout_type == "X":
            return self.extract_final_stabilizer_and_logical_readout_x(
                final_readout_string, previous_syndrome_string
            )
        elif readout_type == "Z":
            return self.extract_final_stabilizer_and_logical_readout_z(
                final_readout_string, previous_syndrome_string
            )

    def logical_x(self) -> None:
        """
        Logical X operator on the qubit.
        Uses the left-most column.
        """
        for i in range(0, self.params["num_data"], self.params["d"]):
            self.circ.x(self.qregisters["data"][i])
        self.circ.barrier()

    def logical_z(self) -> None:
        """
        Logical Z operator on the qubit.
        Uses the top-most row.
        """
        for i in range(self.params["d"]):
            self.circ.z(self.qregisters["data"][i])
        self.circ.barrier()

    def readout_x(self) -> None:
        """
        Convenience method to read-out the logical-X projection.
        Uses the left-most column.
        """
        self.params["num_readout"] += 1
        readout = ClassicalRegister(
            1, name=self.name + "_readout_" + str(self.params["num_readout"])
        )

        self.circ.add_register(readout)

        self.cregisters["readout"] = readout

        self.circ.reset(self.qregisters["ancilla"])
        self.circ.h(self.qregisters["ancilla"])
        for i in range(0, self.params["num_data"], self.params["d"]):
            self.circ.cx(self.qregisters["ancilla"], self.qregisters["data"][i])
        self.circ.h(self.qregisters["ancilla"])
        self.circ.measure(self.qregisters["ancilla"], self.cregisters["readout"])
        self.circ.barrier()

    def readout_z(self) -> None:
        """
        Convenience method to read-out the logical-Z projection.
        Uses the top-most row.
        """
        self.params["num_readout"] += 1
        readout = ClassicalRegister(
            1, name=self.name + "_readout_" + str(self.params["num_readout"])
        )

        self.circ.add_register(readout)

        self.cregisters["readout"] = readout

        self.circ.reset(self.qregisters["ancilla"])
        for i in range(self.params["d"]):
            self.circ.cx(self.qregisters["data"][i], self.qregisters["ancilla"])
        self.circ.measure(self.qregisters["ancilla"], self.cregisters["readout"])
        self.circ.barrier()

    def parse_readout(
        self, readout_string: str, readout_type: Optional[str] = None
    ) -> Tuple[int, Dict[str, List[TQubit]]]:
        """
        Helper method to turn a result string (e.g. 1 10100000 10010000) into an
        appropriate logical readout value and XOR-ed syndrome locations
        according to our grid coordinate convention.
        Args:
            readout_string (str):
                Readout of the form "1 10100000 10010000"
        Returns:
            logical_readout (int): 
                logical readout value
            syndromes (Dict[str, List[TQubit]]]):
                key: syndrome type
                value: (time, row, col) of parsed syndrome hits (changes between consecutive rounds)
        """
        chunks = readout_string.split(" ")

        if len(chunks[0]) > 1:  # this is true when all data qubits are readout
            assert readout_type is not None
            (
                logical_readout,
                final_stabilizer,
            ) = self.extract_final_stabilizer_and_logical_readout(
                chunks[0], chunks[1], readout_type
            )
            chunks = [final_stabilizer,] + chunks[1:]
        else:
            logical_readout = int(chunks[0])
            chunks = chunks[1:]

        int_syndromes = [int(x, base=2) for x in chunks[::-1]]
        xor_syndromes = [a ^ b for (a, b) in zip(int_syndromes, int_syndromes[1:])]

        mask_Z = "1" * self.params["num_syn"]
        mask_X = mask_Z + "0" * self.params["num_syn"]
        X_syndromes = [
            (x & int(mask_X, base=2)) >> self.params["num_syn"] for x in xor_syndromes
        ]
        Z_syndromes = [x & int(mask_Z, base=2) for x in xor_syndromes]

        X = []
        for T, syndrome in enumerate(X_syndromes):
            for loc in range(self.params["num_syn"]):
                if syndrome & 1 << loc:
                    X.append((float(T), -0.5 + loc, 0.5 + loc % 2))

        Z = []
        for T, syndrome in enumerate(Z_syndromes):
            for loc in range(self.params["num_syn"]):
                if syndrome & 1 << loc:
                    Z.append((float(T), 0.5 + loc // 2, 0.5 + loc % 2 * 2 - loc // 2))

        return (
            logical_readout,
            {"X": X, "Z": Z,},
        )


class XXZZQubit(TopologicalQubit[TQubit]):
    """
    A single logical surface code qubit.
    """

    def __init__(
        self,
        params: Dict[str, int],
        name: str = "tqubit",
        circ: Optional[QuantumCircuit] = None,
    ) -> None:
        """
        Initializes this Topological Qubit class.
        
        Args:
            params (Dict[str,int]): 
                Contains params such as d, where d is the number of physical "data" qubits lining a row or column of the lattice. 
                Only odd d is possible!
            name (str):
                Useful when combining multiple TopologicalQubits together. Prepended to all registers.
            circ (Optional[QuantumCircuit]):
                QuantumCircuit on top of which the topological qubit is built. 
                This is often shared amongst multiple TQubits.
                If none is provided, then a new QuantumCircuit is initialized and stored.
            
        """

        # == None is necessary, as `not QuantumCircuit()` is True
        circ = QuantumCircuit() if circ == None else circ

        super().__init__(circ, name)
        self.lattice = _XXZZLattice(params, name, circ)

    def stabilize(self) -> None:
        """
        Run a single round of stabilization (entangle and measure).
        """
        self.lattice.params["T"] += 1
        syndrome_readouts = ClassicalRegister(
            self.lattice.params["num_syn"] * 2,
            name=self.name + "_c{}".format(self.lattice.params["T"]),
        )
        self.lattice.cregisters[
            "syndrome{}".format(self.lattice.params["T"])
        ] = syndrome_readouts
        self.circ.add_register(syndrome_readouts)

        self.lattice.entangle()

        # measure syndromes
        self.circ.measure(
            self.lattice.qregisters["mz"],
            syndrome_readouts[0 : self.lattice.params["num_syn"]],
        )
        self.circ.measure(
            self.lattice.qregisters["mx"],
            syndrome_readouts[
                self.lattice.params["num_syn"] : self.lattice.params["num_syn"] * 2
            ],
        )
        self.circ.reset(self.lattice.qregisters["mz"])
        self.circ.reset(self.lattice.qregisters["mx"])
        self.circ.barrier()

    def identity(self) -> None:
        """
        Inserts an identity on the data and syndrome qubits.
        This allows us to create an isolated noise model by inserting errors only on identity gates.
        """
        [self.circ.id(register) for register in self.lattice.qregisters.values()]
        self.circ.barrier()

    def identity_data(self) -> None:
        """
        Inserts an identity on the data qubits only. 
        This allows us to create an isolated noise model by inserting errors only on identity gates.
        """
        self.circ.id(self.lattice.qregisters["data"])
        self.circ.barrier()

    def logical_x_plus_reset(self) -> None:
        """
        Initialize/reset to a logical |x+> state.
        """
        self.circ.reset(self.lattice.qregisters["data"])
        self.circ.h(self.lattice.qregisters["data"])
        self.circ.barrier()

    def logical_z_plus_reset(self) -> None:
        """
        Initialize/reset to a logical |z+> state.
        """
        self.circ.reset(self.lattice.qregisters["data"])
        self.circ.barrier()

    def logical_x(self) -> None:
        """
        Logical X operator on the topological qubit.
        """
        self.lattice.logical_x()

    def logical_z(self) -> None:
        """
        Logical Z operator on the topological qubit.
        """
        self.lattice.logical_z()

    def readout_x(self) -> None:
        """
        Convenience method to read-out the logical-X projection.
        """
        self.lattice.readout_x()

    def readout_z(self) -> None:
        """
        Convenience method to read-out the logical-Z projection.
        """
        self.lattice.readout_z()

    def lattice_readout_z(self) -> None:
        """
        Readout all data qubits that constitute the lattice.
        This readout can be used to extract a final round of Z stabilizer measurments,
        as well as a logical Z readout.
        """
        self.lattice.params["num_lattice_readout"] += 1

        readout = ClassicalRegister(
            self.lattice.params["num_data"],
            name=self.name
            + "_data_readout_"
            + str(self.lattice.params["num_lattice_readout"]),
        )

        self.circ.add_register(readout)

        self.lattice.cregisters["data_readout"] = readout

        self.circ.measure(
            self.lattice.qregisters["data"], self.lattice.cregisters["data_readout"]
        )
        self.circ.barrier()

    def lattice_readout_x(self) -> None:
        """
        Readout all data qubits that constitute the lattice.
        This readout can be used to extract a final round of X stabilizer measurments,
        as well as a logical X readout.
        """

        self.lattice.params["num_lattice_readout"] += 1
        readout = ClassicalRegister(
            self.lattice.params["num_data"],
            name=self.name
            + "_data_readout_"
            + str(self.lattice.params["num_lattice_readout"]),
        )

        self.circ.add_register(readout)
        self.lattice.cregisters["data_readout"] = readout

        # H|+> = |0>, H|-> = |1>
        self.circ.h(self.lattice.qregisters["data"])
        self.circ.measure(
            self.lattice.qregisters["data"], self.lattice.cregisters["data_readout"]
        )
        self.circ.barrier()

    def parse_readout(
        self, readout_string: str, readout_type: Optional[str] = None
    ) -> Tuple[int, Dict[str, List[TQubit]]]:
        return self.lattice.parse_readout(readout_string, readout_type)