# Gate-Level Combinational Logic Simulator

A Python simulator for gate-level combinational circuits. Takes an **iVerilog VVP netlist** as input, builds a dependency graph, evaluates logic via **topological propagation**, and reports output values.

---

## How It Works

1. **Parse** — reads `.port_info`, `.functor`, and `.net` entries from the iVerilog VVP intermediate format
2. **Graph** — builds a directed acyclic graph where each node is a logic gate
3. **Topo sort** — orders gates using Kahn's algorithm so every gate's inputs are ready before it is evaluated
4. **Propagate** — evaluates gates in order, starting from primary inputs

Supported gate types: `AND`, `OR`, `NOT`, `XOR`, `XNOR`, `NAND`, `NOR`, `BUF`, `BUFZ`

---

## Generating a Netlist

Compile any combinational Verilog module with [iVerilog](https://steveicarus.github.io/iverilog/):

```bash
iverilog -o my_circuit.vvp my_circuit.v
```

---

## Usage

```bash
python3 simulator.py <netlist.vvp> --inputs "port=val,..."
python3 simulator.py <netlist.vvp> --inputs "port=val,..." --verbose
```

### Examples

```bash
# 3-input combinational circuit
python3 simulator.py EDA_netlist.txt --inputs "a=1,b=1,c=0"

# 1-bit full adder — shows both sum and cout
python3 simulator.py tests/netlists/full_adder.vvp --inputs "a=1,b=1,cin=1"

# Show all internal net values as well
python3 simulator.py tests/netlists/full_adder.vvp --inputs "a=1,b=0,cin=1" --verbose
```

### Sample output

```
Inputs:
  a = 1
  b = 1
  cin = 1

Outputs:
  cout = 1
  sum  = 1
```

---

## Running Tests

```bash
python3 -m pytest tests/test_simulator.py -v
```

Tests verify full truth tables for four circuits:

| Netlist | Function |
|---------|----------|
| `EDA_netlist.txt` | `out = a \| (~b & c)` |
| `xor2.vvp` | `out = a ^ b` |
| `full_adder.vvp` | `sum = a^b^cin`, `cout = majority(a,b,cin)` |
| `nand_nor.vvp` | `y_nand = ~(a&b)`, `y_nor = ~(a\|b)` |

---

## Limitations

- **Combinational circuits only** — sequential elements (flip-flops, latches) are not supported
- Single-bit signals only (no bus/vector support)
- Targets the iVerilog VVP format; other simulator formats are not supported

---

## Dependencies

- Python 3.7+
- [pytest](https://pytest.org/) (tests only)

---

## License

MIT — see [LICENSE](LICENSE).
