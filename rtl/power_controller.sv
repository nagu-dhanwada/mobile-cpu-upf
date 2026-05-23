module power_controller (
  input  logic       clk,
  input  logic       reset_n,
  input  logic       idle_hint,
  input  logic       sleep_req,
  input  logic       deep_sleep_req,
  input  logic       wake_irq,
  input  logic       perf_boost,
  output logic       core_clk_en,
  output logic       mem_clk_en,
  output logic       cpu_power_gate_n,
  output logic       mem_power_gate_n,
  output logic       iso_core,
  output logic       iso_mem,
  output logic       ret_save,
  output logic       ret_restore,
  output logic [1:0] dvfs_level,
  output logic [2:0] power_mode
);
  typedef enum logic [2:0] {
    MODE_RUN         = 3'd0,
    MODE_IDLE        = 3'd1,
    MODE_LIGHT_SLEEP = 3'd2,
    MODE_DEEP_SLEEP  = 3'd3,
    MODE_WAKE        = 3'd4
  } mode_e;

  mode_e mode_q;
  mode_e mode_d;

  always_comb begin
    mode_d = mode_q;

    unique case (mode_q)
      MODE_RUN: begin
        if (deep_sleep_req) begin
          mode_d = MODE_DEEP_SLEEP;
        end else if (sleep_req) begin
          mode_d = MODE_LIGHT_SLEEP;
        end else if (idle_hint) begin
          mode_d = MODE_IDLE;
        end
      end

      MODE_IDLE: begin
        if (deep_sleep_req) begin
          mode_d = MODE_DEEP_SLEEP;
        end else if (sleep_req) begin
          mode_d = MODE_LIGHT_SLEEP;
        end else if (!idle_hint || wake_irq || perf_boost) begin
          mode_d = MODE_RUN;
        end
      end

      MODE_LIGHT_SLEEP,
      MODE_DEEP_SLEEP: begin
        if (wake_irq) begin
          mode_d = MODE_WAKE;
        end
      end

      MODE_WAKE: begin
        mode_d = MODE_RUN;
      end

      default: begin
        mode_d = MODE_RUN;
      end
    endcase
  end

  always_ff @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
      mode_q <= MODE_RUN;
    end else begin
      mode_q <= mode_d;
    end
  end

  always_comb begin
    core_clk_en      = 1'b1;
    mem_clk_en       = 1'b1;
    cpu_power_gate_n = 1'b1;
    mem_power_gate_n = 1'b1;
    iso_core         = 1'b0;
    iso_mem          = 1'b0;
    ret_save         = 1'b0;
    ret_restore      = 1'b0;
    dvfs_level       = 2'b01;

    unique case (mode_q)
      MODE_RUN: begin
        dvfs_level = perf_boost ? 2'b10 : 2'b01;
      end

      MODE_IDLE: begin
        core_clk_en = perf_boost;
        mem_clk_en  = 1'b0;
        dvfs_level  = 2'b00;
      end

      MODE_LIGHT_SLEEP: begin
        core_clk_en = 1'b0;
        mem_clk_en  = 1'b0;
        ret_save    = 1'b1;
        dvfs_level  = 2'b00;
      end

      MODE_DEEP_SLEEP: begin
        core_clk_en      = 1'b0;
        mem_clk_en       = 1'b0;
        cpu_power_gate_n = 1'b0;
        mem_power_gate_n = 1'b0;
        iso_core         = 1'b1;
        iso_mem          = 1'b1;
        ret_save         = 1'b1;
        dvfs_level       = 2'b00;
      end

      MODE_WAKE: begin
        core_clk_en = 1'b1;
        mem_clk_en  = 1'b1;
        ret_restore = 1'b1;
        dvfs_level  = 2'b01;
      end

      default: begin
      end
    endcase
  end

  assign power_mode = mode_q;
endmodule

