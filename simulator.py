#!/usr/bin/env python3
"""
Gate-level combinational logic simulator for iVerilog VVP netlists.

Parses the VVP intermediate format produced by iverilog, builds a dependency
graph of logic gates, evaluates the circuit via topological propagation, and
reports output (and optionally all internal net) values.

Supported gate types: AND, OR, NOT, XOR, XNOR, NAND, NOR, BUF, BUFZ

Usage:
    python3 simulator.py <netlist.vvp> --inputs "a=1,b=0,c=1"
    python3 simulator.py <netlist.vvp> --inputs "a=1,b=0,c=1" --verbose
"""

import sys
import argparse
from collections import defaultdict, deque
from functools import reduce


# ---------------------------------------------------------------------------
# Gate evaluation
# ---------------------------------------------------------------------------

def _xor_reduce(vals):
    return reduce(lambda a, b: a ^ b, vals)

GATE_OPS = {
    'NOT':  lambda v: int(not v[0]),
    'BUF':  lambda v: v[0],
    'BUFZ': lambda v: v[0],
    'AND':  lambda v: int(all(v)),
    'OR':   lambda v: int(any(v)),
    'NAND': lambda v: int(not all(v)),
    'NOR':  lambda v: int(not any(v)),
    'XOR':  lambda v: _xor_reduce(v),
    'XNOR': lambda v: int(not _xor_reduce(v)),
}

# Constant tokens in VVP and their integer values
C4_VALUES = {'C4<0>': 0, 'C4<1>': 1, 'C4<z>': None}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_netlist(path):
    """
    Parse an iVerilog VVP netlist file.

    Returns:
        ports    – dict  {name: {'dir': 'INPUT'|'OUTPUT', 'driver': functor_addr}}
        functors – dict  {addr: {'type': str, 'inputs': list[str]}}
    """
    raw_ports = []           # [(index, direction, name)]
    net_name_to_driver = {}  # signal_name -> functor_addr that drives it
    functors = {}            # functor_addr -> {'type': str, 'inputs': [str]}

    with open(path) as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith('#') or line.startswith(':'):
                continue
            tokens = line.split()

            # .port_info  index  /DIR  width  "name"[;]
            if tokens[0] == '.port_info':
                direction = tokens[2].lstrip('/')
                name = tokens[4].strip('";')
                raw_ports.append((int(tokens[1]), direction, name))

            # addr  .functor  TYPE  width,  inp, inp, inp, inp;  [comment]
            elif len(tokens) > 3 and tokens[1] == '.functor':
                addr = tokens[0]
                gate_type = tokens[2]
                # Everything before the first ';' holds addr, .functor, type, width, inputs
                parts = line.split(';')[0].split()
                # parts[3] = "width," — skip; parts[4:] = input tokens
                inputs = [p.strip(',') for p in parts[4:]]
                functors[addr] = {'type': gate_type, 'inputs': inputs}

            # addr  .net  "name",  0  0,  driver_addr;  N drivers
            elif len(tokens) > 5 and tokens[1] == '.net':
                name = tokens[2].strip('*",')
                driver = line.split(';')[0].split()[-1]
                net_name_to_driver[name] = driver

    # Map port names to the functor addresses that drive them
    ports = {}
    for _, direction, name in sorted(raw_ports):
        if name in net_name_to_driver:
            ports[name] = {'dir': direction, 'driver': net_name_to_driver[name]}
        else:
            raise ValueError(
                f"Port '{name}' declared in .port_info but not found in .net table."
            )

    return ports, functors


# ---------------------------------------------------------------------------
# Topological sort (Kahn's algorithm)
# ---------------------------------------------------------------------------

def build_topo_order(functors):
    """
    Return functor addresses in valid evaluation order.
    Raises ValueError if a combinational cycle is detected.
    """
    dependents = defaultdict(list)  # addr -> [addrs that consume this addr's output]
    in_degree = {addr: 0 for addr in functors}

    for addr, info in functors.items():
        for inp in info['inputs']:
            if inp in functors:
                dependents[inp].append(addr)
                in_degree[addr] += 1

    queue = deque(addr for addr in functors if in_degree[addr] == 0)
    order = []
    while queue:
        addr = queue.popleft()
        order.append(addr)
        for consumer in dependents[addr]:
            in_degree[consumer] -= 1
            if in_degree[consumer] == 0:
                queue.append(consumer)

    if len(order) != len(functors):
        raise ValueError(
            "Combinational cycle detected in netlist — cannot simulate."
        )
    return order


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def _resolve(inp, values):
    """Resolve a functor input token to a 0/1 integer."""
    if inp in C4_VALUES:
        val = C4_VALUES[inp]
        return 0 if val is None else val   # C4<z> (undriven) → 0
    if inp in values:
        return values[inp]
    raise KeyError(f"Cannot resolve input '{inp}': not yet evaluated.")


def simulate(ports, functors, input_values):
    """
    Evaluate the circuit for a given set of input values.

    Args:
        ports:        parsed port dict from parse_netlist()
        functors:     parsed functor dict from parse_netlist()
        input_values: dict {port_name: 0|1}

    Returns:
        values: dict {functor_addr: 0|1} for every node in the circuit
    """
    input_ports = {n for n, p in ports.items() if p['dir'] == 'INPUT'}
    missing = input_ports - set(input_values)
    if missing:
        raise ValueError(f"Missing input values for port(s): {sorted(missing)}")

    topo_order = build_topo_order(functors)
    values = {}

    # Seed primary inputs — set their BUFZ functor values directly
    for name in input_ports:
        driver = ports[name]['driver']
        values[driver] = int(input_values[name])

    # Propagate through the circuit in topological order
    for addr in topo_order:
        if addr in values:
            continue   # already set (primary-input BUFZ)
        info = functors[addr]
        gate_type = info['type']
        op = GATE_OPS.get(gate_type)
        if op is None:
            raise ValueError(
                f"Unsupported gate type '{gate_type}'. "
                f"Supported: {sorted(GATE_OPS)}"
            )
        resolved = [_resolve(inp, values) for inp in info['inputs']]
        values[addr] = op(resolved)

    return values


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def parse_input_string(raw):
    """Parse 'a=1,b=0,c=1' into {'a': 1, 'b': 0, 'c': 1}."""
    result = {}
    for pair in raw.split(','):
        pair = pair.strip()
        if '=' not in pair:
            raise ValueError(
                f"Bad input specification '{pair}'. Use name=value (e.g. a=1,b=0)."
            )
        name, val = pair.split('=', 1)
        name, val = name.strip(), val.strip()
        if val not in ('0', '1'):
            raise ValueError(f"Input '{name}': value must be 0 or 1, got '{val}'.")
        result[name] = int(val)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Combinational gate-level simulator for iVerilog VVP netlists.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 simulator.py EDA_netlist.txt --inputs 'a=1,b=1,c=0'\n"
            "  python3 simulator.py full_adder.vvp  --inputs 'a=1,b=1,cin=1' --verbose"
        ),
    )
    parser.add_argument("netlist", help="Path to iVerilog VVP netlist file")
    parser.add_argument(
        "--inputs", required=True,
        help="Comma-separated input assignments, e.g. 'a=1,b=0,c=1'"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Also print values at all internal nets"
    )
    args = parser.parse_args()

    try:
        ports, functors = parse_netlist(args.netlist)
        input_values = parse_input_string(args.inputs)
        values = simulate(ports, functors, input_values)
    except (FileNotFoundError, ValueError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    input_ports  = {n: p for n, p in ports.items() if p['dir'] == 'INPUT'}
    output_ports = {n: p for n, p in ports.items() if p['dir'] == 'OUTPUT'}

    print("Inputs:")
    for name in sorted(input_ports):
        print(f"  {name} = {input_values[name]}")

    print("\nOutputs:")
    for name in sorted(output_ports):
        driver = output_ports[name]['driver']
        print(f"  {name} = {values.get(driver, '?')}")

    if args.verbose:
        addr_to_name = {p['driver']: name for name, p in ports.items()}
        print("\nAll nets:")
        for addr, val in values.items():
            label = addr_to_name.get(addr, addr)
            print(f"  {label:<36} {val}")


if __name__ == "__main__":
    main()
