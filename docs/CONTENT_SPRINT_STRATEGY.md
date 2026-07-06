# Content Sprint — 5 Pillar/Cluster Sets

**Status:** playbook + prompts, ready for the content team.

The audit's #6 recommendation is a content sprint to unlock organic
commercial traffic. Writing 25-30 quality SEO articles is not
something an agent should ship in one go — it produces generic AI slop
that ranks nowhere. What this document delivers is the *skeleton*: five
pillar topics with proven commercial intent, three cluster articles
under each, exact target keywords, and copy-paste-ready prompts for
your existing `/api/blog/generate` endpoint.

**Recommended cadence:** 1 pillar + 3 clusters per week = 5 weeks total.
Each pillar is 2000-2500 words, each cluster is 800-1200 words. All
articles interlink: pillar → clusters (contextual anchors), clusters →
pillar (bottom-of-article "Read the full guide" CTA), all articles →
2-3 live jobs from `/api/public/jobs/list?location=…`.

---

## Pillar 1 — "Manufacturing Recruitment Agency in Pune"

**Target:** high commercial-intent city query. Volume: ~880/mo (Ahrefs India, 2025).
**URL:** `/industrial-hiring-insights/manufacturing-recruitment-agency-pune`

### Pillar outline
- Why Pune's manufacturing corridor (Chakan, Talegaon, Ranjangaon, Hinjewadi)
  needs specialist recruitment
- 5 hiring pain points unique to Pune plants (talent poaching from IT sector,
  Marathi-language shopfloor requirement, Automotive OEM concentration,
  compensation benchmarks vs Chennai/Bengaluru, monsoon-season absentee rate)
- How VHC's Pune bench works: pre-vetted candidates, 72-hour shortlist SLA,
  case study numbers (avg 14 days close, 22% CTC negotiation lift)
- What to look for in a manufacturing recruitment agency (checklist)
- Live openings in Pune (dynamic block pulling 5 jobs)
- FAQ (schema.org FAQPage) — 6 questions

### Cluster articles
1. **Plant Head jobs in Pune — salary benchmarks 2026** (transactional keyword)
2. **How Chakan MIDC plants are hiring shopfloor engineers** (informational)
3. **Automotive Tier-1 supplier hiring in Talegaon: 2026 outlook** (industry)

### Prompt template (paste into admin Blog Generator)
```
Topic: "Manufacturing Recruitment Agency in Pune — Complete Hiring Guide 2026"
Industry: Manufacturing / Automotive OEM
Region: Pune, India
Keywords: manufacturing recruitment agency pune, plant hiring pune,
          industrial recruitment pune, shopfloor engineer hiring pune,
          chakan MIDC recruitment, talegaon plant hiring
Blog type: employer
```

---

## Pillar 2 — "Plant Head Hiring in India — Salary, Skills, Sourcing"

**Target:** high-value senior role, high CPC. Volume: ~590/mo.
**URL:** `/industrial-hiring-insights/plant-head-hiring-india`

### Pillar outline
- What a modern Plant Head owns (P&L, OEE, safety, digital-manufacturing)
- Salary bands 2026 (₹65L-₹1.8Cr by industry, region, revenue tier)
- Where good Plant Head candidates come from (Tier-1 auto, pharma, FMCG)
- Interview scorecard (10 competencies + red flags)
- Retention data: why 40% churn in year one and how to prevent it
- Live Plant Head openings (dynamic block)
- FAQ

### Cluster articles
1. **Plant Head vs Operations Head — key differences** (informational)
2. **Building the succession pipeline: internal vs external Plant Head** (strategic)
3. **How much should you pay a Plant Head in India? 2026 salary guide** (transactional)

### Prompt
```
Topic: "Plant Head Hiring in India — 2026 Salary, Skills, and Sourcing Guide"
Industry: Manufacturing / Cross-industry
Region: India
Keywords: plant head hiring, plant head salary india, hire plant head,
          manufacturing leadership recruitment, operations head vs plant head
Blog type: employer
```

---

## Pillar 3 — "Executive Search for Auto Component Manufacturers"

**Target:** industry-specific, mid-competition. Volume: ~320/mo.
**URL:** `/industrial-hiring-insights/executive-search-auto-components`

### Pillar outline
- The 2026 auto-component leadership market (EV transition, tier consolidation)
- Roles in demand: VP Ops, Head R&D, CSO, EV Program Manager
- Why generalist recruiters miss the mark (technology depth, IATF-16949 vetting)
- VHC's auto-component desk: candidate mapping across Bharat FIH,
  Tata AutoComp, Bosch, Sona Comstar, Motherson tier network
- Case study: 3 recent placements (redact names, keep the numbers)
- Live openings (dynamic block)
- FAQ

### Cluster articles
1. **EV component hiring — the 5 roles nobody has enough of** (trend)
2. **IATF-16949 audit-ready hiring: what auditors actually check** (technical)
3. **Auto-component R&D head: skills, salary, sourcing** (role guide)

### Prompt
```
Topic: "Executive Search for Auto Component Manufacturers in India 2026"
Industry: Automotive / Auto Components
Region: India
Keywords: auto component recruitment, executive search automotive,
          EV component hiring, tier 1 supplier recruitment,
          automotive VP operations hiring
Blog type: employer
```

---

## Pillar 4 — "Hiring for Aerospace and Defence Manufacturing"

**Target:** growing sector (Make in India, IDEX), specialist. Volume: ~210/mo.
**URL:** `/industrial-hiring-insights/aerospace-defence-recruitment-india`

### Pillar outline
- The IDEX / Atmanirbhar Bharat manufacturing surge (Bengaluru, Hyderabad,
  Nagpur, Coimbatore clusters)
- Security-cleared talent: how to source without breaching MoD guidelines
- Skills gap: composites, avionics integration, MRO leadership
- Compensation delta vs commercial aviation & automotive
- VHC's aerospace desk: past placements, active mandates
- Live openings
- FAQ

### Cluster articles
1. **Aerospace machining leaders — where to find them in India** (sourcing)
2. **Defence electronics hiring 2026: skills the market lacks** (skills)
3. **MRO India hiring: the DGCA-approved talent squeeze** (transactional)

### Prompt
```
Topic: "Hiring Leadership for Aerospace and Defence Manufacturing in India 2026"
Industry: Aerospace / Defence
Region: India (Bengaluru, Hyderabad, Nagpur, Coimbatore)
Keywords: aerospace recruitment india, defence hiring india,
          MRO hiring, avionics engineer hiring, IDEX manufacturing hiring
Blog type: employer
```

---

## Pillar 5 — "Industrial Recruitment: Retained vs Contingent Search"

**Target:** decision-stage buyer content. Volume: ~450/mo.
**URL:** `/industrial-hiring-insights/retained-vs-contingent-recruitment`

### Pillar outline
- The two engagement models explained (fees, SLAs, exclusivity, replacement
  guarantees)
- When retained wins: C-suite, confidential searches, niche skill, tight timeline
- When contingent wins: volume roles, competitive pipelines, budget-constrained
- Hybrid models VHC offers (engaged retainer with success-fee tail)
- The math: total cost per successful hire under each model
- Buyer's checklist (12 questions to ask a recruitment agency)
- FAQ

### Cluster articles
1. **Recruitment agency fees in India 2026 — what's normal, what's high**
2. **How to write a search agreement that actually protects you**
3. **Contingent recruitment for factory floor roles: pros, cons, best practice**

### Prompt
```
Topic: "Retained vs Contingent Recruitment for Industrial Roles in India"
Industry: Cross-industry
Region: India
Keywords: retained search india, contingent recruitment fees india,
          recruitment agency comparison, executive search fees
Blog type: employer
```

---

## Workflow

For each pillar week:

1. **Monday:** Open admin `/admin/blog-engine` → "Generate new blog" → paste
   the prompt template above → generate. Review the draft; add specific
   VHC case-study numbers, quotes from your team, images.
2. **Tuesday/Wednesday:** Generate the 3 cluster articles the same way.
   Interlink: each cluster's intro paragraph should contain
   `Read the full guide: <link to pillar>`. The pillar's body should link
   to each cluster with a natural anchor.
3. **Thursday:** Publish the pillar (triggers IndexNow ping to
   Bing/Yandex + Article JSON-LD is now emitted from `SEOHead`).
4. **Friday:** Publish the 3 clusters back-to-back; each publish pings
   IndexNow again.
5. **Following Monday:** Google Search Console → URL Inspection → Request
   Indexing on all 4 URLs. Then move to the next pillar.

## Measurement

After 8 weeks, pull these numbers from Search Console:

- Impressions per pillar (target: 500-3000/mo per pillar by month 3)
- Average position (target: page 1 for pillar terms within 12 weeks)
- CTR (target: 3-8% for informational, 8-15% for transactional)

## Interlinking to live jobs

Add this snippet at the bottom of every pillar/cluster (put it in a
reusable component if you want):

```jsx
{/* Live openings block — pulls from /api/public/jobs/list */}
<LiveJobsBlock
  location={pillarLocation}
  industry={pillarIndustry}
  limit={5}
  heading={`Currently hiring for ${pillarIndustry} in ${pillarLocation}`}
/>
```

Rationale: this converts the SEO traffic. Without the live-jobs block,
you're building an SEO asset that sends the reader to the exit page.
With it, you're building a lead-generation asset.
