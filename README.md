# Temporal Runtime Reconstruction

Reproducibility repository for the study:

**Temporal Behavior Reconstruction under Heterogeneous Runtime Evidence Resolution for Digital Investigation**

## Overview

This repository contains the source code, reconstruction procedures, workload scripts, and analysis scripts used in the study.

The experiments evaluate temporal behaviour reconstruction using:

- filesystem runtime evidence
- sampled process-lifecycle evidence
- event-driven process-exit observation
- CPU-utilisation measurements
- process-start and process-end boundary experiments
- clock-alignment validation

## Dataset

The runtime evidence dataset supporting this study is publicly available on Zenodo:

https://doi.org/10.5281/zenodo.24547971

Version: 1.0.0

## Repository Structure

code/
- collection/
- reconstruction/
- analysis/

environment/
results/
docs/

## Experimental Platform

- Apple MacBook Air (MacBookAir10,1)
- Apple M1
- 8 CPU cores
- 8 GB unified memory
- macOS 15.3.1 (Build 24D70)
- Python 3.15.2
- psutil 7.2.2
## Sampling Intervals

The final experiments evaluated nominal sampling intervals of:

- 10 ms
- 25 ms
- 50 ms
- 100 ms
- 250 ms

## License

Source code in this repository is released under the MIT License.

The associated dataset is released on Zenodo under Creative Commons Attribution 4.0 International (CC BY 4.0).

## Citation

Citation metadata is available in CITATION.cff.
