# Use case scenarios

Every score and quote below is a real response from the live app, not an illustration.
Reproduce any of them at https://chennai-terra-risk.vercel.app

---

## 1. NRI buyer screening a plot she cannot visit

**Priya is in Dubai.** A broker has offered her a plot in Velachery, Chennai. She has
never heard of a "revenue firka" and does not know the ward number.

She types **"velacheri bus stop"** — misspelt, and a landmark rather than an address.

| | |
|---|---|
| Resolves to | Velachery, Chennai 600042 |
| Corporation record | **Ward 177, Zone 13 Adyar** |
| Grade | **Low risk** (23/100), medium confidence |
| Flags | Perungudi Dumpyard 3.3 km away, outer edge of its leachate buffer |
| | No groundwater survey covers Velachery specifically |

**What she gets that she could not get before:** the ward and zone to quote on the
patta and the CMWSSB connection, and a named reason to ask the broker a follow-up
question. **What the tool refuses to do:** call the groundwater reading a measurement.
It says CGWB's regional finding was used and tells her to ask neighbours what depth
their borewell runs at.

---

## 2. Buyer who dodges a genuinely bad plot

**Same buyer, second option:** a cheaper plot in Manali, north Chennai.

| | |
|---|---|
| Corporation record | Ward 18, Zone 2 Manali |
| Grade | **High risk** (68/100) |
| Flood | "The corporation maps this plot inside a 'High' inundation zone." |
| Contamination | "This plot sits inside Manali Industrial Area, which CPCB classes as critically polluted. Test any borewell here for heavy metals in a laboratory before you drink, cook or bathe with it." |

The price difference now has an explanation. This is the case the tool exists for, and
it is the one Chennai's graded flood survey makes possible.

---

## 3. Agent pre-screening a listing in a city with thinner data

**Ramesh lists flats in Bengaluru.** He checks a Bellandur property.

| | |
|---|---|
| Corporation record | Ward 106 Marathahalli |
| Grade | **Low risk** (18/100), capped: no flood survey |
| Why not A | "No graded flood survey is published for Bengaluru. That is a statement about the data, not about the plot." |
| Scarcity | "Borewells around this plot run to a median of **18.5 m**. Expect to drill deep and still buy tanker water." |

Two things worth noticing. The scarcity line is the strongest evidence on the page —
Bengaluru publishes 1,114 measured borewell depths, better data than Chennai has. And
the reading is capped: Bengaluru has no graded flood survey, so the tool will not certify
any plot there as resilient, however good the terrain looks.

**Ramesh should not tell a client "this is low risk."** He should say the water table
runs 18.5 m deep and nobody has surveyed flooding here.

---

## 4. Buyer in a city with almost no open data

**Kurla, Mumbai.**

| | |
|---|---|
| Corporation record | Ward L |
| Grade | **Low risk** (19/100), capped: limited data |
| Not scored | water scarcity |
| Flood | "No graded flood survey is published for Mumbai. This score comes from terrain, mapped water and drains." |

A low number in Mumbai means *we could not find much*, not *this is safe*, and the
interface says so three times over: a "Terrain only" badge, a grade ceiling, and a
"not scored" panel where scarcity would be. Mumbai floods badly and the tool does not
have the data to tell you where. Treat it as a prompt to commission a local survey.

---

## 5. Developer land-banking across a shortlist

**A developer is comparing parcels.** Today this is one lookup at a time; the honest
limitation is that grades are **not comparable across cities of different depth**. A B
in Chennai is backed by 7,453 graded inundation polygons. A B in Ahmedabad is backed by
terrain and OpenStreetMap. That is what the depth badge on every score is for.

Within a single city the comparison is sound, which is where the value is today. Bulk
CSV scoring is the feature that would serve this properly, and it is not built yet.

---

## 6. Someone searching the way people actually speak

All of these resolve correctly, in the selected city:

| Typed | Resolves to |
|---|---|
| `velacheri` (misspelt) | Velachery, Chennai |
| `medavakam` (misspelt) | Medavakkam |
| `near phoenix mall` | Phoenix Mall, Velachery |
| `omr thoraipakkam` | Old Mahabalipuram Road |
| `ecr` | East Coast Road |
| `anna nagar 2nd avenue` | the street itself |
| `bandra station` (Mumbai) | Bandra Station |
| `kukatpally` (Hyderabad) | Kukatpally |
| `salt lake` (Kolkata) | Salt Lake |

Two behaviours worth knowing. Where a landmark does not exist in OpenStreetMap, the
tool offers the **area** rather than something 4 km away: "velacheri bus stop" returns
Velachery itself. And searching is scoped to the selected city, so "MG Road" finds the
right one.

---

## 7. Plot just outside the corporation line

**Perumbakkam, Chennai** returns *"Outside GCC limits, 370 m from Zone 14 Perungudi"*,
with a note that a panchayat or neighbouring municipality governs it — so building
approvals, property tax and water connections run through a different office. Naming
what it borders is more use than a flat "outside".

**Salt Lake, Kolkata** likewise reports outside KMC, which is correct: Salt Lake is
Bidhannagar, a separate municipality.

---

## 8. Delhi and Ahmedabad, where no ward file exists

MCD and AMC publish no open ward boundaries. Rather than guess, the tool shows the
nearest OpenStreetMap locality and flags it:

> *DIZ Area* — "MCD / NDMC does not publish ward boundaries. This locality is from
> OpenStreetMap, for orientation only — it is not the ward number used on forms."

Connaught Place correctly resolves to DIZ Area; Dwarka to Sector 11. An earlier build
ran a containment test against those same OSM polygons and reported "outside MCD
limits" in the middle of Connaught Place, because OSM admin levels there are villages
and colonies that do not tile the city.

---

## What the tool will not do

- Score a plot against the wrong city. Chennai coordinates sent with `city=mumbai`
  return 422 naming the city the point is actually in.
- Score a dimension it has no evidence for. It drops it and renormalises the weights,
  rather than scoring zero and flattering a city that publishes less.
- Average a severe finding away. Manali's contamination alone holds the whole grade
  down, because good drainage does not make groundwater safe to drink.
- Call a plot resilient where nobody has surveyed. The grade is capped at B in every
  city without a graded flood survey.
