PYTHON ?= python3
VERILATOR ?= verilator
SURFER ?= $(shell command -v surfer || true)
GTKWAVE ?= $(shell command -v gtkwave || echo gtkwave)
GTKWAVE_APP ?= /Applications/gtkwave.app
WAVE_FILE ?= $(abspath waves/mobile_cpu_power.fst)
VCD_FILE ?= $(abspath waves/mobile_cpu_power.vcd)
SURFER_COMMAND_FILE ?= $(abspath sim/power_view.sucl)
SCHEME ?= dvfs_retention_domains
WORKLOAD ?= alu_idle
SCENARIO ?= power_modes
WORKLOAD_ASM ?= workloads/$(WORKLOAD).s
WORKLOAD_MEMH ?= build/workloads/$(WORKLOAD).memh
WORKLOAD_LISTING ?= build/workloads/$(WORKLOAD).lst
SCENARIO_FILE ?= sim/scenarios/$(SCENARIO).tcl
POWER_SIM_DIR ?= build/power_sim
POWER_SIM_INC ?= /private/tmp/mobile_cpu_upf_power_sim_inc
POWER_SIM_OBJ ?= /private/tmp/mobile_cpu_upf_power_sim_obj
POWER_SIM_OBJ_VCD ?= /private/tmp/mobile_cpu_upf_power_sim_vcd_obj
POWER_SIM_SRC_LINK ?= /private/tmp/mobile_cpu_upf_src
JOULES_DIR ?= build/joules

RTL_FILES := \
	rtl/mobile_cpu_pkg.sv \
	rtl/clock_gate.sv \
	rtl/power_controller.sv \
	rtl/fetch_unit.sv \
	rtl/instr_rom.sv \
	rtl/decode_unit.sv \
	rtl/regfile.sv \
	rtl/execute_unit.sv \
	rtl/data_sram.sv \
	rtl/mobile_cpu_top.sv

VERILATOR_WARNINGS := -Wno-UNUSEDSIGNAL -Wno-COMBDLY

.PHONY: upf explore test lint-rtl assemble-workload sim-power sim-power-vcd sim-workload sim-workload-vcd joules-script joules-input joules-workload waves waves-workload clean

upf:
	$(PYTHON) tools/gen_upf.py --schemes power_schemes --out upf

explore:
	$(PYTHON) tools/explore_power.py --schemes power_schemes --out reports

test:
	$(PYTHON) -m unittest discover -s tests

lint-rtl:
	$(VERILATOR) --lint-only --sv -Wall $(VERILATOR_WARNINGS) $(RTL_FILES)

assemble-workload:
	mkdir -p build/workloads
	$(PYTHON) tools/asm.py $(WORKLOAD_ASM) --memh $(WORKLOAD_MEMH) --listing $(WORKLOAD_LISTING)

sim-power:
	$(PYTHON) tools/gen_power_sim.py --scheme $(SCHEME) --schemes power_schemes --out $(POWER_SIM_DIR)
	mkdir -p reports waves $(POWER_SIM_INC)
	cp $(POWER_SIM_DIR)/power_intent.hpp $(POWER_SIM_INC)/power_intent.hpp
	ln -sfn "$(CURDIR)" $(POWER_SIM_SRC_LINK)
	rm -rf $(POWER_SIM_OBJ)
	$(VERILATOR) --cc --exe --build --sv -Wall --trace-fst $(VERILATOR_WARNINGS) \
		--Mdir $(POWER_SIM_OBJ) \
		-CFLAGS "-std=c++17 -Wno-unknown-warning-option -I$(POWER_SIM_INC)" \
		--top-module mobile_cpu_power_top \
		$(addprefix $(POWER_SIM_SRC_LINK)/,$(RTL_FILES)) \
		$(POWER_SIM_SRC_LINK)/sim/mobile_cpu_power_top.sv \
		$(POWER_SIM_SRC_LINK)/sim/power_aware_tb.cpp
	$(POWER_SIM_OBJ)/Vmobile_cpu_power_top \
		+power-sim-report=reports/power_sim_events.json \
		+power-sim-summary=reports/power_sim_summary.md \
		+power-sim-wave=waves/mobile_cpu_power.fst

sim-power-vcd:
	$(PYTHON) tools/gen_power_sim.py --scheme $(SCHEME) --schemes power_schemes --out $(POWER_SIM_DIR)
	mkdir -p reports waves $(POWER_SIM_INC)
	cp $(POWER_SIM_DIR)/power_intent.hpp $(POWER_SIM_INC)/power_intent.hpp
	ln -sfn "$(CURDIR)" $(POWER_SIM_SRC_LINK)
	rm -rf $(POWER_SIM_OBJ_VCD)
	$(VERILATOR) --cc --exe --build --sv -Wall --trace-vcd $(VERILATOR_WARNINGS) \
		--Mdir $(POWER_SIM_OBJ_VCD) \
		-CFLAGS "-std=c++17 -DPOWER_SIM_VCD -Wno-unknown-warning-option -I$(POWER_SIM_INC)" \
		--top-module mobile_cpu_power_top \
		$(addprefix $(POWER_SIM_SRC_LINK)/,$(RTL_FILES)) \
		$(POWER_SIM_SRC_LINK)/sim/mobile_cpu_power_top.sv \
		$(POWER_SIM_SRC_LINK)/sim/power_aware_tb.cpp
	$(POWER_SIM_OBJ_VCD)/Vmobile_cpu_power_top \
		+power-sim-report=reports/power_sim_vcd_events.json \
		+power-sim-summary=reports/power_sim_vcd_summary.md \
		+power-sim-wave=waves/mobile_cpu_power.vcd

sim-workload: assemble-workload
	$(PYTHON) tools/gen_power_sim.py --scheme $(SCHEME) --schemes power_schemes --out $(POWER_SIM_DIR)
	mkdir -p reports waves $(POWER_SIM_INC)
	cp $(POWER_SIM_DIR)/power_intent.hpp $(POWER_SIM_INC)/power_intent.hpp
	ln -sfn "$(CURDIR)" $(POWER_SIM_SRC_LINK)
	rm -rf $(POWER_SIM_OBJ)
	$(VERILATOR) --cc --exe --build --sv -Wall --trace-fst $(VERILATOR_WARNINGS) \
		--Mdir $(POWER_SIM_OBJ) \
		-CFLAGS "-std=c++17 -Wno-unknown-warning-option -I$(POWER_SIM_INC)" \
		--top-module mobile_cpu_power_top \
		$(addprefix $(POWER_SIM_SRC_LINK)/,$(RTL_FILES)) \
		$(POWER_SIM_SRC_LINK)/sim/mobile_cpu_power_top.sv \
		$(POWER_SIM_SRC_LINK)/sim/power_aware_tb.cpp
	$(POWER_SIM_OBJ)/Vmobile_cpu_power_top \
		+program=$(WORKLOAD_MEMH) \
		+workload=$(WORKLOAD) \
		+power-sim-scenario="$(abspath $(SCENARIO_FILE))" \
		+power-sim-report=reports/$(WORKLOAD)_power_sim_events.json \
		+power-sim-summary=reports/$(WORKLOAD)_power_sim_summary.md \
		+power-sim-wave=waves/$(WORKLOAD).fst

sim-workload-vcd: assemble-workload
	$(PYTHON) tools/gen_power_sim.py --scheme $(SCHEME) --schemes power_schemes --out $(POWER_SIM_DIR)
	mkdir -p reports waves $(POWER_SIM_INC)
	cp $(POWER_SIM_DIR)/power_intent.hpp $(POWER_SIM_INC)/power_intent.hpp
	ln -sfn "$(CURDIR)" $(POWER_SIM_SRC_LINK)
	rm -rf $(POWER_SIM_OBJ_VCD)
	$(VERILATOR) --cc --exe --build --sv -Wall --trace-vcd $(VERILATOR_WARNINGS) \
		--Mdir $(POWER_SIM_OBJ_VCD) \
		-CFLAGS "-std=c++17 -DPOWER_SIM_VCD -Wno-unknown-warning-option -I$(POWER_SIM_INC)" \
		--top-module mobile_cpu_power_top \
		$(addprefix $(POWER_SIM_SRC_LINK)/,$(RTL_FILES)) \
		$(POWER_SIM_SRC_LINK)/sim/mobile_cpu_power_top.sv \
		$(POWER_SIM_SRC_LINK)/sim/power_aware_tb.cpp
	$(POWER_SIM_OBJ_VCD)/Vmobile_cpu_power_top \
		+program=$(WORKLOAD_MEMH) \
		+workload=$(WORKLOAD) \
		+power-sim-scenario="$(abspath $(SCENARIO_FILE))" \
		+power-sim-report=reports/$(WORKLOAD)_power_sim_vcd_events.json \
		+power-sim-summary=reports/$(WORKLOAD)_power_sim_vcd_summary.md \
		+power-sim-wave=waves/$(WORKLOAD).vcd

joules-script: upf
	mkdir -p $(JOULES_DIR)
	$(PYTHON) tools/gen_joules.py \
		--scheme $(SCHEME) \
		--schemes power_schemes \
		--rtl-root . \
		--vcd "$(VCD_FILE)" \
		--upf upf/$(SCHEME).upf \
		--out $(JOULES_DIR)/run_joules_power.tcl

joules-input: upf sim-power-vcd joules-script

joules-workload: upf sim-workload-vcd
	mkdir -p $(JOULES_DIR)
	$(PYTHON) tools/gen_joules.py \
		--scheme $(SCHEME) \
		--schemes power_schemes \
		--rtl-root . \
		--vcd "$(abspath waves/$(WORKLOAD).vcd)" \
		--upf upf/$(SCHEME).upf \
		--out $(JOULES_DIR)/$(WORKLOAD)_run_joules_power.tcl

waves:
	@if [ -n "$(SURFER)" ]; then \
		"$(SURFER)" --command-file "$(SURFER_COMMAND_FILE)" "$(WAVE_FILE)"; \
	elif [ -d "$(GTKWAVE_APP)" ]; then \
		open -b com.geda.gtkwave "$(WAVE_FILE)" || \
		(cd / && "$(GTKWAVE_APP)/Contents/MacOS/gtkwave" "$(WAVE_FILE)"); \
	else \
		"$(GTKWAVE)" "$(WAVE_FILE)"; \
	fi

waves-workload:
	$(MAKE) waves WAVE_FILE="$(abspath waves/$(WORKLOAD).fst)"

clean:
	rm -rf upf reports build waves $(POWER_SIM_INC) $(POWER_SIM_OBJ) $(POWER_SIM_OBJ_VCD) $(POWER_SIM_SRC_LINK)
