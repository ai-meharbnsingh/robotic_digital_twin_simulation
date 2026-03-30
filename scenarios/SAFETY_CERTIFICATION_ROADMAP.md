# Safety Certification Roadmap — SIL2 / PLd for io-gita Cold Start

## Target Standards

| Standard | Level | Scope |
|----------|-------|-------|
| IEC 61508 | SIL 2 | Functional safety of E/E/PE systems |
| ISO 13849 | PLd (Cat. 3) | Safety of machinery control systems |
| ISO 3691-4 | Clause 4.7 | Driverless industrial trucks — localization |
| IEC 62443 | SL 2 | Industrial cybersecurity |

## Current State — Gap Analysis

### What io-gita Has (passes)

| Requirement | Status | Evidence |
|------------|--------|----------|
| Independent safety scanner (SICK nanoScan3) | PASS | Safety rules S1-S7, config-driven |
| Minimum clearance check (2m) before any movement | PASS | `safety_checker.py` S1 |
| Max crawl speed (0.1 m/s) during recovery | PASS | `safety_checker.py` S3 |
| Independent safety laser (separate from navigation LiDAR) | PASS | `safety_checker.py` S5 |
| Scan quality validation (variance, valid ray percentage) | PASS | `io_gita_engine.py:263` |
| Recovery time bounded (<5s) | PASS | `io_gita_engine.py:267` |
| Confidence threshold with AMCL fallback | PASS | 70% threshold, proven |
| Multi-scan consensus (no single-scan lock) | PASS | `cold_start_node.py:79` |
| Config-only deployment (no code changes per warehouse) | PASS | YAML-driven |
| Pickle → JSON serialization (no arbitrary code execution) | PASS | Fix #3 from audit |

### What's Missing (gaps)

| Gap | SIL2 Requirement | Current State | Effort |
|-----|------------------|---------------|--------|
| **G1: Formal FMEA** | Failure Mode & Effects Analysis for all recovery paths | Informal — safety rules exist but no formal FMEA document | 2-3 weeks |
| **G2: Diagnostic coverage** | DC ≥ 90% for SIL2 | No formal diagnostic coverage calculation. Safety scanner is independent but not formally proven as diagnostic channel | 1-2 weeks |
| **G3: Hardware fault tolerance** | HFT = 0 for SIL2 (but Cat.3 PLd needs redundancy) | Single LiDAR for zone ID + independent safety scanner. No redundant zone ID channel | 2-4 weeks |
| **G4: Systematic capability** | SC 2 for SIL2 | No formal V-model lifecycle. Tests exist but not per IEC 61508 Part 3 | 4-6 weeks |
| **G5: Common cause failure** | β factor analysis | No CCF analysis between navigation LiDAR and safety scanner | 1 week |
| **G6: Proof test interval** | Defined test frequency with documented procedures | No formal proof test schedule. Calibration exists but not safety-qualified | 1 week |
| **G7: Safe state definition** | Documented safe states for all failure modes | Implicit (stop + AMCL fallback) but not formally specified | 1 week |
| **G8: Software safety lifecycle** | IEC 61508 Part 3 compliant development | Informal TDD. No safety requirements spec, no formal verification | 4-8 weeks |
| **G9: Cybersecurity** | IEC 62443 SL 2 for safety-relevant communication | No encrypted communication. YAML configs not integrity-checked | 2-3 weeks |
| **G10: Certification body engagement** | TÜV/UL assessment | Not started | Ongoing (6-12 months) |

## Architecture for SIL2

```
                    ┌─────────────────────────────────┐
                    │     SAFETY CONTROLLER (SIL2)    │
                    │  Independent safety PLC/MCU     │
                    │  Monitors: speed, clearance,    │
                    │  heartbeat, watchdog timer       │
                    └──────────┬──────────────────────┘
                               │ Safety I/O
                               │
    ┌──────────────────────────┼────────────────────────┐
    │                          │                        │
    ▼                          ▼                        ▼
┌────────────┐      ┌──────────────────┐      ┌─────────────────┐
│ SICK       │      │ io-gita          │      │ Motor           │
│ nanoScan3  │      │ Cold Start       │      │ Controller      │
│ (Cat.3)    │      │ (non-safety)     │      │ (STO via safety │
│            │      │                  │      │  relay)          │
│ Hardware   │      │ LiDAR → Zone ID  │      │                 │
│ safety     │      │ → Confidence     │      │ Safe Torque Off │
│ scanner    │      │ → AMCL fallback  │      │ if safety trip  │
└────────────┘      └──────────────────┘      └─────────────────┘
```

**Key principle**: io-gita is NOT the safety system. The SICK safety scanner + safety PLC provide the SIL2-rated protection. io-gita provides the intelligence layer that INFORMS navigation, with the safety system as an independent watchdog.

## Certification Path

### Phase 1: Documentation (Months 1-2)

| Deliverable | Standard Reference |
|-------------|-------------------|
| Safety Requirements Specification (SRS) | IEC 61508-1, Clause 7.10 |
| Failure Mode & Effects Analysis (FMEA) | IEC 61508-2, Annex C |
| Safe state definition document | IEC 61508-1, Clause 3.1.25 |
| Common Cause Failure analysis | IEC 61508-6, Annex D |
| Diagnostic coverage calculation | IEC 61508-2, Annex C |
| Software safety requirements | IEC 61508-3, Clause 7.2 |

### Phase 2: Architecture Modifications (Months 2-4)

| Modification | Reason |
|-------------|--------|
| Add watchdog timer on io-gita node | SIL2 requires fault detection within PFDT |
| Add heartbeat between io-gita and safety PLC | Detect io-gita hang → trigger STO |
| Implement CRC on calibration data | Integrity check for safety-relevant config |
| Add input validation on all scan data | Defensive programming per IEC 61508-3 |
| Separate safety-critical from non-safety code | Clear safety boundary |
| Add monotonic clock for recovery timeout | Prevent time manipulation |

### Phase 3: Testing per IEC 61508-3 (Months 4-6)

| Test Type | Coverage Target |
|-----------|----------------|
| Unit tests (MC/DC coverage) | ≥ 100% branch for safety functions |
| Integration tests | All safety-relevant interfaces |
| Fault injection tests | All FMEA failure modes |
| Stress tests | Dynamic obstacles, sensor degradation |
| Regression test suite | Automated, run on every change |
| Performance tests | Worst-case execution time proven |

### Phase 4: Assessment (Months 6-12)

| Activity | Provider |
|---------|----------|
| Pre-assessment review | TÜV SÜD or TÜV Rheinland |
| Gap closure from pre-assessment | Internal team |
| Formal assessment | Certification body |
| Certificate issuance | Certification body |

## PLd (ISO 13849) Specific Requirements

| Parameter | Required | Current |
|-----------|----------|---------|
| Category | 3 (single fault tolerance) | 2 (independent safety scanner, but no redundant zone ID) |
| MTTFd | High (30-100 years per channel) | Not calculated |
| DCavg | Medium (60-90%) | Not calculated |
| CCF score | ≥ 65 points | Not assessed |
| PFHd | ≤ 1×10⁻⁶ per hour | Not calculated |

### Path to Cat.3 PLd:

1. **Channel 1**: SICK nanoScan3 safety scanner (already Cat.3 rated)
2. **Channel 2**: io-gita zone ID + independent AMCL verification
3. **Monitoring**: Cross-check between Channel 1 and Channel 2
4. **Safe state**: Motor STO (Safe Torque Off) on disagreement

## Risk Assessment Matrix

| Hazard | Severity | Probability | Risk | Mitigation |
|--------|----------|------------|------|------------|
| Wrong zone → drive into shelf | Serious injury | Low (multi-scan consensus, 97% accuracy) | Medium | Safety scanner stops before collision |
| Recovery timeout → robot stuck | Operational loss | Medium | Low | 5s timeout → AMCL fallback → operator alert |
| Calibration drift → systematic error | Serious injury | Low (fleet learning updates fingerprints) | Medium | Periodic recalibration + drift detection |
| Scan sensor failure → no data | Operational loss | Low | Low | Scan quality check → AMCL fallback |
| Config file corruption | Wrong operation | Very low | Low | CRC validation (to be added) |
| Cyber attack on scan data | Serious injury | Very low (local network) | Low | IEC 62443 SL2 (to be added) |

## Estimated Timeline

```
Month 1-2:  Documentation (FMEA, SRS, safe states)
Month 2-4:  Architecture modifications (watchdog, heartbeat, CRC)
Month 4-6:  Testing (MC/DC, fault injection, stress)
Month 6-8:  Pre-assessment with TÜV
Month 8-10: Gap closure
Month 10-12: Formal assessment
Month 12+:  Certificate maintenance
```

## Cost Estimate

| Item | Estimate |
|------|----------|
| Safety engineering consultant (FMEA, SRS) | €30-50K |
| Architecture modifications (internal) | €20-30K |
| Testing infrastructure (fault injection rig) | €10-15K |
| TÜV pre-assessment | €15-25K |
| TÜV formal assessment | €30-50K |
| **Total** | **€105-170K** |

## Honest Assessment

io-gita is currently a **pre-certification intelligence layer**. It provides real value (0.008ms recovery, 97% zone accuracy) but is NOT safety-certified.

**What we can claim today**: "io-gita accelerates cold start recovery and informs navigation, with an independent SIL2-rated safety scanner providing the actual safety guarantee."

**What we CANNOT claim**: "io-gita is SIL2 certified" or "io-gita provides safety-rated localization."

**Recommendation**: The fastest path to deployment is to position io-gita as a non-safety performance optimization, with the SICK safety scanner as the certified safety layer. Full SIL2 certification of the io-gita algorithm itself would require 6-12 months and €100-170K, and may not be necessary if the safety architecture properly separates safety from performance.
