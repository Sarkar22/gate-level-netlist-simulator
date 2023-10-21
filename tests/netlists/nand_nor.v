module nand_nor(input a, b, output y_nand, y_nor);
  assign y_nand = ~(a & b);
  assign y_nor  = ~(a | b);
endmodule
