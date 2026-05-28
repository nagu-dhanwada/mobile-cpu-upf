module execute_unit (
  input  mobile_cpu_pkg::decoded_instr_t decoded,
  input  logic [31:0]                    pc,
  input  logic [31:0]                    rs1_data,
  input  logic [31:0]                    rs2_data,
  input  logic [31:0]                    mem_rdata,
  output logic                           wb_en,
  output logic [3:0]                     wb_addr,
  output logic [31:0]                    wb_data,
  output logic                           mem_req,
  output logic                           mem_we,
  output logic [31:0]                    mem_addr,
  output logic [31:0]                    mem_wdata,
  output logic                           branch_taken,
  output logic [31:0]                    branch_target,
  output logic                           idle_hint,
  output logic                           retired
);
  logic signed [31:0] imm_ext;

  always_comb begin
    imm_ext = {{28{decoded.rs2_imm[3]}}, decoded.rs2_imm};

    wb_en         = 1'b0;
    wb_addr       = decoded.rd;
    wb_data       = 32'h0000_0000;
    mem_req       = 1'b0;
    mem_we        = 1'b0;
    mem_addr      = 32'h0000_0000;
    mem_wdata     = rs2_data;
    branch_taken  = 1'b0;
    branch_target = 32'h0000_0000;
    idle_hint     = 1'b0;
    retired       = 1'b1;

    unique case (decoded.opcode)
      mobile_cpu_pkg::OP_NOP: begin
      end

      mobile_cpu_pkg::OP_ADD: begin
        wb_en   = 1'b1;
        wb_data = rs1_data + rs2_data;
      end

      mobile_cpu_pkg::OP_SUB: begin
        wb_en   = 1'b1;
        wb_data = rs1_data - rs2_data;
      end

      mobile_cpu_pkg::OP_AND: begin
        wb_en   = 1'b1;
        wb_data = rs1_data & rs2_data;
      end

      mobile_cpu_pkg::OP_OR: begin
        wb_en   = 1'b1;
        wb_data = rs1_data | rs2_data;
      end

      mobile_cpu_pkg::OP_ADDI: begin
        wb_en   = 1'b1;
        wb_data = rs1_data + imm_ext;
      end

      mobile_cpu_pkg::OP_LD: begin
        wb_en    = 1'b1;
        wb_data  = mem_rdata;
        mem_req  = 1'b1;
        mem_addr = rs1_data + imm_ext;
      end

      mobile_cpu_pkg::OP_ST: begin
        mem_req   = 1'b1;
        mem_we    = 1'b1;
        mem_addr  = rs1_data + imm_ext;
        mem_wdata = rs2_data;
      end

      mobile_cpu_pkg::OP_BEQ: begin
        branch_taken  = (rs1_data == rs2_data);
        branch_target = pc + (imm_ext <<< 2);
      end

      mobile_cpu_pkg::OP_WFI: begin
        idle_hint = 1'b1;
      end

      default: begin
        retired = 1'b0;
      end
    endcase
  end
endmodule
