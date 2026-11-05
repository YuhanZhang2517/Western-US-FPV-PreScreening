# Known limitations

These are factual statements about the data and methods. **Source-data limitations** come from inputs. **Method limitations** come from choices in the analysis. No coding error is known in the calculations listed here. The regional totals are theoretical: they assume a uniform 10% coverage of every record, and they are not an estimate of deployable capacity.

## Source-data limitations

**Flatiron Dam area (corrected).** NID lists 381,500 acres (1,543.9 km²) with 1,136 acre-ft of storage, and its own drainage area is smaller than that surface. The authors replaced this with 45 acres, the Reclamation 2012 survey value (Northern Water gives 47 acres; the difference is about 0.0002 TWh/yr). The correction removed 29.30 TWh/yr, 15.44 GW and 0.19 km³/yr. The source value stays in `surfaceArea_source_acres` and in the pre-correction files. See `VERSION_HISTORY.md`.

**18 remaining area-quality flags.** Records with area ≥ 1 km² and implied mean depth < 1 ft carry `area_review_flag = True`. Originally 19 records; Flatiron left the set once corrected. The other 18 keep their NID areas and total 361 km², 7.23 TWh/yr, 3.61 GW and 0.052 km³/yr. The largest are Encino Det Dam 083 (218 km²) and Alamos Detention Dam (57 km²). These are screening flags with no independent replacement value, and some may be errors of the same kind as Flatiron.

**Repeated reservoir area.** NID gives dikes and saddle dams their own records, often repeating the reservoir's area. 122 Dam IDs repeat on 319 records. Most remain in the 8,516 records because the review matches exact names. This is the largest open issue in the regional totals. Removing the 234 records that NID marks as associated structures would lower the corrected totals by 67.8 TWh/yr (13.6%) and 0.53 km³/yr (15.1%), to about 429 TWh/yr and 2.99 km³/yr. That filter has not been applied, so 497 TWh/yr and 3.52 km³/yr should be read as including this repeated area. "8,516" is a record count and should not be read as a verified count of distinct water bodies.

**Other inventory points.** 3,665 records with missing area and 177 with zero area were dropped. Missing area does not prove a site is dry. Some retained records are tailings, leachate or detention facilities.

**Copied attributes.** The 13 natural lakes, contributing about 122.8 TWh/yr (24.7% of the total), use attributes from curated files because polygons are unavailable. The Great Salt Lake evaporation value (0.8597 m/yr) cannot be traced to its source; raw ERA5 cells over the lake read about zero.

**State labels.** Four candidates have labels that disagree with their coordinates: Honey Lake, Yellowstone Lake, Washoe Lake and Heron Reservoir. Correcting them would shift 112 of 138 ranks. Several border reservoirs also have one assigned state.

## Method limitations

**Missing HAB observations.** The HAB value is missing for 121 of the 138 candidates, and these are coded as "no bloom" (worst score). All 17 observed sites exceed the threshold, so there are no observed absences. The Private and Utility files have no HAB values at all, and at 5 coordinates one file has a value while another does not. Treating missing values as neutral or removing HAB changes the Top 5, moves Great Salt Lake from rank 61 to 86–106, and removes the ownership difference in Table 3.

**Evaporation.** The figure assumes 100% suppression of ERA5 potential evaporation under the covered area. It is a theoretical maximum, not realistic net water savings. Published reductions range from 5% to 90%.

**Capacity factor.** It is a theoretical value proportional to irradiation. It contains no temperature, inverter, soiling or availability effects.

**Decile rescaling.** Rounding collapsed bins half-up instead of half-even reorders ranks 3–5 and moves class counts at seed 42. Top-30 membership does not change.

**Hydropower distance rule.** The zero-distance rule is applied to the 138 candidates but not to the regional dataset, where 650 hydropower records keep positive distances.

**Consistency.** The aggregate matrix has CR = 0.001. Individually, 20 of the 100 simulated matrices and one real expert exceed CR 0.10. All were retained.

**Table 3.** Groups are built from the same criteria being tested, so its p-values are descriptive. The ownership result depends on one borderline site, Cutler.

**Candidates outside the inventory.** 8 of the 138 candidates, including Lake Pleasant, are not in the regional inventory.

## Provenance gaps

Manual curation of the Top-30 files, the CyAN query, NHD lake selection and matrix generation cannot be reproduced from available materials. See `DATA_SOURCES.md`.
