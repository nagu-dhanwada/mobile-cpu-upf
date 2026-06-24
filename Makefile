PYTHON ?= python3
VERILATOR ?= verilator
YOSYS ?= yosys
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
GEN_WORKLOAD ?= dataflow_energy_probe
GEN_WORKLOAD_SPEC ?= workload_specs/$(GEN_WORKLOAD).json
GEN_WORKLOAD_OUT ?= workloads/generated
GEN_WORKLOAD_MANIFEST_DIR ?= build/workloadgen
SCENARIO_FILE ?= sim/scenarios/$(SCENARIO).tcl
POWER_SIM_DIR ?= build/power_sim
POWER_SIM_INC ?= /private/tmp/mobile_cpu_upf_power_sim_inc
POWER_SIM_OBJ ?= /private/tmp/mobile_cpu_upf_power_sim_obj
POWER_SIM_OBJ_VCD ?= /private/tmp/mobile_cpu_upf_power_sim_vcd_obj
POWER_SIM_SRC_LINK ?= /private/tmp/mobile_cpu_upf_src
JOULES_DIR ?= build/joules
TECH ?= generic_7nm
TECH_CONFIG ?= configs/tech/$(TECH).json
P2416_SPEC ?= spec_model/ieee2416_2025_schema.json
P2416_SCHEMA ?= schemas/ieee2416-2025.xsd
P2416_MODEL_DIR ?= power_models/mobile_cpu/rtl
P2416_REPORT_DIR ?= reports/2416/$(WORKLOAD)_$(TECH)
OPENLOWPOWER_2416_XSD ?= $(HOME)/Downloads/2416.xsd
OPENLOWPOWER_2416_MODEL ?= power_models/mobile_cpu/p2416/mobile_cpu_library.xml
OPENLOWPOWER_2416_REPORT_DIR ?= reports/p2416/$(WORKLOAD)_$(TECH)_$(SCHEME)
P2416_WORKLOADS ?= alu_idle compute_burst memory_burst cpu_mac dataflow_mac
P2416_SCHEMES ?= baseline_always_on clock_gated_idle core_power_gated_sleep dvfs_retention_domains
EFFICIENCY_WORKLOADS ?= cpu_mac dataflow_mac
DVFS_OPPS ?= configs/dvfs/mobile_cpu_opps.json
DVFS_REPORT_DIR ?= reports/2416/dvfs/$(WORKLOAD)_$(TECH)_$(SCHEME)
SYNTH_DIR ?= build/synth/$(WORKLOAD)
SYNTH_NETLIST ?= $(SYNTH_DIR)/mobile_cpu_gate.v
SYNTH_JSON ?= $(SYNTH_DIR)/mobile_cpu_synth.json
SYNTH_METRICS ?= $(SYNTH_DIR)/mobile_cpu_synth_metrics.json
SYNTH_MODEL_DIR ?= power_models/mobile_cpu/synth
SYNTH_2416_REPORT_DIR ?= reports/2416_synth/$(WORKLOAD)_$(TECH)
GLS_OBJ ?= /private/tmp/mobile_cpu_upf_gls_obj
TECHLIB ?= nangate45
TECHLIB_CONFIG ?= configs/techlibs/$(TECHLIB).json
TECHLIB_LIBERTY ?= third_party/nangate45/NangateOpenCellLibrary_typical.lib
TECHLIB_STDCELL_SIM ?= build/techlibs/$(TECHLIB)/NangateOpenCellLibrary.functional.v
STDCELL_MODEL_DIR ?= power_models/stdcells/$(TECHLIB)
STDCELL_SUMMARY ?= $(STDCELL_MODEL_DIR)/stdcells_summary.json
MEMORY_MACRO_CONFIG ?= configs/memory_macros/mobile_cpu_memory_macros.json
MEMORY_MACRO_MODEL_DIR ?= power_models/mobile_cpu/macros
MAPPED_DIR ?= build/mapped/$(TECHLIB)/$(WORKLOAD)
MAPPED_NETLIST ?= $(MAPPED_DIR)/mobile_cpu_mapped.v
MAPPED_JSON ?= $(MAPPED_DIR)/mobile_cpu_mapped.json
MAPPED_METRICS ?= $(MAPPED_DIR)/mobile_cpu_mapped_metrics.json
MAPPED_GLS_OBJ ?= /private/tmp/mobile_cpu_upf_mapped_gls_obj
MAPPED_2416_REPORT_DIR ?= reports/2416_mapped/$(TECHLIB)/$(WORKLOAD)_$(TECH)
ABSTRACTION_COMPARE_DIR ?= reports/2416_compare/$(WORKLOAD)_$(TECH)_$(TECHLIB)

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
	rtl/dataflow_unit.sv \
	rtl/mobile_cpu_top.sv

VERILATOR_WARNINGS := -Wno-UNUSEDSIGNAL -Wno-COMBDLY
VERILATOR_GLS_WARNINGS := $(VERILATOR_WARNINGS) -Wno-DECLFILENAME -Wno-LATCH -Wno-UNOPTFLAT

.PHONY: upf explore test lint-rtl gen-workload assemble-generated sim-generated sim-generated-vcd profile-generated assemble-workload sim-power sim-power-vcd sim-workload sim-workload-vcd synth gls synth-mapped gls-mapped techlib-nangate45 2416-stdcell-models 2416-stdcell-validate 2416-memory-macros 2416-memory-macro-validate joules-script joules-input joules-workload 2416-schema 2416-characterize 2416-validate 2416-activity 2416-power 2416-compare-workloads 2416-compare-schemes 2416-dvfs-explore 2416-synth-characterize 2416-synth-validate 2416-synth-power 2416-mapped-power 2416-compare-abstractions p2416-characterize p2416-validate p2416-power profile-workload compare-dataflow waves waves-workload clean

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

gen-workload:
	$(PYTHON) tools/gen_workload.py \
		--spec $(GEN_WORKLOAD_SPEC) \
		--out $(GEN_WORKLOAD_OUT) \
		--manifest-dir $(GEN_WORKLOAD_MANIFEST_DIR)

assemble-generated: gen-workload
	$(MAKE) assemble-workload WORKLOAD=generated/$(GEN_WORKLOAD)

sim-generated: gen-workload
	$(MAKE) sim-workload WORKLOAD=generated/$(GEN_WORKLOAD) SCHEME=$(SCHEME) SCENARIO=$(SCENARIO)

sim-generated-vcd: gen-workload
	$(MAKE) sim-workload-vcd WORKLOAD=generated/$(GEN_WORKLOAD) SCHEME=$(SCHEME) SCENARIO=$(SCENARIO)

profile-generated: gen-workload
	$(MAKE) profile-workload WORKLOAD=generated/$(GEN_WORKLOAD) TECH=$(TECH) SCHEME=$(SCHEME)

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
	mkdir -p "$(dir reports/$(WORKLOAD)_power_sim_events.json)" "$(dir waves/$(WORKLOAD).fst)"
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
	mkdir -p "$(dir reports/$(WORKLOAD)_power_sim_vcd_events.json)" "$(dir waves/$(WORKLOAD).vcd)"
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

synth: assemble-workload
	$(PYTHON) tools/run_yosys_synth.py \
		--yosys $(YOSYS) \
		--program $(WORKLOAD_MEMH) \
		--workload $(WORKLOAD) \
		--out $(SYNTH_DIR)

gls: synth
	mkdir -p reports/gls waves
	mkdir -p "$(dir reports/gls/$(WORKLOAD)_gate_summary.md)" "$(dir waves/$(WORKLOAD)_gate.vcd)"
	ln -sfn "$(CURDIR)" $(POWER_SIM_SRC_LINK)
	rm -rf $(GLS_OBJ)
	$(VERILATOR) --cc --exe --build --sv -Wall --trace-vcd $(VERILATOR_GLS_WARNINGS) \
		--Mdir $(GLS_OBJ) \
		-CFLAGS "-std=c++17 -Wno-unknown-warning-option" \
		--top-module mobile_cpu_top \
		$(POWER_SIM_SRC_LINK)/$(SYNTH_NETLIST) \
		$(POWER_SIM_SRC_LINK)/sim/gate_level_tb.cpp
	$(GLS_OBJ)/Vmobile_cpu_top \
		+workload=$(WORKLOAD) \
		+gate-summary=reports/gls/$(WORKLOAD)_gate_summary.md \
		+gate-wave=waves/$(WORKLOAD)_gate.vcd

techlib-nangate45:
	$(PYTHON) tools/install_nangate45.py --out third_party/nangate45

synth-mapped: assemble-workload techlib-nangate45
	$(PYTHON) tools/run_yosys_synth.py \
		--yosys $(YOSYS) \
		--program $(WORKLOAD_MEMH) \
		--workload $(WORKLOAD) \
		--out $(MAPPED_DIR) \
		--mapped \
		--memory-macros \
		--liberty $(TECHLIB_LIBERTY) \
		--macro-blackbox macros/memory/instr_rom_blackbox.v \
		--macro-blackbox macros/memory/data_sram_blackbox.v \
		--stdcell-sim $(TECHLIB_STDCELL_SIM)

gls-mapped: synth-mapped
	mkdir -p reports/gls waves
	mkdir -p "$(dir reports/gls/$(WORKLOAD)_$(TECHLIB)_mapped_gate_summary.md)" "$(dir waves/$(WORKLOAD)_$(TECHLIB)_mapped_gate.vcd)"
	ln -sfn "$(CURDIR)" $(POWER_SIM_SRC_LINK)
	rm -rf $(MAPPED_GLS_OBJ)
	$(VERILATOR) --cc --exe --build --sv -Wall --trace-vcd $(VERILATOR_GLS_WARNINGS) \
		--Mdir $(MAPPED_GLS_OBJ) \
		-CFLAGS "-std=c++17 -Wno-unknown-warning-option" \
		--top-module mobile_cpu_top \
		$(POWER_SIM_SRC_LINK)/$(TECHLIB_STDCELL_SIM) \
		$(POWER_SIM_SRC_LINK)/$(MAPPED_NETLIST) \
		$(POWER_SIM_SRC_LINK)/rtl/instr_rom.sv \
		$(POWER_SIM_SRC_LINK)/rtl/data_sram.sv \
		$(POWER_SIM_SRC_LINK)/sim/gate_level_tb.cpp
	$(MAPPED_GLS_OBJ)/Vmobile_cpu_top \
		+program=$(WORKLOAD_MEMH) \
		+workload=$(WORKLOAD)-$(TECHLIB) \
		+gate-summary=reports/gls/$(WORKLOAD)_$(TECHLIB)_mapped_gate_summary.md \
		+gate-wave=waves/$(WORKLOAD)_$(TECHLIB)_mapped_gate.vcd

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

2416-schema:
	$(PYTHON) tools/gen_2416_xsd.py --spec $(P2416_SPEC) --out $(P2416_SCHEMA)

2416-characterize: 2416-schema
	$(PYTHON) tools/characterize_2416.py --tech $(TECH_CONFIG) --out $(P2416_MODEL_DIR)

2416-validate: 2416-schema
	$(PYTHON) tools/validate_2416.py $(P2416_MODEL_DIR) --xsd $(P2416_SCHEMA)

2416-activity: sim-workload-vcd
	$(PYTHON) tools/vcd_activity_2416.py \
		--vcd waves/$(WORKLOAD).vcd \
		--out $(P2416_REPORT_DIR)/2416_activity.json

2416-power: 2416-characterize 2416-validate sim-workload-vcd
	$(PYTHON) tools/estimate_power_2416.py \
		--models $(P2416_MODEL_DIR) \
		--tech $(TECH_CONFIG) \
		--vcd waves/$(WORKLOAD).vcd \
		--scheme $(SCHEME) \
		--out $(P2416_REPORT_DIR)

2416-compare-workloads:
	@set -e; for workload in $(P2416_WORKLOADS); do \
		$(MAKE) 2416-power WORKLOAD=$$workload TECH=$(TECH) SCHEME=$(SCHEME) P2416_REPORT_DIR=reports/2416/$${workload}_$(TECH); \
	done
	$(PYTHON) tools/compare_2416.py \
		--result-root reports/2416 \
		--labels $(P2416_WORKLOADS) \
		--suffix _$(TECH) \
		--title "IEEE 2416 Workload Power Comparison ($(TECH), $(SCHEME))" \
		--out reports/2416/compare_workloads_$(TECH)_$(SCHEME)

2416-compare-schemes: 2416-characterize 2416-validate sim-workload-vcd
	@set -e; for scheme in $(P2416_SCHEMES); do \
		$(PYTHON) tools/estimate_power_2416.py \
			--models $(P2416_MODEL_DIR) \
			--tech $(TECH_CONFIG) \
			--vcd waves/$(WORKLOAD).vcd \
			--scheme $$scheme \
			--out reports/2416/$(WORKLOAD)_$(TECH)_$${scheme}; \
	done
	$(PYTHON) tools/compare_2416.py \
		--result-root reports/2416 \
		--labels $(P2416_SCHEMES) \
		--prefix $(WORKLOAD)_$(TECH)_ \
		--title "IEEE 2416 Power Scheme Comparison ($(WORKLOAD), $(TECH))" \
		--out reports/2416/compare_schemes_$(WORKLOAD)_$(TECH)

2416-dvfs-explore: 2416-characterize 2416-validate sim-workload-vcd
	$(PYTHON) tools/dvfs_explore_2416.py \
		--models $(P2416_MODEL_DIR) \
		--tech $(TECH_CONFIG) \
		--opps $(DVFS_OPPS) \
		--vcd waves/$(WORKLOAD).vcd \
		--scheme $(SCHEME) \
		--out $(DVFS_REPORT_DIR)

2416-synth-characterize: 2416-characterize synth
	$(PYTHON) tools/characterize_2416_synth.py \
		--rtl-models $(P2416_MODEL_DIR) \
		--metrics $(SYNTH_METRICS) \
		--out $(SYNTH_MODEL_DIR)

2416-synth-validate: 2416-schema 2416-synth-characterize
	$(PYTHON) tools/validate_2416.py $(SYNTH_MODEL_DIR) --xsd $(P2416_SCHEMA)

2416-synth-power: 2416-synth-validate sim-workload-vcd
	$(PYTHON) tools/estimate_power_2416.py \
		--models $(SYNTH_MODEL_DIR) \
		--tech $(TECH_CONFIG) \
		--vcd waves/$(WORKLOAD).vcd \
		--scheme $(SCHEME) \
		--out $(SYNTH_2416_REPORT_DIR)

2416-stdcell-models: 2416-schema techlib-nangate45
	$(PYTHON) tools/gen_2416_stdcell.py \
		--techlib $(TECHLIB_CONFIG) \
		--out $(STDCELL_MODEL_DIR)

2416-stdcell-validate: 2416-stdcell-models
	$(PYTHON) tools/validate_2416.py $(STDCELL_MODEL_DIR) --xsd $(P2416_SCHEMA)

2416-memory-macros: 2416-schema
	$(PYTHON) tools/gen_memory_macro_2416.py \
		--config $(MEMORY_MACRO_CONFIG) \
		--out $(MEMORY_MACRO_MODEL_DIR)

2416-memory-macro-validate: 2416-memory-macros
	$(PYTHON) tools/validate_2416.py $(MEMORY_MACRO_MODEL_DIR) --xsd $(P2416_SCHEMA)

2416-mapped-power: 2416-stdcell-models 2416-memory-macros sim-workload-vcd gls-mapped
	$(PYTHON) tools/estimate_mapped_power_2416.py \
		--metrics $(MAPPED_METRICS) \
		--stdcells $(STDCELL_SUMMARY) \
		--memory-macros $(MEMORY_MACRO_CONFIG) \
		--tech $(TECH_CONFIG) \
		--rtl-vcd waves/$(WORKLOAD).vcd \
		--gate-vcd waves/$(WORKLOAD)_$(TECHLIB)_mapped_gate.vcd \
		--scheme $(SCHEME) \
		--out $(MAPPED_2416_REPORT_DIR)

2416-compare-abstractions: 2416-power 2416-synth-power 2416-mapped-power
	$(PYTHON) tools/compare_2416_abstractions.py \
		--case rtl:$(P2416_REPORT_DIR) \
		--case synth:$(SYNTH_2416_REPORT_DIR) \
		--case mapped:$(MAPPED_2416_REPORT_DIR) \
		--out $(ABSTRACTION_COMPARE_DIR)

p2416-characterize:
	$(PYTHON) tools/p2416/characterize.py \
		--tech $(TECH_CONFIG) \
		--out $(OPENLOWPOWER_2416_MODEL)

p2416-validate: p2416-characterize
	$(PYTHON) tools/p2416/validate.py \
		$(OPENLOWPOWER_2416_MODEL) \
		--xsd $(OPENLOWPOWER_2416_XSD)

p2416-power: p2416-validate sim-workload-vcd
	$(PYTHON) tools/p2416/estimate.py \
		--model $(OPENLOWPOWER_2416_MODEL) \
		--tech $(TECH_CONFIG) \
		--vcd waves/$(WORKLOAD).vcd \
		--scheme $(SCHEME) \
		--out $(OPENLOWPOWER_2416_REPORT_DIR)

profile-workload: p2416-power
	$(PYTHON) tools/profile_workload.py \
		--workload $(WORKLOAD) \
		--estimate $(OPENLOWPOWER_2416_REPORT_DIR)/2416_power_estimate.json \
		--out $(OPENLOWPOWER_2416_REPORT_DIR)/workload_profile

compare-dataflow:
	@set -e; for workload in $(EFFICIENCY_WORKLOADS); do \
		$(MAKE) profile-workload WORKLOAD=$$workload TECH=$(TECH) SCHEME=$(SCHEME) OPENLOWPOWER_2416_REPORT_DIR=reports/p2416/$${workload}_$(TECH)_$(SCHEME); \
	done
	$(PYTHON) tools/compare_2416.py \
		--result-root reports/p2416 \
		--labels $(EFFICIENCY_WORKLOADS) \
		--suffix _$(TECH)_$(SCHEME) \
		--title "CPU vs Dataflow Workload Energy ($(TECH), $(SCHEME))" \
		--out reports/p2416/compare_dataflow_$(TECH)_$(SCHEME)

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
	rm -rf upf reports build waves $(POWER_SIM_INC) $(POWER_SIM_OBJ) $(POWER_SIM_OBJ_VCD) $(GLS_OBJ) $(MAPPED_GLS_OBJ) $(POWER_SIM_SRC_LINK)
