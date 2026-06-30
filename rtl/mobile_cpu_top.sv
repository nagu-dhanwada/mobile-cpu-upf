module mobile_cpu_top #(
  parameter int SRAM_RESPONSE_DELAY = 1,
  parameter int DATAFLOW_RESPONSE_DELAY = 1
) (
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
  logic        execute_wb_en;
  logic [3:0]  execute_wb_addr;
  logic [31:0] execute_wb_data;
  logic        regfile_wb_en;
  logic [3:0]  regfile_wb_addr;
  logic [31:0] regfile_wb_data;
  logic        mem_req;
  logic        mem_we;
  logic [31:0] mem_addr;
  logic [31:0] mem_wdata;
  logic [31:0] mem_rdata;
  logic        lsu_stall;
  logic        lsu_retired;
  logic        lsu_load_wb_en;
  logic [3:0]  lsu_load_wb_addr;
  logic [31:0] lsu_load_wb_data;
  logic        lsu_error_seen;
  logic        bus_req_valid;
  logic        bus_req_ready;
  logic        bus_req_we;
  logic [31:0] bus_req_addr;
  logic [31:0] bus_req_wdata;
  logic [3:0]  bus_req_byte_en;
  logic        bus_resp_valid;
  logic [31:0] bus_resp_rdata;
  logic        bus_resp_error;
  logic        sram_req;
  logic        sram_we;
  logic [31:0] sram_addr;
  logic [31:0] sram_wdata;
  logic [31:0] sram_rdata;
  logic        dataflow_req_valid;
  logic        dataflow_req_ready;
  logic        dataflow_req_we;
  logic [1:0]  dataflow_req_addr;
  logic [31:0] dataflow_req_wdata;
  logic        dataflow_resp_valid;
  logic [31:0] dataflow_resp_rdata;
  logic        dataflow_resp_error;
  logic        dataflow_busy;
  logic        dataflow_op_valid;
  logic [31:0] dataflow_result;
  logic        branch_taken;
  logic [31:0] branch_target;
  logic        execute_retired;
  logic        retired;
  logic        fetch_valid;
  logic        decode_valid;
  logic        execute_valid;
  logic        stall_fetch;
  logic        stall_decode;
  logic        stall_execute;
  logic        fetch_ce;
  logic        decode_ce;
  logic        execute_ce;
  logic        dataflow_ctrl_ce;
  logic        dataflow_mac_ce;

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
    .stall         (lsu_stall),
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
    .wr_en            (regfile_wb_en & cpu_power_gate_n & !iso_core),
    .wr_addr          (regfile_wb_addr),
    .wr_data          (regfile_wb_data),
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
    .wb_en         (execute_wb_en),
    .wb_addr       (execute_wb_addr),
    .wb_data       (execute_wb_data),
    .mem_req       (mem_req),
    .mem_we        (mem_we),
    .mem_addr      (mem_addr),
    .mem_wdata     (mem_wdata),
    .branch_taken  (branch_taken),
    .branch_target (branch_target),
    .idle_hint     (idle_hint),
    .retired       (execute_retired)
  );

  assign mem_rdata = lsu_load_wb_data;
  assign fetch_valid   = cpu_power_gate_n & !iso_core;
  assign decode_valid  = cpu_power_gate_n & !iso_core;
  assign execute_valid = cpu_power_gate_n & !iso_core;
  assign stall_fetch   = lsu_stall;
  assign stall_decode  = lsu_stall;
  assign stall_execute = lsu_stall;
  assign fetch_ce      = fetch_valid & !stall_fetch;
  assign decode_ce     = decode_valid & !stall_decode;
  assign execute_ce    = execute_valid & !stall_execute;

  load_store_unit u_lsu (
    .clk                (core_clk),
    .reset_n            (reset_n),
    .enable             (cpu_power_gate_n & !iso_core),
    .execute_mem_req    (mem_req),
    .execute_mem_we     (mem_we),
    .execute_wb_addr    (execute_wb_addr),
    .execute_mem_addr   (mem_addr),
    .execute_mem_wdata  (mem_wdata),
    .stall              (lsu_stall),
    .retired            (lsu_retired),
    .load_wb_en         (lsu_load_wb_en),
    .load_wb_addr       (lsu_load_wb_addr),
    .load_wb_data       (lsu_load_wb_data),
    .error_seen         (lsu_error_seen),
    .bus_req_valid      (bus_req_valid),
    .bus_req_ready      (bus_req_ready),
    .bus_req_we         (bus_req_we),
    .bus_req_addr       (bus_req_addr),
    .bus_req_wdata      (bus_req_wdata),
    .bus_req_byte_en    (bus_req_byte_en),
    .bus_resp_valid     (bus_resp_valid),
    .bus_resp_rdata     (bus_resp_rdata),
    .bus_resp_error     (bus_resp_error)
  );

  assign regfile_wb_en   = lsu_load_wb_en ? 1'b1 : (execute_wb_en & !mem_req & !lsu_stall);
  assign regfile_wb_addr = lsu_load_wb_en ? lsu_load_wb_addr : execute_wb_addr;
  assign regfile_wb_data = lsu_load_wb_en ? lsu_load_wb_data : execute_wb_data;
  assign retired         = mem_req ? lsu_retired : (execute_retired & !lsu_stall);

  data_bus_interconnect #(
    .SRAM_RESPONSE_DELAY (SRAM_RESPONSE_DELAY)
  ) u_dbus (
    .clk                 (mem_clk),
    .reset_n             (reset_n),
    .enable              (mem_power_gate_n & !iso_mem),
    .req_valid           (bus_req_valid),
    .req_ready           (bus_req_ready),
    .req_we              (bus_req_we),
    .req_addr            (bus_req_addr),
    .req_wdata           (bus_req_wdata),
    .req_byte_en         (bus_req_byte_en),
    .resp_valid          (bus_resp_valid),
    .resp_rdata          (bus_resp_rdata),
    .resp_error          (bus_resp_error),
    .sram_req            (sram_req),
    .sram_we             (sram_we),
    .sram_addr           (sram_addr),
    .sram_wdata          (sram_wdata),
    .sram_rdata          (sram_rdata),
    .dataflow_req_valid  (dataflow_req_valid),
    .dataflow_req_ready  (dataflow_req_ready),
    .dataflow_req_we     (dataflow_req_we),
    .dataflow_req_addr   (dataflow_req_addr),
    .dataflow_req_wdata  (dataflow_req_wdata),
    .dataflow_resp_valid (dataflow_resp_valid),
    .dataflow_resp_rdata (dataflow_resp_rdata),
    .dataflow_resp_error (dataflow_resp_error)
  );

  data_sram u_dmem (
    .clk     (mem_clk),
    .reset_n (reset_n),
    .enable  (mem_power_gate_n),
    .req     (sram_req),
    .we      (sram_we),
    .addr    (sram_addr),
    .wdata   (sram_wdata),
    .rdata   (sram_rdata)
  );

  dataflow_unit #(
    .RESPONSE_DELAY (DATAFLOW_RESPONSE_DELAY)
  ) u_dataflow (
    .clk        (mem_clk),
    .reset_n    (reset_n),
    .enable     (cpu_power_gate_n & mem_power_gate_n & !iso_mem),
    .req_valid  (dataflow_req_valid),
    .req_ready  (dataflow_req_ready),
    .req_we     (dataflow_req_we),
    .req_addr   (dataflow_req_addr),
    .req_wdata  (dataflow_req_wdata),
    .resp_valid (dataflow_resp_valid),
    .resp_rdata (dataflow_resp_rdata),
    .resp_error (dataflow_resp_error),
    .busy       (dataflow_busy),
    .op_valid   (dataflow_op_valid),
    .result     (dataflow_result)
  );

  assign dataflow_ctrl_ce = dataflow_req_valid | dataflow_resp_valid | dataflow_busy;
  assign dataflow_mac_ce  = dataflow_op_valid;

  assign cpu_sleeping = !core_clk_en || !cpu_power_gate_n;
  assign debug_pc     = instr_addr;
endmodule
