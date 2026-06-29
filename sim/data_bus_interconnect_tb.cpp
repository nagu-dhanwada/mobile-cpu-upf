#include "Vdata_bus_interconnect.h"
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

void eval(Vdata_bus_interconnect& dut) {
  dut.eval();
}

void tick(Vdata_bus_interconnect& dut) {
  dut.clk = 0;
  eval(dut);
  dut.clk = 1;
  eval(dut);
  dut.clk = 0;
  eval(dut);
}

void reset(Vdata_bus_interconnect& dut) {
  dut.clk = 0;
  dut.reset_n = 0;
  dut.enable = 1;
  dut.req_valid = 0;
  dut.req_we = 0;
  dut.req_addr = 0;
  dut.req_wdata = 0;
  dut.req_byte_en = 0xf;
  dut.sram_rdata = 0;
  dut.dataflow_req_ready = 1;
  dut.dataflow_resp_valid = 0;
  dut.dataflow_resp_rdata = 0;
  dut.dataflow_resp_error = 0;
  tick(dut);
  dut.reset_n = 1;
  tick(dut);
}

void check_sram_route_and_response() {
  Vdata_bus_interconnect dut;
  reset(dut);

  dut.req_valid = 1;
  dut.req_we = 0;
  dut.req_addr = 0x20;
  dut.sram_rdata = 0x11112222;
  eval(dut);
  expect_true("sram_ready", dut.req_ready);
  expect_true("sram_req", dut.sram_req);
  expect_true("sram_read", !dut.sram_we);
  expect_eq("sram_addr", 0x20, dut.sram_addr);

  tick(dut);
  dut.req_valid = 0;
  for (int i = 0; i < 4 && !dut.resp_valid; ++i) {
    tick(dut);
  }
  expect_true("sram_resp_valid", dut.resp_valid);
  expect_true("sram_resp_ok", !dut.resp_error);
  expect_eq("sram_resp_data", 0x11112222, dut.resp_rdata);
}

void check_mmio_route_and_response() {
  Vdata_bus_interconnect dut;
  reset(dut);

  dut.req_valid = 1;
  dut.req_we = 1;
  dut.req_addr = 0x6;
  dut.req_wdata = 0x3;
  dut.dataflow_req_ready = 1;
  eval(dut);
  expect_true("mmio_ready", dut.req_ready);
  expect_true("mmio_req", dut.dataflow_req_valid);
  expect_true("mmio_we", dut.dataflow_req_we);
  expect_eq("mmio_local_addr", 2, dut.dataflow_req_addr);
  expect_eq("mmio_wdata", 3, dut.dataflow_req_wdata);

  tick(dut);
  dut.req_valid = 0;
  dut.dataflow_resp_rdata = 0xa5a50001;
  dut.dataflow_resp_valid = 1;
  tick(dut);
  dut.dataflow_resp_valid = 0;
  eval(dut);
  expect_true("mmio_resp_valid", dut.resp_valid);
  expect_true("mmio_resp_ok", !dut.resp_error);
  expect_eq("mmio_resp_data", 0xa5a50001, dut.resp_rdata);
}

void check_unmapped_error() {
  Vdata_bus_interconnect dut;
  reset(dut);

  dut.req_valid = 1;
  dut.req_we = 0;
  dut.req_addr = 0x400;
  eval(dut);
  expect_true("error_ready", dut.req_ready);
  expect_true("error_not_sram", !dut.sram_req);
  expect_true("error_not_mmio", !dut.dataflow_req_valid);

  tick(dut);
  dut.req_valid = 0;
  tick(dut);
  eval(dut);
  expect_true("error_resp_valid", dut.resp_valid);
  expect_true("error_resp", dut.resp_error);
}

}  // namespace

int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);
  check_sram_route_and_response();
  check_mmio_route_and_response();
  check_unmapped_error();
  std::cout << "DATA-BUS-INTERCONNECT PASS\n";
  return 0;
}
