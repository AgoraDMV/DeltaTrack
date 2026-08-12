# Re-adjudication packet — Study 1 observations that no longer reproduce

**Do not look for the previous answer before ruling.** Three observations from the 2026-07 similarity answer key describe provisions the parser no longer represents the way it did when they were ruled. The legislation has not changed: the source XML is byte-identical to the file that entered git, and the parser as it stood on the labelling date still reproduces the old representation from today's bytes. What changed is how the engine divides that legislation into provisions, so the *unit* you originally ruled on is not a unit the pipeline now produces.

You are therefore being asked the same legislative question over the current unit, not asked to confirm or overturn anything. Your earlier judgment stands as a judgment about the earlier unit; it is preserved separately and is not being edited.

This packet deliberately withholds every similarity score, the current matcher's decision, the original verdict, and any indication of which approach a given answer would favour. Where the old provision's original text no longer exists, the packet does **not** guess which current provision replaced it — that guess would have to come from one of the similarity signals under evaluation. It lists every provision the parser now emits at that structural location and asks you to pick, which is exhaustive within that location.

**For each item, answer:**

1. Which of the old-version options (if any) is the counterpart of the new-version provision? `option N` / `none of them`.
2. Given that choice: are these the **same provision carried across versions**, or **two different provisions**? `same` / `different` / `uncertain`.
3. One sentence of reasoning, in terms of the legislation.
4. If your answer is `uncertain`, say what additional context would settle it.

---

## Item 1 — `contested-2-corps-110`

Bill **115-hr-5895**, comparing version `4_engrossed-amendment-senate` (old) with `5_enrolled-bill` (new).

### New-version provision

- structural location: `Division A: Energy and Water Development and Related Agencies Appropriations Act, 2019 > TITLE I—Corps of engineers—civil > General provisions—corps of engineers—civil > sec. 110`
- header: (no header)
- length: 229 characters

```
None of the funds made available by this Act or any other Act may be used to reorganize or to transfer the Civil Works functions or authority of the Corps of Engineers or the Secretary of the Army to another department or agency.
```

### Old-version candidates at the same structural location

The parser emits **1** provision(s) at `corps of engineers—civil > general provisions—corps of engineers—civil > sec. 110` in `4_engrossed-amendment-senate`. All of them are shown, in document order.

**THE OLD-VERSION PROVISION**

- structural location: `Division A: Energy and Water Development and Related Agencies Appropriations Act, 2019 > TITLE I—Corps of engineers—civil > General provisions—corps of engineers—civil > sec. 110`
- header: (no header)
- length: 563 characters

```
None of the funds made available by this title may be used by the Corps of Engineers to conduct a release or discharge of water from Lake Okeechobee to the Caloosahatchee Estuary or the Indian River Lagoon unless the discharge or release—(1)is conducted in pulses to minimize downstream impacts from reduced water quality and harmful algal blooms to local communities and wildlife habitat; or(2)is necessary—(A)to protect the integrity of the Herbert Hoover Dike; and(B)to minimize threats to lives and human health in the communities surrounding Lake Okeechobee.
```

**Your ruling:**

- counterpart: 
- same / different / uncertain: 
- because: 

---

## Item 2 — `anchor-diff-sec252`

Bill **115-hr-5895**, comparing version `4_engrossed-amendment-senate` (old) with `5_enrolled-bill` (new).

### New-version provision

- structural location: `Division C: Military Construction, Veterans Affairs, and Related Agencies Appropriations Act, 2019 > TITLE II—Department of veterans affairs > Administrative provisions > sec. 252`
- header: (no header)
- length: 502 characters

```
None of the funds appropriated or otherwise made available by this Act to the Veterans Health Administration may be used in fiscal year 2019 to convert any program which received specific purpose funds in fiscal year 2018 to a general purpose funded program unless the Secretary of Veterans Affairs submits written notification of any such proposal to the Committees on Appropriations of both Houses of Congress at least thirty days prior to any such action and an approval is issued by the Committees.
```

### Old-version candidates at the same structural location

The parser emits **1** provision(s) at `department of veterans affairs > administrative provisions > sec. 252` in `4_engrossed-amendment-senate`. All of them are shown, in document order.

**THE OLD-VERSION PROVISION**

- structural location: `Division C: MILITARY CONSTRUCTION, VETERANS AFFAIRS, AND RELATED AGENCIES APPROPRIATIONS ACT, 2019 > TITLE II—Department of veterans affairs > Administrative provisions > sec. 252`
- header: (no header)
- length: 766 characters

```
Not later than 90 days after the date of the enactment of this Act, the Secretary of Veterans Affairs shall submit to the Committee on Appropriations and the Committee on Veterans’ Affairs of the Senate and the Committee on Appropriations and the Committee on Veterans’ Affairs of the House of Representatives a report that contains—(1)the number of coordinators of caregiver support services under the program of support services for caregivers of veterans under section 1720G(b) of title 38, United States Code, at each medical center of the Department of Veterans Affairs;(2)the number of staff assigned to appeals for such program at each such medical center; and(3)a determination by the Secretary of the appropriate staff-to-participant ratio for such program.
```

**Your ruling:**

- counterpart: 
- same / different / uncertain: 
- because: 

---

## Item 3 — `extreme-alien-snap-10012`

Bill **119-hr-1**, comparing version `1_reported-in-house` (old) with `2_engrossed-in-house` (new).

### New-version provision

- structural location: `TITLE I—Committee on Agriculture > Nutrition > sec. 10012`
- header: Alien SNAP eligibility
- length: 2242 characters

```
Section 6(f) of the Food and Nutrition Act of 2008 (7 U.S.C. 2015(f)) is amended to read as follows:(f)No individual who is a member of a household otherwise eligible to participate in the supplemental nutrition assistance program under this section shall be eligible to participate in the supplemental nutrition assistance program as a member of that or any other household unless he or she is—(1)a resident of the United States; and(2)either—(A)a citizen or national of the United States;(B)an alien lawfully admitted for permanent residence as an immigrant as defined by sections 101(a)(15) and 101(a)(20) of the Immigration and Nationality Act, excluding, among others, alien visitors, tourists, diplomats, and students who enter the United States temporarily with no intention of abandoning their residence in a foreign country;(C)an alien who is a citizen or national of the Republic of Cuba and who—(i)is the beneficiary of an approved petition under section 203(a) of the Immigration and Nationality Act;(ii)meets all eligibility requirements for an immigrant visa but for whom such a visa is not immediately available;(iii)is not otherwise inadmissible under section 212(a) of such Act; and(iv)is physically present in the United States pursuant to a grant of parole in furtherance of the commitment of the United States to the minimum level of annual legal migration of Cuban nationals to the United States specified in the U.S.-Cuba Joint Communiqué on Migration, done at New York September 9, 1994, and reaffirmed in the Cuba-United States: Joint Statement on Normalization of Migration, Building on the Agreement of September 9, 1994, done at New York May 2, 1995; or(D)an individual who lawfully resides in the United States in accordance with a Compact of Free Association referred to in section 402(b)(2)(G) of the Personal Responsibility and Work Opportunity Reconciliation Act of 1996. The income (less, at State option, a pro rata share) and financial resources of the individual rendered ineligible to participate in the supplemental nutrition assistance program under this subsection shall be considered in determining the eligibility and the value of the allotment of the household of which such individual is a member..
```

### Old-version candidates at the same structural location

The parser emits **2** provision(s) at `committee on agriculture > nutrition > sec. 10012` in `1_reported-in-house`. All of them are shown, in document order.

**OPTION 1 of 2**

- structural location: `TITLE I—Committee on Agriculture > Nutrition > sec. 10012`
- header: Alien SNAP eligibility
- length: 1443 characters

```
Section 6(f) of the Food and Nutrition Act of 2008 (7 U.S.C. 2015(f)) is amended—(1)in the 1st sentence—(A)by striking No and inserting In addition to the limitations on eligibility in the Personal Responsibility and Work Opportunity Reconciliation Act of 1996, no; and(B)by striking ; or(C) an alien who entered the United States prior to June 30, 1948, or such subsequent date as is enacted by law, has continuously maintained his or her residence in the United States since then, and is not ineligible for citizenship, but who is deemed to be lawfully admitted for permanent residence as a result of an exercise of discretion by the Attorney General pursuant to section 249 of the Immigration and Nationality Act (8 U.S.C. 1259); or(D) an alien who has qualified for conditional entry pursuant to sections 207 and 208 of the Immigration and Nationality Act (8 U.S.C. 1157 and 1158); or(E) an alien who is lawfully present in the United States as a result of an exercise of discretion by the Attorney General for emergent reasons or reasons deemed strictly in the public interest pursuant to section 212(d)(5) of the Immigration and Nationality Act (8 U.S.C. 1182(d)(5)); or(F) an alien within the United States as to whom the Attorney General has withheld deportation pursuant to section 243 of the Immigration and Nationality Act (8 U.S.C. 1253(h)); and(2)in the 2d sentence by striking clauses(B) through(F) and inserting paragraph(2)(B).
```

**OPTION 2 of 2**

- structural location: `TITLE I—Committee on Agriculture > Nutrition > sec. 10012`
- header: Emergency food assistance
- length: 133 characters

```
Section 203D(d)(5) of the Emergency Food Assistance Act of 1983 (7 U.S.C. 7507(d)(5)) is amended by striking 2024 and inserting 2031.
```

**Your ruling:**

- counterpart: 
- same / different / uncertain: 
- because: 

---
