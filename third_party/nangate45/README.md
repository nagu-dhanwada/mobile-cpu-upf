# Nangate45 Reference Technology Files

This directory is the local install location for the Nangate Open Cell Library
files used by the mapped synthesis and 2416 standard-cell power examples.

The large Liberty and Verilog files are intentionally ignored by git. Recreate
them with:

```sh
make techlib-nangate45
```

The flow expects:

- `NangateOpenCellLibrary_typical.lib`
- `NangateOpenCellLibrary.blackbox.v`
- `OpenCellLibraryLicenseSi2.txt`

These files are used as an educational/open reference library for mapping and
power-model experiments. They are not a signoff PDK.
