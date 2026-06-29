#include "Vload_store_unit.h"
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

void eval(Vload_store_unit& dut) {
  dut.eval();
}

void tick(Vload_store_unit& dut) {
  dut.clk = 0;
  eval(dut);
  dut.clk = 1;
  eval(dut);
  dut.clk = 0;
  eval(dut);
}

void reset(Vload_store_unit& dut) {
  dut.clk = 0;
  dut.reset_n = 0;
  dut.enable = 1;
  dut.execute_mem_req = 0;
  dut.execute_mem_we = 0;
  dut.execute_wb_addr = 0;
  dut.execute_mem_addr = 0;
  dut.execute_mem_wdata = 0;
  dut.bus_req_ready = 1;
  dut.bus_resp_valid = 0;
  dut.bus_resp_rdata = 0;
  dut.bus_resp_error = 0;
  tick(dut);
  dut.reset_n = 1;
  tick(dut);
}

void check_delayed_load_stalls_and_writes_back() {
  Vload_store_unit dut;
  reset(dut);

  dut.execute_mem_req = 1;
  dut.execute_mem_we = 0;
  dut.execute_wb_addr = 5;
  dut.execute_mem_addr = 0x20;
  dut.bus_req_ready = 1;
  eval(dut);
  expect_true("load_initial_stall", dut.stall);
  expect_true("load_req_valid", dut.bus_req_valid);
  expect_eq("load_req_addr", 0x20, dut.bus_req_addr);

  tick(dut);
  int duplicate_requests = 0;
  for (int i = 0; i < 3; ++i) {
    eval(dut);
    duplicate_requests += dut.bus_req_valid ? 1 : 0;
    expect_true("load_wait_stall", dut.stall);
    tick(dut);
  }
  expect_eq("load_no_duplicate_requests", 0, duplicate_requests);

  dut.bus_resp_rdata = 0x12345678;
  dut.bus_resp_valid = 1;
  tick(dut);
  dut.bus_resp_valid = 0;
  eval(dut);
  expect_true("load_done_retires", dut.retired);
  expect_true("load_done_releases_stall", !dut.stall);
  expect_true("load_wb_en", dut.load_wb_en);
  expect_eq("load_wb_addr", 5, dut.load_wb_addr);
  expect_eq("load_wb_data", 0x12345678, dut.load_wb_data);
  dut.execute_mem_req = 0;
}

void check_store_retires_after_response() {
  Vload_store_unit dut;
  reset(dut);

  dut.execute_mem_req = 1;
  dut.execute_mem_we = 1;
  dut.execute_mem_addr = 0x24;
  dut.execute_mem_wdata = 0xfeedcafe;
  dut.bus_req_ready = 1;
  eval(dut);
  expect_true("store_initial_stall", dut.stall);
  expect_true("store_req_valid", dut.bus_req_valid);
  expect_true("store_req_we", dut.bus_req_we);
  expect_eq("store_req_wdata", 0xfeedcafe, dut.bus_req_wdata);
  tick(dut);

  expect_true("store_wait_stall", dut.stall);
  dut.bus_resp_valid = 1;
  tick(dut);
  dut.bus_resp_valid = 0;
  eval(dut);
  expect_true("store_retired", dut.retired);
  expect_true("store_no_wb", !dut.load_wb_en);
  dut.execute_mem_req = 0;
}

void check_error_response_is_observed() {
  Vload_store_unit dut;
  reset(dut);

  dut.execute_mem_req = 1;
  dut.execute_mem_we = 0;
  dut.execute_wb_addr = 6;
  tick(dut);
  dut.bus_resp_error = 1;
  dut.bus_resp_valid = 1;
  tick(dut);
  dut.bus_resp_valid = 0;
  eval(dut);
  expect_true("error_retired", dut.retired);
  expect_true("error_seen", dut.error_seen);
  expect_true("error_suppresses_load_wb", !dut.load_wb_en);
  dut.execute_mem_req = 0;
}

}  // namespace

int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);
  check_delayed_load_stalls_and_writes_back();
  check_store_retires_after_response();
  check_error_response_is_observed();
  std::cout << "LOAD-STORE-UNIT PASS\n";
  return 0;
}
