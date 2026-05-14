# Crux reproduction implementation map

This file maps the offline simulator to the Crux paper sections.

## Paper section 3: GPU intensity

Implemented in `Job.intensity`:

```python
job.intensity = job.compute_work / job.base_comm_time
```

The simulator treats `compute_work` as the per-iteration useful GPU work and
`base_comm_time` as the job's isolated communication time.

## Paper section 4.1: GPU-intensity-aware path selection

Implemented by `assign_crux_paths`.

Jobs are sorted by descending GPU intensity. Each job chooses the currently
least-loaded candidate ECMP path. Link load is weighted by traffic and
intensity, so high-intensity jobs are spread away from each other first.

## Paper section 4.2: priority assignment

Implemented by `assign_logical_priorities(..., mode="crux")`.

The paper computes a correction factor from iteration characteristics and
compute/communication overlap. This simulator uses a compact proxy:

```python
correction = sensitivity * (1.0 + 1.0 / iteration_time)
logical_priority = intensity * correction
```

where `sensitivity = 1 - overlap_ratio`. Jobs whose communication is less
hidden by computation become more urgent.

## Paper section 4.3: priority compression

Implemented by `contention_dag`, `random_topological_order`,
`best_sequence_cut`, and `compress_priorities`.

The simulator builds a communication contention DAG:

- node: one DLT job;
- directed edge: higher-priority job can contend with lower-priority job;
- edge weight: higher-priority job's GPU intensity.

It samples 10 topological orders and chooses the best sequence K-cut. The code
uses exhaustive split enumeration because the local reproduction uses small
job counts; the paper uses a more efficient dynamic programming formulation.

## Paper section 5: deployment mechanisms

Not implemented in this offline simulator.

The real paper uses RoCEv2 source-port steering for ECMP path selection,
traffic classes for inter-host priority queues, and semaphores for intra-host
PCIe priority. Reproducing this requires a real multi-GPU/multi-NIC testbed.

## Paper section 6: evaluation

Implemented qualitatively by comparing:

- `random_same`: random ECMP and one priority level;
- `random_intensity`: random ECMP plus intensity priority;
- `crux_no_compress`: Crux path selection with enough logical priorities;
- `crux`: Crux path selection plus limited hardware priority levels.

The expected trend is:

```text
random_same < random_intensity < crux ~= crux_no_compress
```

Exact paper numbers are not expected from this simulator because it does not
use the production trace, NCCL kernels, or physical GPU/NIC/PCIe measurements.
