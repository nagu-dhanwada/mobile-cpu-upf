.PHONY: upf explore test clean

upf:
	python3 tools/gen_upf.py --schemes power_schemes --out upf

explore:
	python3 tools/explore_power.py --schemes power_schemes --out reports

test:
	python3 -m unittest discover -s tests

clean:
	rm -rf upf reports

