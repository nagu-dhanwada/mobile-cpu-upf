module mobile_cpu_top (
  input  logic       clk,
  input  logic       reset_n,
  input  logic       sleep_req,
  input  logic       deep_sleep_req,
  input  logic       wake_irq,
  input  logic       perf_boost,
  input  logic       scan_enable,
  output logic [1:0] dvfs_level,
  output logic       cpu_sleeping,
  output logic [2:0] power_mode,
  output logic [31:0] debug_pc
);
  logic core_clk;
  logic mem_clk;
  logic core_clk_en;
  logic mem_clk_en;
  logic cpu_power_gate_n;
  logic mem_power_gate_n;
  logic iso_core;
  logic iso_mem;
  logic ret_save;
  logic ret_restore;
  logic idle_hint;

  logic [31:0] instr_addr;
  logic [15:0] instr_rdata;
  logic [15:0] instr;
  mobile_cpu_pkg::decoded_instr_t decoded;

  logic [3:0]  rs2_addr;
  logic [31:0] rs1_data;
  logic [31:0] rs2_data;
  logic        wb_en;
  logic [3:0]  wb_addr;
  logic [31:0] wb_data;
  logic        mem_req;
  logic        mem_we;
  logic [31:0] mem_addr;
  logic [31:0] mem_wdata;
  logic [31:0] mem_rdata;
  logic [31:0] sram_rdata;
  logic [31:0] dataflow_rdata;
  logic        dataflow_sel;
  logic        dataflow_req;
  logic        dataflow_busy;
  logic        dataflow_op_valid;
  logic [31:0] dataflow_result;
  logic        branch_taken;
  logic [31:0] branch_target;
  logic        retired;

  clock_gate u_core_clk_gate (
    .clk         (clk),
    .reset_n     (reset_n),
    .enable      (core_clk_en),
    .scan_enable (scan_enable),
    .gated_clk   (core_clk)
  );

  clock_gate u_mem_clk_gate (
    .clk         (clk),
    .reset_n     (reset_n),
    .enable      (mem_clk_en),
    .scan_enable (scan_enable),
    .gated_clk   (mem_clk)
  );

  power_controller u_power_controller (
    .clk              (clk),
    .reset_n          (reset_n),
    .idle_hint        (idle_hint),
    .sleep_req        (sleep_req),
    .deep_sleep_req   (deep_sleep_req),
    .wake_irq         (wake_irq),
    .perf_boost       (perf_boost),
    .core_clk_en      (core_clk_en),
    .mem_clk_en       (mem_clk_en),
    .cpu_power_gate_n (cpu_power_gate_n),
    .mem_power_gate_n (mem_power_gate_n),
    .iso_core         (iso_core),
    .iso_mem          (iso_mem),
    .ret_save         (ret_save),
    .ret_restore      (ret_restore),
    .dvfs_level       (dvfs_level),
    .power_mode       (power_mode)
  );

  fetch_unit u_fetch (
    .clk           (core_clk),
    .reset_n       (reset_n),
    .enable        (cpu_power_gate_n),
    .stall         (1'b0),
    .branch_taken  (branch_taken),
    .branch_target (branch_target),
    .instr_rdata   (instr_rdata),
    .instr_addr    (instr_addr),
    .instr         (instr)
  );

  instr_rom u_icache (
    .addr  (instr_addr),
    .instr (instr_rdata)
  );

  decode_unit u_decode (
    .instr   (instr),
    .decoded (decoded)
  );

  assign rs2_addr = (decoded.opcode == mobile_cpu_pkg::OP_ST) ? decoded.rd : decoded.rs2_imm;

  regfile u_regfile (
    .clk              (core_clk),
    .reset_n          (reset_n),
    .retention_enable (!cpu_power_gate_n),
    .wr_en            (wb_en & cpu_power_gate_n & !iso_core),
    .wr_addr          (wb_addr),
    .wr_data          (wb_data),
    .rd_addr_a        (decoded.rs1),
    .rd_addr_b        (rs2_addr),
    .rd_data_a        (rs1_data),
    .rd_data_b        (rs2_data)
  );

  execute_unit u_execute (
    .decoded       (decoded),
    .pc            (instr_addr),
    .rs1_data      (rs1_data),
    .rs2_data      (rs2_data),
    .mem_rdata     (mem_rdata),
    .wb_en         (wb_en),
    .wb_addr       (wb_addr),
    .wb_data       (wb_data),
    .mem_req       (mem_req),
    .mem_we        (mem_we),
    .mem_addr      (mem_addr),
    .mem_wdata     (mem_wdata),
    .branch_taken  (branch_taken),
    .branch_target (branch_target),
    .idle_hint     (idle_hint),
    .retired       (retired)
  );

  assign dataflow_sel = (mem_addr[3:2] == 2'b01);
  assign dataflow_req = mem_req & dataflow_sel & !iso_mem;
  assign mem_rdata    = dataflow_sel ? dataflow_rdata : sram_rdata;

  data_sram u_dmem (
    .clk     (mem_clk),
    .reset_n (reset_n),
    .enable  (mem_power_gate_n),
    .req     (mem_req & !dataflow_sel & !iso_mem),
    .we      (mem_we),
    .addr    (mem_addr),
    .wdata   (mem_wdata),
    .rdata   (sram_rdata)
  );

  dataflow_unit u_dataflow (
    .clk      (mem_clk),
    .reset_n  (reset_n),
    .enable   (cpu_power_gate_n & mem_power_gate_n),
    .req      (dataflow_req),
    .we       (mem_we),
    .addr     (mem_addr[1:0]),
    .wdata    (mem_wdata),
    .rdata    (dataflow_rdata),
    .busy     (dataflow_busy),
    .op_valid (dataflow_op_valid),
    .result   (dataflow_result)
  );

  assign cpu_sleeping = !core_clk_en || !cpu_power_gate_n;
  assign debug_pc     = instr_addr;
endmodule
