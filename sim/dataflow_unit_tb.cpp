#include "Vdataflow_unit.h"
#include "verilated.h"

#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <string>

namespace {

void fail(const std::string& name, uint32_t expected, uint32_t actual) {
  std::cerr << "FAIL " << name << ": expected 0x" << std::hex << expected
            << " got 0x" << actual << std::dec << "\n";
  std::exit(1);
}

void expect_eq(const std::string& name, uint32_t expected, uint32_t actual) {
  if (expected != actual) {
    fail(name, expected, actual);
  }
}

void expect_true(const std::string& name, bool value) {
  if (!value) {
    std::cerr << "FAIL " << name << "\n";
    std::exit(1);
  }
}

void eval(Vdataflow_unit& dut) {
  dut.eval();
}

void tick(Vdataflow_unit& dut) {
  dut.clk = 0;
  eval(dut);
  dut.clk = 1;
  eval(dut);
  dut.clk = 0;
  eval(dut);
}

void reset(Vdataflow_unit& dut) {
  dut.clk = 0;
  dut.reset_n = 0;
  dut.enable = 1;
  dut.req = 0;
  dut.we = 0;
  dut.addr = 0;
  dut.wdata = 0;
  tick(dut);
  dut.reset_n = 1;
  tick(dut);
}

void write_reg(Vdataflow_unit& dut, uint8_t addr, uint32_t value) {
  dut.req = 1;
  dut.we = 1;
  dut.addr = addr;
  dut.wdata = value;
  tick(dut);
  dut.req = 0;
  dut.we = 0;
  tick(dut);
}

uint32_t read_reg(Vdataflow_unit& dut, uint8_t addr) {
  dut.req = 1;
  dut.we = 0;
  dut.addr = addr;
  eval(dut);
  uint32_t value = dut.rdata;
  dut.req = 0;
  eval(dut);
  return value;
}

uint32_t status(Vdataflow_unit& dut) {
  return read_reg(dut, 2);
}

uint32_t result(Vdataflow_unit& dut) {
  return read_reg(dut, 3);
}

void program_operands(Vdataflow_unit& dut, uint32_t a, uint32_t b) {
  write_reg(dut, 0, a);
  write_reg(dut, 1, b);
}

void check_single_mac_and_status() {
  Vdataflow_unit dut;
  reset(dut);
  program_operands(dut, 2, 3);
  write_reg(dut, 2, 1);
  expect_eq("single_mac_result", 6, result(dut));
  expect_true("single_mac_done", (status(dut) & 0x1u) != 0);
  expect_true("single_mac_not_busy", (status(dut) & 0x2u) == 0);
}

void check_clear_only() {
  Vdataflow_unit dut;
  reset(dut);
  program_operands(dut, 2, 3);
  write_reg(dut, 2, 1);
  write_reg(dut, 2, 2);
  expect_eq("clear_only_result", 0, result(dut));
  expect_true("clear_only_done", (status(dut) & 0x1u) != 0);
  expect_true("clear_only_not_busy", (status(dut) & 0x2u) == 0);
}

void check_clear_then_start_ordering() {
  Vdataflow_unit dut;
  reset(dut);
  program_operands(dut, 2, 3);
  write_reg(dut, 2, 1);
  program_operands(dut, 4, 5);
  write_reg(dut, 2, 3);
  expect_eq("clear_then_start_result", 20, result(dut));
  expect_true("clear_then_start_done", (status(dut) & 0x1u) != 0);
}

void check_held_command_does_not_repeat() {
  Vdataflow_unit dut;
  reset(dut);
  program_operands(dut, 2, 3);

  dut.req = 1;
  dut.we = 1;
  dut.addr = 2;
  dut.wdata = 1;
  tick(dut);
  tick(dut);
  tick(dut);
  tick(dut);
  dut.req = 0;
  dut.we = 0;
  tick(dut);

  expect_eq("held_command_single_mac", 6, result(dut));
}

void check_repeat_mode() {
  Vdataflow_unit dut;
  reset(dut);
  program_operands(dut, 2, 3);
  write_reg(dut, 3, 4);

  int valid_pulses = 0;
  dut.req = 1;
  dut.we = 1;
  dut.addr = 2;
  dut.wdata = 3;

  tick(dut);
  valid_pulses += dut.op_valid ? 1 : 0;
  expect_eq("repeat_first_result", 6, result(dut));
  expect_true("repeat_busy_after_start", dut.busy != 0);

  dut.req = 0;
  dut.we = 0;
  tick(dut);
  valid_pulses += dut.op_valid ? 1 : 0;
  tick(dut);
  valid_pulses += dut.op_valid ? 1 : 0;
  tick(dut);
  valid_pulses += dut.op_valid ? 1 : 0;

  expect_eq("repeat_result", 24, result(dut));
  expect_eq("repeat_valid_pulses", 4, static_cast<uint32_t>(valid_pulses));
  expect_true("repeat_done", (status(dut) & 0x1u) != 0);
  expect_true("repeat_not_busy", (status(dut) & 0x2u) == 0);
  expect_eq("repeat_status_count", 4, (status(dut) >> 16) & 0xffu);
}

}  // namespace

int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);
  check_single_mac_and_status();
  check_clear_only();
  check_clear_then_start_ordering();
  check_held_command_does_not_repeat();
  check_repeat_mode();
  std::cout << "DATAFLOW-UNIT PASS\n";
  return 0;
}
