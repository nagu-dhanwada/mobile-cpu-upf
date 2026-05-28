#include "Vmobile_cpu_top.h"
#include "verilated.h"
#include "verilated_vcd_c.h"

#include <cstdint>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace {

struct Options {
  std::string summary_path = "reports/gls/gate_summary.md";
  std::string wave_path = "waves/mobile_cpu_gate.vcd";
  std::string workload_name = "builtin";
  bool no_wave = false;
};

bool starts_with(const std::string& text, const std::string& prefix) {
  return text.rfind(prefix, 0) == 0;
}

Options parse_options(int argc, char** argv) {
  Options opts;
  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    if (starts_with(arg, "+gate-summary=")) {
      opts.summary_path = arg.substr(std::string("+gate-summary=").size());
    } else if (starts_with(arg, "+gate-wave=")) {
      opts.wave_path = arg.substr(std::string("+gate-wave=").size());
    } else if (starts_with(arg, "+workload=")) {
      opts.workload_name = arg.substr(std::string("+workload=").size());
    } else if (arg == "+gate-no-wave=1") {
      opts.no_wave = true;
    }
  }
  return opts;
}

std::string mode_name(uint8_t mode) {
  switch (mode) {
    case 0:
      return "RUN";
    case 1:
      return "IDLE";
    case 2:
      return "LIGHT_SLEEP";
    case 3:
      return "DEEP_SLEEP";
    case 4:
      return "WAKE";
    default:
      return "UNKNOWN";
  }
}

struct Check {
  uint64_t cycle;
  std::string name;
  std::string detail;
  bool pass;
};

class GateLevelSim {
 public:
  explicit GateLevelSim(const Options& options) : opts_(options) {
    dut_.clk = 0;
    dut_.reset_n = 0;
    dut_.sleep_req = 0;
    dut_.deep_sleep_req = 0;
    dut_.wake_irq = 0;
    dut_.perf_boost = 0;
    dut_.scan_enable = 0;

    if (!opts_.no_wave) {
      Verilated::traceEverOn(true);
      trace_ = new VerilatedVcdC;
      dut_.trace(trace_, 99);
      trace_->open(opts_.wave_path.c_str());
    }
  }

  ~GateLevelSim() {
    if (trace_) {
      trace_->close();
      delete trace_;
      trace_ = nullptr;
    }
  }

  int run() {
    apply_reset();
    check_run_progress();
    check_idle_and_dvfs();
    check_sleep_wake();
    write_summary();
    if (failures_ == 0) {
      std::cout << "GATE-SIM PASS: wrote " << opts_.summary_path << "\n";
      return 0;
    }
    std::cout << "GATE-SIM FAIL: " << failures_ << " failure(s); wrote " << opts_.summary_path << "\n";
    return 1;
  }

 private:
  void eval_and_dump() {
    dut_.eval();
    if (trace_) {
      trace_->dump(time_);
    }
    ++time_;
  }

  void tick() {
    dut_.clk = 0;
    eval_and_dump();
    dut_.clk = 1;
    eval_and_dump();
    dut_.clk = 0;
    eval_and_dump();
    ++cycle_;
  }

  void apply_reset() {
    for (int i = 0; i < 4; ++i) {
      tick();
    }
    dut_.reset_n = 1;
    for (int i = 0; i < 2; ++i) {
      tick();
    }
    require(dut_.power_mode == 0, "reset_to_run", "Gate netlist should leave reset in RUN");
  }

  void check_run_progress() {
    const uint32_t start_pc = dut_.debug_pc;
    bool pc_advanced = false;
    for (int i = 0; i < 12; ++i) {
      tick();
      pc_advanced = pc_advanced || (dut_.debug_pc != start_pc);
    }
    require(pc_advanced, "pc_advances", "PC should advance while executing the synthesized ROM workload");
  }

  void check_idle_and_dvfs() {
    bool saw_idle = false;
    bool low_dvfs = false;
    for (int i = 0; i < 96; ++i) {
      tick();
      saw_idle = saw_idle || (dut_.power_mode == 1);
      low_dvfs = low_dvfs || (dut_.dvfs_level == 0);
    }
    require(saw_idle, "wfi_enters_idle", "Synthesized workload should eventually execute WFI");
    require(low_dvfs, "idle_low_dvfs", "IDLE should request low-power DVFS");
  }

  void check_sleep_wake() {
    dut_.sleep_req = 1;
    tick();
    require(dut_.power_mode == 2, "light_sleep_entered", "sleep_req should enter LIGHT_SLEEP");
    dut_.sleep_req = 0;
    dut_.wake_irq = 1;
    tick();
    require(dut_.power_mode == 4, "wake_entered", "wake_irq should enter WAKE");
    dut_.wake_irq = 0;
    tick();
    require(dut_.power_mode == 0, "wake_returns_run", "WAKE should return to RUN");

    dut_.deep_sleep_req = 1;
    tick();
    require(dut_.power_mode == 3, "deep_sleep_entered", "deep_sleep_req should enter DEEP_SLEEP");
    dut_.deep_sleep_req = 0;
    dut_.wake_irq = 1;
    tick();
    require(dut_.power_mode == 4, "deep_sleep_wake_entered", "wake_irq should wake DEEP_SLEEP");
    dut_.wake_irq = 0;
    tick();
    require(dut_.power_mode == 0, "deep_sleep_returns_run", "DEEP_SLEEP wake should return to RUN");
  }

  void require(bool condition, const std::string& name, const std::string& detail) {
    checks_.push_back(Check{cycle_, name, detail, condition});
    if (!condition) {
      ++failures_;
    }
  }

  void write_summary() const {
    std::ofstream out(opts_.summary_path);
    out << "# Gate-Level Simulation Summary\n\n";
    out << "- Workload: `" << opts_.workload_name << "`\n";
    out << "- Result: " << (failures_ == 0 ? "PASS" : "FAIL") << "\n";
    out << "- Failing checks: " << failures_ << "\n";
    out << "- Waveform: `" << (opts_.no_wave ? "disabled" : opts_.wave_path) << "`\n\n";
    out << "This is a functional post-synthesis simulation of the Yosys-generated netlist. ";
    out << "It checks externally visible CPU behavior before the design moves to timing-aware GLS.\n\n";
    out << "| Cycle | Check | Result | Detail |\n";
    out << "| ---: | --- | --- | --- |\n";
    for (const auto& check : checks_) {
      out << "| " << check.cycle << " | " << check.name << " | "
          << (check.pass ? "PASS" : "FAIL") << " | " << check.detail << " |\n";
    }
  }

  Options opts_;
  Vmobile_cpu_top dut_;
  VerilatedVcdC* trace_ = nullptr;
  uint64_t time_ = 0;
  uint64_t cycle_ = 0;
  std::vector<Check> checks_;
  int failures_ = 0;
};

}  // namespace

int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);
  GateLevelSim sim(parse_options(argc, argv));
  return sim.run();
}
