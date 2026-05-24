module mobile_cpu_power_top (
  input  logic        clk,
  input  logic        reset_n,
  input  logic        sleep_req,
  input  logic        deep_sleep_req,
  input  logic        wake_irq,
  input  logic        perf_boost,
  input  logic        scan_enable,
  output logic [1:0]  dvfs_level,
  output logic        cpu_sleeping,
  output logic [2:0]  power_mode,
  output logic [31:0] debug_pc,
  output logic        core_clk_en,
  output logic        mem_clk_en,
  output logic        cpu_power_gate_n,
  output logic        mem_power_gate_n,
  output logic        iso_core,
  output logic        iso_mem,
  output logic        ret_save,
  output logic        ret_restore
);
  mobile_cpu_top u_dut (
    .clk            (clk),
    .reset_n        (reset_n),
    .sleep_req      (sleep_req),
    .deep_sleep_req (deep_sleep_req),
    .wake_irq       (wake_irq),
    .perf_boost     (perf_boost),
    .scan_enable    (scan_enable),
    .dvfs_level     (dvfs_level),
    .cpu_sleeping   (cpu_sleeping),
    .power_mode     (power_mode),
    .debug_pc       (debug_pc)
  );

  assign core_clk_en      = u_dut.core_clk_en;
  assign mem_clk_en       = u_dut.mem_clk_en;
  assign cpu_power_gate_n = u_dut.cpu_power_gate_n;
  assign mem_power_gate_n = u_dut.mem_power_gate_n;
  assign iso_core         = u_dut.iso_core;
  assign iso_mem          = u_dut.iso_mem;
  assign ret_save         = u_dut.ret_save;
  assign ret_restore      = u_dut.ret_restore;
endmodule

