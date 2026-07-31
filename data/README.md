# Data policy

This package does not distribute raw load or weather observations. The
`data/raw/` and `data/hourly_regions/` paths are local-only caches populated by
the public EIA/NOAA download and preparation scripts.

Only these public regions are supported:

- ERCO / ERCOT
- CISO / CAISO
- ISNE / ISO-NE
- MISO / MISO

The private Chinese-province data used in the article's primary analysis are
outside this repository and are not required by the public four-region
workflow.
