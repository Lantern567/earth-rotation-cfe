# Three-site trace-driven power-accounting experiment

This controlled experiment tests how geographic placement affects electricity accounting when both the sending and receiving sites are included. It is separate from the annual country-scale waveform analysis. The input is the complete Azure coding trace, containing 16,803,695 requests over 168 UTC hours from 10 to 16 May 2024. The release provides request timestamps and input/output token counts, without location, GPU configuration, metered power or serving-delay measurements. The experiment therefore uses real arrival counts with specified origin, capacity, power and renewable-supply scenarios; its numerical outputs are modeled electricity quantities.

## Workload and capacity

The zero-based row index of each original request is reduced modulo ten. Residues 0–4 are assigned to the US, 5–7 to Germany and 8–9 to Japan. This deterministic allocation preserves every request and produces approximately 50%, 30% and 20% origin shares. These labels are experiment assignments, without inference about users' true locations. The hourly request count is not rescaled. Optimization uses continuous hourly request-equivalent flows, with a common modeled processing weight. The trace's mean input/output lengths are 2,511.28/22.69 tokens; token-level energy and serving times are unmeasured, and the benchmark endpoints do not characterize this length distribution.

At each origin, each UTC day has a finite background pool equal to the ceiling of 20% of that origin's daily request count. These are scenario job units with the same modeled processing weight as one interactive request. The resulting fixed background pool contains 3,360,749 job units. Every comparison completes the same interactive arrivals in their arrival hour and the same background pool by the end of its release day. No additional background work appears when capacity becomes available.

The published high-load arrival rate of 0.3 requests per second per GPU supplies a design reference, with a chosen utilization ceiling of 80%. Each site's installed fleet is the ceiling of its maximum hourly local interactive demand plus the uniform daily background allocation, divided by this design capacity. The resulting fixed fleets are 190, 114 and 76 GPUs in the US, Germany and Japan. The rate and headroom are scenario design choices; the benchmark arrival rate is not a measured saturation capacity or a service guarantee for the Azure requests. Hourly average capacity does not certify sub-hour bursts.

## Power and shared clean supply

For site j and hour h, the modeled GPU power is

`P[j,h] = N_awake[j,h] P_idle + (P_high - P_idle) (I[j,h] + B[j,h]) / (0.3 × 3600)`,

where I and B denote executed interactive requests and background job units per hour. This interpolates between an idle endpoint and a high-load mean for a reference GPU. The H100, A100 and L4 scenarios use idle/high-load endpoints of 59/165.9 W, 56/172.9 W and 17/68.7 W, respectively. These are GPU board-level measurements and medium-model class averages from [Watt Counts](https://arxiv.org/html/2604.09048v1), Fig. 5 and Table 6. They do not provide model-specific Azure request energy or whole-server power curves.

The same execution ledger is also evaluated with a piecewise linear interpolation through the published low-load endpoint at 0.017 requests/s. Those endpoints are 94.7, 70.7 and 38.8 W for the same three GPUs (Table 5). This changes the accounting curve while freezing placement and awake counts; it is a sensitivity calculation, without claiming a newly optimized schedule.

Country hourly renewable profiles come from the paper's existing wind/solar reconstruction. A 50:50 rated-capacity blend is used within each site. Each 2024 request hour is paired with the same civil month, day and UTC hour in 2025. The time alignment creates a controlled cross-year experiment; arrivals and renewable generation are not contemporaneous observations. Each site's blended series is scaled once to the energy consumed by its local, always-on GPU baseline. The resulting three supply series remain identical across every placement and power policy within a hardware scenario. Supply is physically shared within this experiment: every executed job consumes site power, and site clean generation can cover that site's demand once. Hourly surplus is not exported or stored. Different hardware scenarios are separately referenced to their own baseline, so their clean-energy budgets must not be interpreted as a common cross-hardware allocation.

## Placement and power-management policies

Origin–destination flows conserve the entire hourly interactive workload. Assumed added network delays are 120 ms between US–Germany, 180 ms between US–Japan and 220 ms between Germany–Japan, with zero added delay for local execution. Local-only, 200 ms and 500 ms added-delay budgets define nested admissible sets. These values are explicit budget scenarios; they are not measured paths or network percentiles. A request remains at its chosen destination for the complete response.

The three policies are:

1. **Remain on with idle capacity.** All installed GPUs remain awake. Background work runs uniformly within each release day at its assigned origin. Routing changes interactive placement, while the freed idle electricity stays at the sending site.
2. **Finite backfill.** All installed GPUs remain awake. The same local background pool can be rearranged within its release day. Its hourly allowance cannot exceed the uniform background allocation plus capacity released by outbound interactive jobs, and total site workload remains below capacity. The daily background amount is fixed at every site.
3. **Consolidate and sleep.** Background work retains its uniform local schedule. Integer awake counts can change from one hour to the next, with at least one warm replica at every site. Interactive placement and awake capacity are chosen jointly. Required additional replicas are assumed to be predictively prewarmed before the relevant hour, with no reactive cold start on a newly arriving request's path.

For each policy, an LP or MILP minimizes the sum over sites and hours of `max(P - G, 0)`, where G is the fixed clean supply. For consolidation, a second optimization minimizes total GPU energy while retaining the first-stage minimum absolute gap to within 0.00001 kWh. This removes arbitrary selection among equally matched solutions. Comparisons report absolute unmatched kWh, total modeled kWh, unmatched percentage, routed fraction, awake GPU hours, activation counts and all conserved job totals. Percentages for different power policies have different denominators, so absolute kWh identifies the matching effect.

The transition sensitivity retains the optimized no-charge execution schedule, adds 34,393.48 J (9.553744 Wh) per new replica activation and allocates the energy to the previous hour for predictive preparation. This charge is drawn from initialization plus 8B model loading in a separate two-H100 node experiment in [Niu et al.](https://hotcarbon.org/assets/2025/paper-11.pdf), Table 1; the reported setup lasts 60.03 s. Applying that external node-level charge per logical activation is a stress assumption, not a measurement of these GPUs' sleep/wake transitions. Initial deployment is excluded equally from all policies. Prediction accuracy and warm-capacity operation remain unmeasured.

Fixed non-GPU load of 0, 50 or 100 W per installed GPU and PUE values of 1.0, 1.2 or 1.5 are evaluated with the execution schedule frozen. Fixed load stays at its site even when GPU counts fall. These parameters do not supply measured facility characteristics. Their purpose is to quantify how a fixed local electricity component can dilute the benefit of migrating requests.

## TTFT and token-delivery constraints

An added network budget is one component of service admission. An operational controller needs separate constraints on

`network setup + queue + prefill + handshake/reserve ≤ TTFT budget`

and

`generation interval + streaming jitter ≤ TBT budget`.

Elapsed completion time is not an allowable network delay. For an entire response executed at one destination, fixed path propagation shifts the first-token arrival; subsequent token gaps depend on generation and network variation. Mid-response migration would additionally require state transfer and continuity checks, which this experiment does not model.

The illustrative service-budget table allocates 100 ms to engine queue/prefill and 100 ms to handshake/jitter reserve, yielding total TTFT budgets of 200, 400 or 700 ms alongside added network budgets of 0, 200 or 500 ms. It separately labels a 100 ms TBT budget. These allowances are assumptions, without measured performance guarantees. Watt Counts Table 6 reports class averages of experiment TTFT p95 values of 39, 48 and 203 ms for H100, A100 and L4; an average of percentiles does not certify the tail of this trace or an arbitrary deployed model. Azure has no TTFT or TBT observations. The released routing, capacity and energy ledgers certify modeled hourly conservation and supply accounting, while empirical request-level service certification requires the intended deployment's network, queue, prefill and token-generation measurements.

## Verification and scope

The implementation verifies every origin-hour flow balance, each origin-day background pool, each receiving site's design-capacity bound, every reported energy/gap ledger and solver completion. It also checks that enlarging the admissible network set does not increase the optimized absolute gap beyond numerical tolerance. Full input hashes, scenario constants and solver status are recorded. These are deterministic accounting checks on real trace timing and reconstructed supply, without measured facility-power validation, request-level queue simulation, failure recovery, user-location inference or a claim about the annual global physical clean-power floor.
