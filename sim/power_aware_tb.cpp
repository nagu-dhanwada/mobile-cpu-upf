#include "Vmobile_cpu_power_top.h"
#include "power_intent.hpp"
#include "verilated.h"
#ifdef POWER_SIM_VCD
#include "verilated_vcd_c.h"
#else
#include "verilated_fst_c.h"
#endif

#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace {

constexpr uint8_t MODE_RUN = 0;
constexpr uint8_t MODE_IDLE = 1;
constexpr uint8_t MODE_LIGHT_SLEEP = 2;
constexpr uint8_t MODE_DEEP_SLEEP = 3;
constexpr uint8_t MODE_WAKE = 4;

struct Options {
  std::string report_path = "reports/power_sim_events.json";
  std::string summary_path = "reports/power_sim_summary.md";
#ifdef POWER_SIM_VCD
  std::string wave_path = "waves/mobile_cpu_power.vcd";
#else
  std::string wave_path = "waves/mobile_cpu_power.fst";
#endif
  std::string scenario_path;
  std::string workload_name = "builtin";
  bool no_wave = false;
  bool inject_illegal_combo = false;
  bool disable_isolation_model = false;
  bool disable_retention_model = false;
};

struct Event {
  uint64_t cycle;
  std::string kind;
  std::string check;
  std::string detail;
  std::string mode;
  bool pass;
};

std::string json_escape(const std::string& input) {
  std::ostringstream out;
  for (char ch : input) {
    switch (ch) {
      case '\\':
        out << "\\\\";
        break;
      case '"':
        out << "\\\"";
        break;
      case '\n':
        out << "\\n";
        break;
      case '\r':
        out << "\\r";
        break;
      case '\t':
        out << "\\t";
        break;
      default:
        out << ch;
        break;
    }
  }
  return out.str();
}

bool starts_with(const std::string& text, const std::string& prefix) {
  return text.rfind(prefix, 0) == 0;
}

std::string trim(const std::string& text) {
  const auto first = text.find_first_not_of(" \t\r\n");
  if (first == std::string::npos) {
    return "";
  }
  const auto last = text.find_last_not_of(" \t\r\n");
  return text.substr(first, last - first + 1);
}

std::string strip_comment(const std::string& text) {
  const auto hash = text.find('#');
  if (hash == std::string::npos) {
    return trim(text);
  }
  return trim(text.substr(0, hash));
}

Options parse_options(int argc, char** argv) {
  Options opts;
  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];
    if (starts_with(arg, "+power-sim-report=")) {
      opts.report_path = arg.substr(std::string("+power-sim-report=").size());
    } else if (starts_with(arg, "+power-sim-summary=")) {
      opts.summary_path = arg.substr(std::string("+power-sim-summary=").size());
    } else if (starts_with(arg, "+power-sim-wave=")) {
      opts.wave_path = arg.substr(std::string("+power-sim-wave=").size());
    } else if (starts_with(arg, "+power-sim-scenario=")) {
      opts.scenario_path = arg.substr(std::string("+power-sim-scenario=").size());
    } else if (starts_with(arg, "+workload=")) {
      opts.workload_name = arg.substr(std::string("+workload=").size());
    } else if (arg == "+power-sim-no-wave=1") {
      opts.no_wave = true;
    } else if (arg == "+power-sim-inject-illegal=1") {
      opts.inject_illegal_combo = true;
    } else if (arg == "+power-sim-disable-isolation=1") {
      opts.disable_isolation_model = true;
    } else if (arg == "+power-sim-disable-retention=1") {
      opts.disable_retention_model = true;
    }
  }
  return opts;
}

std::string mode_name(uint8_t mode) {
  switch (mode) {
    case MODE_RUN:
      return "RUN";
    case MODE_IDLE:
      return "IDLE";
    case MODE_LIGHT_SLEEP:
      return "LIGHT_SLEEP";
    case MODE_DEEP_SLEEP:
      return "DEEP_SLEEP";
    case MODE_WAKE:
      return "WAKE";
    default:
      return "UNKNOWN";
  }
}

int mode_value(const std::string& value) {
  if (value == "RUN") {
    return MODE_RUN;
  }
  if (value == "IDLE") {
    return MODE_IDLE;
  }
  if (value == "LIGHT_SLEEP") {
    return MODE_LIGHT_SLEEP;
  }
  if (value == "DEEP_SLEEP") {
    return MODE_DEEP_SLEEP;
  }
  if (value == "WAKE") {
    return MODE_WAKE;
  }
  return std::strtol(value.c_str(), nullptr, 0);
}

class PowerAwareSim {
#ifdef POWER_SIM_VCD
  using TraceT = VerilatedVcdC;
#else
  using TraceT = VerilatedFstC;
#endif

 public:
  explicit PowerAwareSim(const Options& options) : opts_(options) {
    dut_.clk = 0;
    dut_.reset_n = 0;
    dut_.sleep_req = 0;
    dut_.deep_sleep_req = 0;
    dut_.wake_irq = 0;
    dut_.perf_boost = 0;
    dut_.scan_enable = 0;

    if (!opts_.no_wave) {
      Verilated::traceEverOn(true);
      trace_ = new TraceT;
      dut_.trace(trace_, 99);
      trace_->open(opts_.wave_path.c_str());
    }
  }

  ~PowerAwareSim() {
    if (trace_) {
      trace_->close();
      delete trace_;
      trace_ = nullptr;
    }
  }

  int run() {
    record("info", "scheme", power_intent::kSchemeName, true);
    record("info", "workload", opts_.workload_name, true);
    record("info", "upf_subset",
           "Modeling domains, switches, isolation, retention, level shifters, and PST legality.",
           true);

    if (opts_.inject_illegal_combo) {
      bool legal = power_intent::legal_domain_combo(true, false, true);
      require(!legal, "illegal_combo_fixture",
              "Injected AON=on CPU=off MEM=on combination should not be legal");
      require(false, "illegal_combo_observed",
              "Intentional negative fixture: simulator observed an illegal power-domain combo");
      finish_reports();
      return failures_ == 0 ? 0 : 2;
    }

    if (!opts_.scenario_path.empty()) {
      run_scripted_scenario();
    } else {
      apply_reset();
      check_run_and_idle();
      check_turbo_and_light_sleep();
      check_deep_sleep_and_wake();
    }
    check_level_shifter_coverage();

    finish_reports();
    return failures_ == 0 ? 0 : 1;
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
    record_mode_change();
    seen_modes_[mode()] = true;
  }

  void apply_reset() {
    dut_.reset_n = 0;
    dut_.sleep_req = 0;
    dut_.deep_sleep_req = 0;
    dut_.wake_irq = 0;
    dut_.perf_boost = 0;
    dut_.scan_enable = 0;
    for (int i = 0; i < 4; ++i) {
      tick();
    }
    dut_.reset_n = 1;
    for (int i = 0; i < 2; ++i) {
      tick();
    }
    require(mode() == MODE_RUN, "reset_to_run", "CPU should leave reset in RUN mode");
    require(domain_combo_is_legal(), "reset_domain_combo_legal", domain_combo_detail());
  }

  void check_run_and_idle() {
    uint32_t start_pc = dut_.debug_pc;
    bool pc_advanced = false;
    bool saw_idle = false;
    bool idle_core_clock_gated = false;
    bool idle_mem_clock_gated = false;
    bool idle_low_power_dvfs = false;

    for (int i = 0; i < 16; ++i) {
      tick();
      pc_advanced = pc_advanced || (dut_.debug_pc != start_pc);
      if (mode() == MODE_IDLE) {
        saw_idle = true;
        idle_core_clock_gated = idle_core_clock_gated || (dut_.core_clk_en == 0);
        idle_mem_clock_gated = idle_mem_clock_gated || (dut_.mem_clk_en == 0);
        idle_low_power_dvfs =
            idle_low_power_dvfs || (dut_.dvfs_level == power_intent::kLowPowerDvfsLevel);
      }
    }

    require(pc_advanced, "run_pc_advances", "PC should advance during RUN before WFI");
    require(saw_idle, "wfi_enters_idle", "WFI instruction should request IDLE mode");
    require(idle_core_clock_gated, "idle_core_clock_gated", "core_clk_en should be low in IDLE");
    require(idle_mem_clock_gated, "idle_mem_clock_gated", "mem_clk_en should be low in IDLE");
    require(idle_low_power_dvfs, "idle_low_power_dvfs", "IDLE should request the low-power DVFS level");
    require(domain_combo_is_legal(), "idle_domain_combo_legal", domain_combo_detail());
  }

  void check_turbo_and_light_sleep() {
    dut_.perf_boost = 1;
    for (int i = 0; i < 3; ++i) {
      tick();
    }
    require(mode() == MODE_RUN, "perf_boost_wakes_run", "perf_boost should leave IDLE for RUN");
    require(dut_.core_clk_en == 1, "turbo_core_clock_on", "core clock should be enabled in RUN");
    require(dut_.dvfs_level == power_intent::kTurboDvfsLevel,
            "turbo_dvfs_level", "perf_boost RUN should request TURBO DVFS");

    dut_.perf_boost = 0;
    tick();
    require(dut_.dvfs_level == power_intent::kNominalDvfsLevel,
            "nominal_dvfs_level", "RUN without perf_boost should request NOMINAL DVFS");

    dut_.sleep_req = 1;
    tick();
    require(mode() == MODE_LIGHT_SLEEP, "light_sleep_entered", "sleep_req should enter LIGHT_SLEEP");
    require(dut_.core_clk_en == 0, "light_sleep_core_clock_gated", "core clock should be gated");
    require(dut_.mem_clk_en == 0, "light_sleep_mem_clock_gated", "memory clock should be gated");
    require(ret_save_observed(), "light_sleep_retention_save", "ret_save should assert in LIGHT_SLEEP");
    require(domain_combo_is_legal(), "light_sleep_domain_combo_legal", domain_combo_detail());

    dut_.sleep_req = 0;
    dut_.wake_irq = 1;
    tick();
    require(mode() == MODE_WAKE, "light_sleep_wake_state", "wake_irq should enter WAKE");
    require(ret_restore_observed(), "light_sleep_retention_restore", "ret_restore should assert in WAKE");
    dut_.wake_irq = 0;
    tick();
    require(mode() == MODE_RUN, "light_sleep_returns_run", "WAKE should return to RUN");
  }

  void check_deep_sleep_and_wake() {
    dut_.deep_sleep_req = 1;
    tick();
    require(mode() == MODE_DEEP_SLEEP, "deep_sleep_entered", "deep_sleep_req should enter DEEP_SLEEP");
    require(cpu_on() == !power_intent::kCpuHasSwitch,
            "deep_sleep_cpu_switch", "CPU switched domain should be off in DEEP_SLEEP");
    require(mem_on() == !power_intent::kMemHasSwitch,
            "deep_sleep_mem_switch", "MEM switched domain should be off in DEEP_SLEEP");
    require(cpu_isolated(), "deep_sleep_cpu_isolated", "CPU isolation should clamp off-domain outputs");
    require(mem_isolated(), "deep_sleep_mem_isolated", "MEM isolation should clamp off-domain outputs");
    require(ret_save_observed(), "deep_sleep_retention_save", "ret_save should assert before wake");
    require(domain_combo_is_legal(), "deep_sleep_domain_combo_legal", domain_combo_detail());

    for (int i = 0; i < 3; ++i) {
      tick();
      require(cpu_isolated(), "deep_sleep_cpu_isolation_hold", "CPU isolation should remain asserted");
      require(mem_isolated(), "deep_sleep_mem_isolation_hold", "MEM isolation should remain asserted");
    }

    dut_.deep_sleep_req = 0;
    dut_.wake_irq = 1;
    tick();
    require(mode() == MODE_WAKE, "deep_sleep_wake_state", "wake_irq should enter WAKE");
    require(ret_restore_observed(), "deep_sleep_retention_restore", "ret_restore should assert in WAKE");
    require(cpu_on(), "deep_sleep_cpu_power_restored", "CPU switch should be on in WAKE");
    require(mem_on(), "deep_sleep_mem_power_restored", "MEM switch should be on in WAKE");
    dut_.wake_irq = 0;
    tick();
    require(mode() == MODE_RUN, "deep_sleep_returns_run", "WAKE should return to RUN");
  }

  void check_level_shifter_coverage() {
    if (power_intent::kNeedsVoltageLevelShifters) {
      require(power_intent::kLevelShifterCount > 0,
              "level_shifter_coverage",
              "Voltage-crossing legal states should have level-shifter strategy entries");
    } else {
      record("pass", "level_shifter_coverage", "No voltage-crossing state requires level shifters", true);
    }
  }

  void run_scripted_scenario() {
    std::ifstream input(opts_.scenario_path);
    if (!input) {
      require(false, "scenario_open", "Could not open scenario " + opts_.scenario_path);
      return;
    }
    record("info", "scenario", opts_.scenario_path, true);

    std::string raw_line;
    int line_no = 0;
    while (std::getline(input, raw_line)) {
      ++line_no;
      const std::string line = strip_comment(raw_line);
      if (line.empty()) {
        continue;
      }

      std::istringstream stream(line);
      std::string command;
      stream >> command;
      if (command == "reset") {
        int cycles = 4;
        stream >> cycles;
        scripted_reset(cycles);
      } else if (command == "run") {
        int cycles = 1;
        stream >> cycles;
        run_cycles(cycles);
      } else if (command == "run_until_mode") {
        std::string expected;
        int max_cycles = 1;
        stream >> expected;
        if (!(stream >> max_cycles)) {
          max_cycles = 1;
        }
        run_until_mode(expected, max_cycles, line_no);
      } else if (command == "set") {
        std::string signal;
        int value = 0;
        stream >> signal >> value;
        set_input(signal, value != 0);
      } else if (command == "pulse") {
        std::string signal;
        int cycles = 1;
        stream >> signal;
        if (!(stream >> cycles)) {
          cycles = 1;
        }
        set_input(signal, true);
        run_cycles(cycles);
        set_input(signal, false);
      } else if (command == "expect") {
        std::string signal;
        std::string expected;
        stream >> signal >> expected;
        expect_signal(signal, expected);
      } else if (command == "expect_seen_mode") {
        std::string expected;
        stream >> expected;
        const int expected_mode = mode_value(expected);
        const bool seen = expected_mode >= 0 && expected_mode < 8 && seen_modes_[expected_mode];
        require(seen, "scenario_expect_seen_mode",
                "Expected to have seen mode " + expected + " at line " + std::to_string(line_no));
      } else {
        require(false, "scenario_parse",
                "Unknown command at " + opts_.scenario_path + ":" + std::to_string(line_no) +
                    ": " + command);
      }
    }
  }

  void scripted_reset(int cycles) {
    dut_.reset_n = 0;
    dut_.sleep_req = 0;
    dut_.deep_sleep_req = 0;
    dut_.wake_irq = 0;
    dut_.perf_boost = 0;
    dut_.scan_enable = 0;
    for (int i = 0; i < cycles; ++i) {
      tick();
    }
    dut_.reset_n = 1;
    run_cycles(2);
    require(mode() == MODE_RUN, "scenario_reset_to_run", "Scenario reset should leave CPU in RUN");
  }

  void run_cycles(int cycles) {
    for (int i = 0; i < cycles; ++i) {
      tick();
      check_scripted_power_invariants();
    }
  }

  void run_until_mode(const std::string& expected, int max_cycles, int line_no) {
    const int expected_mode = mode_value(expected);
    if (expected_mode < 0 || expected_mode >= 8) {
      require(false, "scenario_run_until_mode",
              "Unknown mode " + expected + " at line " + std::to_string(line_no));
      return;
    }

    for (int i = 0; i < max_cycles; ++i) {
      tick();
      check_scripted_power_invariants();
      if (mode() == expected_mode) {
        require(true, "scenario_run_until_mode",
                "Reached mode " + expected + " within " + std::to_string(max_cycles) +
                    " cycles at line " + std::to_string(line_no));
        return;
      }
    }

    require(false, "scenario_run_until_mode",
            "Expected mode " + expected + " within " + std::to_string(max_cycles) +
                " cycles at line " + std::to_string(line_no));
  }

  void set_input(const std::string& signal, bool value) {
    if (signal == "reset_n") {
      dut_.reset_n = value;
    } else if (signal == "sleep_req") {
      dut_.sleep_req = value;
    } else if (signal == "deep_sleep_req") {
      dut_.deep_sleep_req = value;
    } else if (signal == "wake_irq") {
      dut_.wake_irq = value;
    } else if (signal == "perf_boost") {
      dut_.perf_boost = value;
    } else if (signal == "scan_enable") {
      dut_.scan_enable = value;
    } else {
      require(false, "scenario_set", "Unknown input signal " + signal);
    }
  }

  int read_signal(const std::string& signal) const {
    if (signal == "reset_n") {
      return dut_.reset_n;
    }
    if (signal == "sleep_req") {
      return dut_.sleep_req;
    }
    if (signal == "deep_sleep_req") {
      return dut_.deep_sleep_req;
    }
    if (signal == "wake_irq") {
      return dut_.wake_irq;
    }
    if (signal == "perf_boost") {
      return dut_.perf_boost;
    }
    if (signal == "power_mode") {
      return mode();
    }
    if (signal == "dvfs_level") {
      return dut_.dvfs_level;
    }
    if (signal == "core_clk_en") {
      return dut_.core_clk_en;
    }
    if (signal == "mem_clk_en") {
      return dut_.mem_clk_en;
    }
    if (signal == "cpu_power_gate_n") {
      return dut_.cpu_power_gate_n;
    }
    if (signal == "mem_power_gate_n") {
      return dut_.mem_power_gate_n;
    }
    if (signal == "iso_core") {
      return dut_.iso_core;
    }
    if (signal == "iso_mem") {
      return dut_.iso_mem;
    }
    if (signal == "ret_save") {
      return dut_.ret_save;
    }
    if (signal == "ret_restore") {
      return dut_.ret_restore;
    }
    return -1;
  }

  void expect_signal(const std::string& signal, const std::string& expected) {
    const int actual = read_signal(signal);
    const int expected_value = (signal == "power_mode") ? mode_value(expected)
                                                        : std::strtol(expected.c_str(), nullptr, 0);
    require(actual == expected_value, "scenario_expect",
            "Expected " + signal + "=" + expected + ", got " + std::to_string(actual));
  }

  void check_scripted_power_invariants() {
    if (!domain_combo_is_legal()) {
      require(false, "scenario_domain_combo_legal", domain_combo_detail());
    }

    switch (mode()) {
      case MODE_RUN:
        if (!script_checked_run_) {
          require(cpu_on(), "scenario_run_cpu_on", "CPU domain should be on in RUN");
          require(mem_on(), "scenario_run_mem_on", "MEM domain should be on in RUN");
          script_checked_run_ = true;
        }
        break;
      case MODE_IDLE:
        if (!script_checked_idle_) {
          require(dut_.core_clk_en == 0, "scenario_idle_core_clock_gated",
                  "core_clk_en should be low in IDLE");
          require(dut_.mem_clk_en == 0, "scenario_idle_mem_clock_gated",
                  "mem_clk_en should be low in IDLE");
          require(dut_.dvfs_level == power_intent::kLowPowerDvfsLevel,
                  "scenario_idle_low_power_dvfs", "IDLE should request low-power DVFS");
          script_checked_idle_ = true;
        }
        break;
      case MODE_LIGHT_SLEEP:
        if (!script_checked_light_sleep_) {
          require(dut_.core_clk_en == 0, "scenario_light_sleep_core_clock_gated",
                  "core clock should be gated in LIGHT_SLEEP");
          require(dut_.mem_clk_en == 0, "scenario_light_sleep_mem_clock_gated",
                  "memory clock should be gated in LIGHT_SLEEP");
          require(ret_save_observed(), "scenario_light_sleep_retention_save",
                  "ret_save should assert in LIGHT_SLEEP");
          script_checked_light_sleep_ = true;
        }
        break;
      case MODE_DEEP_SLEEP:
        if (!script_checked_deep_sleep_) {
          require(cpu_on() == !power_intent::kCpuHasSwitch,
                  "scenario_deep_sleep_cpu_switch",
                  power_intent::kCpuHasSwitch
                      ? "CPU switched domain should be off in DEEP_SLEEP"
                      : "CPU has no switch in this scheme and should remain modeled on");
          require(mem_on() == !power_intent::kMemHasSwitch,
                  "scenario_deep_sleep_mem_switch",
                  power_intent::kMemHasSwitch
                      ? "MEM switched domain should be off in DEEP_SLEEP"
                      : "MEM has no switch in this scheme and should remain modeled on");
          require(cpu_isolated(), "scenario_deep_sleep_cpu_isolated",
                  "CPU isolation should assert in DEEP_SLEEP");
          require(mem_isolated(), "scenario_deep_sleep_mem_isolated",
                  "MEM isolation should assert in DEEP_SLEEP");
          require(ret_save_observed(), "scenario_deep_sleep_retention_save",
                  "ret_save should assert in DEEP_SLEEP");
          script_checked_deep_sleep_ = true;
        }
        break;
      case MODE_WAKE:
        if (!script_checked_wake_) {
          require(cpu_on(), "scenario_wake_cpu_on", "CPU domain should be restored in WAKE");
          require(mem_on(), "scenario_wake_mem_on", "MEM domain should be restored in WAKE");
          require(ret_restore_observed(), "scenario_wake_retention_restore",
                  "ret_restore should assert in WAKE");
          script_checked_wake_ = true;
        }
        break;
      default:
        break;
    }
  }

  uint8_t mode() const {
    return static_cast<uint8_t>(dut_.power_mode);
  }

  bool cpu_on() const {
    return !power_intent::kCpuHasSwitch || dut_.cpu_power_gate_n;
  }

  bool mem_on() const {
    return !power_intent::kMemHasSwitch || dut_.mem_power_gate_n;
  }

  bool cpu_isolated() const {
    return !power_intent::kCpuHasIsolation || (dut_.iso_core && !opts_.disable_isolation_model);
  }

  bool mem_isolated() const {
    return !power_intent::kMemHasIsolation || (dut_.iso_mem && !opts_.disable_isolation_model);
  }

  bool ret_save_observed() const {
    const bool requires_retention = power_intent::kCpuHasRetention || power_intent::kMemHasRetention;
    return !requires_retention || (dut_.ret_save && !opts_.disable_retention_model);
  }

  bool ret_restore_observed() const {
    const bool requires_retention = power_intent::kCpuHasRetention || power_intent::kMemHasRetention;
    return !requires_retention || (dut_.ret_restore && !opts_.disable_retention_model);
  }

  bool domain_combo_is_legal() const {
    return power_intent::legal_domain_combo(true, cpu_on(), mem_on());
  }

  std::string domain_combo_detail() const {
    std::ostringstream out;
    out << "AON=on CPU=" << (cpu_on() ? "on" : "off")
        << " MEM=" << (mem_on() ? "on" : "off")
        << " mode=" << mode_name(mode());
    return out.str();
  }

  void record_mode_change() {
    if (!have_last_mode_ || mode() != last_mode_) {
      last_mode_ = mode();
      have_last_mode_ = true;
      record("mode", "mode_change", "Entered " + mode_name(mode()), true);
    }
  }

  void require(bool condition, const std::string& check, const std::string& detail) {
    if (!condition) {
      ++failures_;
      record("fail", check, detail, false);
    } else {
      record("pass", check, detail, true);
    }
  }

  void record(const std::string& kind, const std::string& check,
              const std::string& detail, bool pass) {
    events_.push_back(Event{cycle_, kind, check, detail, mode_name(mode()), pass});
  }

  void finish_reports() {
    write_events();
    write_summary();
    if (failures_ == 0) {
      std::cout << "POWER-SIM PASS: wrote " << opts_.summary_path << "\n";
    } else {
      std::cout << "POWER-SIM FAIL: " << failures_ << " failure(s); wrote "
                << opts_.summary_path << "\n";
    }
  }

  void write_events() const {
    std::ofstream out(opts_.report_path);
    out << "[\n";
    for (size_t i = 0; i < events_.size(); ++i) {
      const auto& event = events_[i];
      out << "  {"
          << "\"cycle\":" << event.cycle << ","
          << "\"kind\":\"" << json_escape(event.kind) << "\","
          << "\"check\":\"" << json_escape(event.check) << "\","
          << "\"detail\":\"" << json_escape(event.detail) << "\","
          << "\"mode\":\"" << json_escape(event.mode) << "\","
          << "\"pass\":" << (event.pass ? "true" : "false")
          << "}";
      if (i + 1 != events_.size()) {
        out << ",";
      }
      out << "\n";
    }
    out << "]\n";
  }

  void write_summary() const {
    int passes = 0;
    for (const auto& event : events_) {
      if (event.kind == "pass") {
        ++passes;
      }
    }

    std::ofstream out(opts_.summary_path);
    out << "# Power-Aware Simulation Summary\n\n";
    out << "- Scheme: `" << power_intent::kSchemeName << "`\n";
    out << "- Result: " << (failures_ == 0 ? "PASS" : "FAIL") << "\n";
    out << "- Passing checks: " << passes << "\n";
    out << "- Failing checks: " << failures_ << "\n";
    out << "- Waveform: `" << (opts_.no_wave ? "disabled" : opts_.wave_path) << "`\n\n";
    out << "This is a UPF-driven simulation model for the supported project subset. ";
    out << "It checks power-domain legality, isolation, retention, DVFS state requests, ";
    out << "and level-shifter strategy coverage around the toy mobile CPU.\n\n";
    out << "| Cycle | Kind | Check | Mode | Detail |\n";
    out << "| ---: | --- | --- | --- | --- |\n";
    for (const auto& event : events_) {
      if (event.kind == "info") {
        continue;
      }
      out << "| " << event.cycle << " | " << event.kind << " | " << event.check
          << " | " << event.mode << " | " << event.detail << " |\n";
    }
    out << "\n";
  }

  Options opts_;
  Vmobile_cpu_power_top dut_;
  TraceT* trace_ = nullptr;
  uint64_t time_ = 0;
  uint64_t cycle_ = 0;
  std::vector<Event> events_;
  int failures_ = 0;
  uint8_t last_mode_ = 0;
  bool have_last_mode_ = false;
  bool seen_modes_[8] = {};
  bool script_checked_run_ = false;
  bool script_checked_idle_ = false;
  bool script_checked_light_sleep_ = false;
  bool script_checked_deep_sleep_ = false;
  bool script_checked_wake_ = false;
};

}  // namespace

int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);
  Options opts = parse_options(argc, argv);
  PowerAwareSim sim(opts);
  return sim.run();
}
