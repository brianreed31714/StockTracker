# ZPTA headline overlay — source audit (2026-11-04)

Status: SOURCE DISCOVERY ONLY. No headline performance lift is established. The existing `analysis/zpta_quantum_headline_join.py` requires timezone-aware first-publication timestamps, URL, scope and sentiment; date-only records MUST NOT be passed off as verified intraday timestamps.

## Primary-source candidates (verify first-publication timestamps before joining)
| Publication date | Event | Primary source | Classification status |
|---|---|---|---|
| 2026-04-23 | $15M strategic financing | https://www.sec.gov/Archives/edgar/data/1843714/000107997326000531/ex99x1.htm | Unlabeled: capital raised and dilution risk need separate assessment |
| 2026-06-23 | NVIDIA quantum/agentic-AI collaboration | https://investors.zapataquantum.com/news-releases | Unlabeled: partnership catalyst |
| 2026-08-12 | QuEra partnership | https://www.sec.gov/Archives/edgar/data/1843714/000168316826006225/zapata_ex9901.htm | Unlabeled: partnership catalyst |
| 2026-09-22 | Quantum Pilot early access | https://www.sec.gov/Archives/edgar/data/1843714/000168316826007295/zapata_ex9901.htm | Unlabeled: product catalyst |
| 2026-10-06 | IBM Quantum Network announcement | https://investors.zapataquantum.com/news-releases/news-release-details/zapata-quantum-joins-ibm-quantum-network-accelerate-mission | Unlabeled: partnership catalyst |
| 2026-10-20 | Scientific advisory board | https://investors.zapataquantum.com/news-releases | Unlabeled: personnel/scientific catalyst |

## Non-negotiable next steps
1. Retrieve exact first-publication timestamps (timezone-aware) and deduplicate syndications; assign publication-time uncertainty when only date is available. Do not invent 09:00 or 16:00 timestamps.
2. Collect negative/corporate-action disclosures, dilution and sector-wide news; avoid positive-PR-only selection bias. Check 2026 reverse-split authorizations and actual effective dates.
3. Score catalyst novelty, materiality and sentiment independently, preserving raw sources and prompt/model version; never use subsequent price moves as labeling input.
4. Join only information available by completed-day cutoff; exclude or mark ambiguous timestamp rows, and compare price+volume baseline against price+volume+news on same eligible sessions.
5. Use embargoed chronological holdout, non-overlapping 1/3/5-session trades, matched controls, friction and uncertainty. No live trading until evidence and operational validation.

Source audit is not a backtest, CI result or Windows activation.
