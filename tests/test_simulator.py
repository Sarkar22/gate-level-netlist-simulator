"""
Tests for simulator.py

Circuits under test:
  EDA_netlist.txt      out  = a | (~b & c)           3 inputs, 1 output
  xor2.vvp             out  = a ^ b                  2 inputs, 1 output
  full_adder.vvp       sum  = a ^ b ^ cin             3 inputs, 2 outputs
                       cout = majority(a, b, cin)
  nand_nor.vvp         y_nand = ~(a & b)              2 inputs, 2 outputs
                       y_nor  = ~(a | b)
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from simulator import parse_netlist, simulate, parse_input_string, build_topo_order

NETS_DIR = os.path.join(os.path.dirname(__file__), "netlists")

def netlist(name):
    return os.path.join(NETS_DIR, name)

def run(path, **kwargs):
    """Parse netlist and simulate with given input values. Returns output values."""
    ports, functors = parse_netlist(path)
    values = simulate(ports, functors, kwargs)
    return {name: values[p['driver']]
            for name, p in ports.items() if p['dir'] == 'OUTPUT'}


# ---------------------------------------------------------------------------
# parse_netlist
# ---------------------------------------------------------------------------

class TestParseNetlist:
    def test_eda_ports(self):
        ports, _ = parse_netlist("EDA_netlist.txt")
        assert set(ports) == {"a", "b", "c", "out"}
        assert ports["a"]["dir"]   == "INPUT"
        assert ports["out"]["dir"] == "OUTPUT"

    def test_xor2_ports(self):
        ports, _ = parse_netlist(netlist("xor2.vvp"))
        assert {n for n, p in ports.items() if p["dir"] == "INPUT"}  == {"a", "b"}
        assert {n for n, p in ports.items() if p["dir"] == "OUTPUT"} == {"out"}

    def test_full_adder_ports(self):
        ports, _ = parse_netlist(netlist("full_adder.vvp"))
        assert {n for n, p in ports.items() if p["dir"] == "INPUT"}  == {"a", "b", "cin"}
        assert {n for n, p in ports.items() if p["dir"] == "OUTPUT"} == {"sum", "cout"}

    def test_functors_nonempty(self):
        _, functors = parse_netlist("EDA_netlist.txt")
        assert len(functors) > 0

    def test_all_functor_inputs_are_strings(self):
        _, functors = parse_netlist(netlist("full_adder.vvp"))
        for addr, info in functors.items():
            assert isinstance(info["inputs"], list)
            for inp in info["inputs"]:
                assert isinstance(inp, str)


# ---------------------------------------------------------------------------
# build_topo_order
# ---------------------------------------------------------------------------

class TestTopoOrder:
    def test_length_matches_functors(self):
        _, functors = parse_netlist(netlist("full_adder.vvp"))
        order = build_topo_order(functors)
        assert len(order) == len(functors)

    def test_no_forward_references(self):
        """Every input dependency of a functor must appear before it in the order."""
        _, functors = parse_netlist(netlist("full_adder.vvp"))
        order = build_topo_order(functors)
        position = {addr: i for i, addr in enumerate(order)}
        for addr, info in functors.items():
            for inp in info["inputs"]:
                if inp in functors:
                    assert position[inp] < position[addr]


# ---------------------------------------------------------------------------
# EDA_netlist.txt  —  out = a | (~b & c)
# ---------------------------------------------------------------------------

class TestCombinationalEDA:
    # Full truth table
    @pytest.mark.parametrize("a,b,c,expected", [
        (0, 0, 0, 0),
        (0, 0, 1, 1),
        (0, 1, 0, 0),
        (0, 1, 1, 0),
        (1, 0, 0, 1),
        (1, 0, 1, 1),
        (1, 1, 0, 1),
        (1, 1, 1, 1),
    ])
    def test_truth_table(self, a, b, c, expected):
        assert run("EDA_netlist.txt", a=a, b=b, c=c)["out"] == expected


# ---------------------------------------------------------------------------
# xor2.vvp  —  out = a ^ b
# ---------------------------------------------------------------------------

class TestXor2:
    @pytest.mark.parametrize("a,b,expected", [
        (0, 0, 0),
        (0, 1, 1),
        (1, 0, 1),
        (1, 1, 0),
    ])
    def test_truth_table(self, a, b, expected):
        assert run(netlist("xor2.vvp"), a=a, b=b)["out"] == expected


# ---------------------------------------------------------------------------
# full_adder.vvp  —  sum = a^b^cin,  cout = majority(a,b,cin)
# ---------------------------------------------------------------------------

class TestFullAdder:
    @pytest.mark.parametrize("a,b,cin,exp_sum,exp_cout", [
        (0, 0, 0, 0, 0),
        (0, 0, 1, 1, 0),
        (0, 1, 0, 1, 0),
        (0, 1, 1, 0, 1),
        (1, 0, 0, 1, 0),
        (1, 0, 1, 0, 1),
        (1, 1, 0, 0, 1),
        (1, 1, 1, 1, 1),
    ])
    def test_truth_table(self, a, b, cin, exp_sum, exp_cout):
        out = run(netlist("full_adder.vvp"), a=a, b=b, cin=cin)
        assert out["sum"]  == exp_sum
        assert out["cout"] == exp_cout


# ---------------------------------------------------------------------------
# nand_nor.vvp  —  y_nand = ~(a&b),  y_nor = ~(a|b)
# ---------------------------------------------------------------------------

class TestNandNor:
    @pytest.mark.parametrize("a,b,exp_nand,exp_nor", [
        (0, 0, 1, 1),
        (0, 1, 1, 0),
        (1, 0, 1, 0),
        (1, 1, 0, 0),
    ])
    def test_truth_table(self, a, b, exp_nand, exp_nor):
        out = run(netlist("nand_nor.vvp"), a=a, b=b)
        assert out["y_nand"] == exp_nand
        assert out["y_nor"]  == exp_nor


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrors:
    def test_missing_input(self):
        ports, functors = parse_netlist(netlist("xor2.vvp"))
        with pytest.raises(ValueError, match="Missing input"):
            simulate(ports, functors, {"a": 1})   # b missing

    def test_bad_input_format(self):
        with pytest.raises(ValueError, match="Bad input"):
            parse_input_string("a1,b=0")

    def test_bad_input_value(self):
        with pytest.raises(ValueError, match="must be 0 or 1"):
            parse_input_string("a=2,b=0")

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            parse_netlist("nonexistent.vvp")


# ---------------------------------------------------------------------------
# parse_input_string
# ---------------------------------------------------------------------------

class TestParseInputString:
    def test_basic(self):
        assert parse_input_string("a=1,b=0,c=1") == {"a": 1, "b": 0, "c": 1}

    def test_spaces_ok(self):
        assert parse_input_string("a = 1, b = 0") == {"a": 1, "b": 0}

    def test_single(self):
        assert parse_input_string("x=0") == {"x": 0}
