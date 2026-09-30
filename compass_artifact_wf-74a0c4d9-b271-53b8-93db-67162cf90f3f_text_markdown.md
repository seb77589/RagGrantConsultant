# Pan-European, English-Only Grant Consultant: Revised Feasibility and Analysis Report

## Short answer (in plain words)

Yes, the revised idea still makes sense, and your laptop can still run it. Putting European-level sources first actually makes the data work easier than the Romania-only version. Almost everything published at European level is in English, openly licensed and available in bulk or through official download services. The hard part has moved. Covering the national layer for every eligible country in English is where the effort now goes, because only a handful of countries publish their national calls and guides fully in English.

The honest trade-off: if you keep only documents that were originally written in English, you will cover European-level funding very well. You will cover national funding well in only about six to eight countries, including Ireland, Malta, Estonia, Finland, Denmark, Cyprus, Norway and Switzerland. For the large countries, such as Germany, France, Italy, Spain, Poland and Romania, you will only have the Commission's English descriptions of their programmes plus links to the national authorities.

Rough time: about 130–210 hours for a first version that fully serves your job-practice goal, and about 210–340 hours in total for the full "consultant for any European company" version. You will reach roughly 300,000 useful text sections without padding. Stay below about 500,000 sections so that the laptop remains comfortable.

---

## Complete analysis report

### Abbreviations used in this report (all defined here)

| Abbreviation | Meaning |
|---|---|
| CC BY 4.0 | Creative Commons Attribution 4.0 International licence |
| CC0 | Creative Commons Zero public-domain dedication |
| CORDIS | Community Research and Development Information Service (the Commission's research-project database) |
| CSV | Comma-separated values (a plain table file format) |
| HNSW | Hierarchical Navigable Small World (the graph index type used for vector search in pgvector) |
| LLDAP | Light Lightweight Directory Access Protocol server (the user directory in the job's login chain) |
| NACE | Statistical classification of economic activities in the European Community (sector codes) |
| NUTS | Nomenclature of Territorial Units for Statistics (the European region codes) |
| PDF | Portable Document Format |
| REST | Representational State Transfer (a common style of web programming interface) |
| SEDIA | Single Electronic Data Interchange Area\[1\] (the formal name of the Funding and Tenders Portal) |
| SPARQL | SPARQL Protocol and RDF Query Language, where RDF is Resource Description Framework (the query language of the Commission's CELLAR repository) |

Everything else is spelled out: "small and medium-sized enterprise", "graphics card", "European Union", and so on.

---

### Key findings

1. **European-level first is easier than Romania-first for data.** The European layer consists of EUR-Lex, the Funding and Tenders Portal, CORDIS, the Cohesion Open Data Platform, Kohesio, keep.eu for Interreg, the Recovery and Resilience Scoreboard, the Digital Innovation Hubs catalogue and the Eureka/Eurostars pages. All of it is in English, and most of it comes as structured data or bulk downloads under open terms. This removes the biggest pain of the Romanian version: guides that exist only in Romanian.
2. **"Any eligible country" makes the logic harder.** Eligibility now depends on country, region code, company size, sector code, state-aid category and programme association status. The regional aid ceilings alone differ for every region in 27 countries. This is the part that turns a document search tool into a consultant.
3. **English-origin national coverage is thin.** Full English national funding information exists in Ireland, Malta, Estonia, Finland, Denmark, Cyprus (English for information only), Norway (Research Council) and Switzerland. Partial English exists in Sweden, the Netherlands, Latvia, Austria and Innovation Norway. Coverage is very limited or absent in Lithuania and Germany's federal database. By money, the countries with full English national calls receive only a small share of the €512 billion of 2021–2027 cohesion funding.\[2\] My estimate is well under a tenth, so treat it as an estimate.
4. **Hidden trap: Kohesio's English is machine-translated.** Kohesio states that it uses "eTranslation, the machine translation tool designed by the European Commission, to translate automatically into English the operation / project titles and descriptions".\[3\]\[4\] So Kohesio text breaks your "100% English origin" rule, except for projects that were originally in English. Keep Kohesio's numbers, codes and regions in the core, and put its translated text in a clearly labelled optional tier.
5. **Corpus size:** about 190,000–420,000 on-topic English-origin sections, with a central estimate of about 320,000. CORDIS project records make up the largest share. The 300,000 target is reachable without padding. Adding Kohesio translations or all European Union legislation would push past 1–2 million sections, which is padding and should be avoided.
6. **Hardware conclusion unchanged.** The 4-bit Qwen3.5-9B plus bge-m3 plus bge-reranker-v2-m3 still fit in 16 gigabytes of graphics memory. At 300,000–500,000 sections, embedding, index building and search remain comfortable on this laptop. At 1,000,000 sections it still works, but embedding takes about a day and re-indexing becomes a planned event. Cap the core at about 500,000.
7. **Time:** Phase 1 takes about 130–210 hours. The earlier estimates were 100–160 hours for the Romanian minimal version and 75–120 hours for the generic version. Phase 2, the full consultant, takes about 210–340 hours cumulative, against 150–260 hours for the earlier Romanian full version. The job-practice core, about 75–120 hours, is unchanged.

---

### A. Does the revised idea make sense, and is it feasible?

**Yes, and it is a better fit for the freelance job.** The job asks for a question-answering system with sources over several hundred thousand sections, plus proof that search and answers are equivalent after migration. A pan-European English corpus gives you exactly that scale. It also comes from clean, stable, well-identified sources, and stable document identifiers are what make a before-and-after migration comparison credible.

**Easier than the Romanian version:**
- **One language.** There is no translation step and no mixed-language retrieval, and bge-m3 and the reranker work at their best on English.
- **Structured sources.** These include the Funding and Tenders search interface, which is a public REST service, and the CELLAR SPARQL endpoint for legislation. There are also monthly CORDIS bulk downloads and Kohesio country exports in CSV or spreadsheet format.\[3\]\[4\]\[5\]\[6\] The Cohesion Open Data Platform provides datasets. One example is the 2021–2027 programme-to-region lookup table, with about 16,100 rows, released as CC0 public domain.\[7\]
- **Clear reuse terms.** Most sources are covered by Commission Decision 2011/833/EU and CC BY 4.0.\[5\]\[8\]\[9\]

**Harder than the Romanian version:**
- **Eligibility logic across countries.** There are 27 member states, plus programme-specific associated countries, plus Eurostars' 37 member countries, each with its own national funding rules.\[10\]
- **National calls are mostly not in English.** You must accept link-outs instead of full content for most countries.
- **Keeping it current across many calendars.** Horizon Europe, Digital Europe, the European Innovation Council, Eurostars and dozens of national agencies all run their own deadlines. The Recovery and Resilience Facility "provides funds to Member States… until the end of 2026".\[11\] By now, late 2026, that layer is closing and mostly useful as history.
- **Programme period change.** The 2028–2034 budget and the successor to Horizon Europe are already being discussed. The Horizon Europe National Contact Point portal reported a September 2026 event on "the future role of National Contact Points… under FP10".\[12\] Design for versioned programme periods from day one.

**Net verdict:** feasible, sensible, and a better job-practice vehicle than the Romanian version. The consultant ambition must be phased, because the multi-country eligibility engine is the expensive part.

---

### B. English-only data across Europe: what exists

#### B1. Pan-European sources (all English)

| Source | What it gives | Language | Licence / reuse | Approximate size |
|---|---|---|---|---|
| **EUR-Lex** (eur-lex.europa.eu; bulk via CELLAR SPARQL and REST, data dump with EU Login) | Funding regulations, state-aid rules, small and medium-sized enterprise definition, national recovery plan approval decisions | English is an authentic language for all acts | Decision 2011/833/EU; editorial content CC BY 4.0 | Relevant subset: a few hundred acts |
| **Funding and Tenders Portal** (ec.europa.eu/info/funding-tenders; search service at api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA) | All calls and topics with status (forthcoming, open, closed), deadlines, work programmes, guides, National Contact Point lists\[13\] | English | Commission default CC BY 4.0 | Thousands of topics across programmes (my estimate: 8,000–12,000 for 2021–2027) |
| **National Contact Points list** (Funding and Tenders Portal, "support/ncp") | Country-specific advisers per programme; the portal notes the list is "currently available for the Horizon programme"\[14\] | English | Contains personal names and contacts: store organisation-level data only | Several thousand entries |
| **CORDIS** (cordis.europa.eu; data.europa.eu datasets) | Funded projects, participants, objectives, results; about 19,495 Horizon Europe and 35,389 Horizon 2020 projects (third-party count)\[15\] | English | Decision 2011/833/EU / CC BY 4.0; datasets refreshed monthly\[5\] | Horizon Europe dataset about 33 megabytes; roughly 55,000 projects\[5\]\[15\] |
| **Kohesio** (kohesio.eu) | Cohesion-policy projects and beneficiaries, 2014–2020 and 2021–2027\[3\]\[4\] | Original language plus **machine-translated** English\[4\] | Commission legal notice | Kohesio's About page says it "currently contains more than 1.5 million projects and approximately 500,000 beneficiaries"; a newer figure from the Organisation for Economic Co-operation and Development, citing the Commission (2025), is "over 640 000 beneficiaries have implemented more than 1.8 million projects… since 2014" |
| **Cohesion Open Data Platform** (cohesiondata.ec.europa.eu) | Planned and paid amounts per country, programme, theme and fund;\[16\] region lookups; €512,106,686,843 planned for 2021–2027\[2\]\[7\] | English | Varies by dataset; the region lookup is CC0\[7\] | Hundreds of programmes; small text, rich numbers\[2\] |
| **Partnership Agreements 2021–2027** (commission.europa.eu collection) | Each member state's strategy and programme list\[17\] | Published per country, often in the national language only; Malta's and Ireland's are in English\[18\]\[19\] | CC BY 4.0 | 27 documents\[20\] |
| **Inforegio programme pages** (ec.europa.eu/regional_policy) | English summaries of each national and regional programme | English | CC BY 4.0 | About 400 programmes |
| **Recovery and Resilience Scoreboard and country pages** (ec.europa.eu/economy_finance/recovery-and-resilience-scoreboard; reforms-investments country pages) | Per-country plans, milestones, payments, the 100 largest recipients\[21\]\[22\] | English (dataset metadata: "Languages: English")\[23\] | Commission open data | 27 country pages plus the approval decisions in EUR-Lex |
| **Regional aid maps 2022–2027** (Commission press releases and decisions) | Eligible regions and maximum aid intensities per region; small firms get +20 percentage points and medium firms +10 for initial investments up to €50 million\[24\]\[25\] | English press releases; decisions in the authentic language | CC BY 4.0 | 27 maps plus amendments |
| **Access to European Union Finance** (youreurope.europa.eu, financial intermediaries) | "Over 1,000" banks and funds offering European Union-backed loans, guarantees and venture capital, filterable by country (for example 309 in France, 214 in the Netherlands, 70 in Ireland)\[26\]\[27\]\[28\]\[29\] | English | Commission legal notice | Over 1,000 entries |
| **European Investment Fund intermediaries** (eif.org, "where to access finance") | Intermediaries by country, including candidate and associated countries\[30\] | English | European Investment Fund terms: check before reuse | Hundreds of entries |
| **Enterprise Europe Network** (een.ec.europa.eu) | Local advisers and a partnering database; Innosuisse describes the Network as "more than 600 member organisation in over 60 countries", while the Network's own September 2024 notice cites "experts from over 500 organizations worldwide" and "more than 3,000 experts" | English | Profiles are anonymised third-party offers: **use for link-out only**\[31\] | Thousands of profiles |
| **European Digital Innovation Hubs catalogue** (european-digital-innovation-hubs.ec.europa.eu) | Hub descriptions, services, country; "Download Data" available; the hubs portal says "Since May 2025, 168 hubs funded under the Digital Europe Programme have formed part of the EDIH Network", and the Commission's digital strategy site adds that "A total of 102 EDIHs… will also receive the STEP Seal" (the German network page on the same portal cites 255 hubs Europe-wide) | English | Commission legal notice; **contains named contact persons, e-mails, phones: strip**\[32\] | About 168 Digital Europe-funded hubs, plus Seal of Excellence hubs |
| **Eureka / Eurostars** (eurekanetwork.org) | Per-country funding rules on each call page (for example Germany up to €500,000 for all German partners; Iceland up to 54 million króna); Call 11 deadline September 2026, Call 12 deadline March 2027\[33\]\[34\]\[35\] | English | Eureka site terms: check; link and quote briefly | 37 countries × each call |
| **keep.eu** (Interreg projects) | 32,381 Interreg projects since 2000 (88% of all), 63,907 project documents for 2014–2020, 390 programmes; programming interface since November 2024\[36\]\[37\] | Mostly English | Run by the Interact programme: licence not confirmed, check\[38\] | About 32,000 projects |
| **European Innovation Council, Digital Europe, Connecting Europe Facility Digital, Single Market Programme, InvestEU, LIFE** | Programme pages and calls, all served through the Funding and Tenders Portal and programme sites\[13\] | English | CC BY 4.0 | Included in Funding and Tenders topics |
| **EIT Digital** (European Institute of Innovation and Technology) | Venture and accelerator calls | English | Own terms | Small |
| **Erasmus+** | Mostly education; relevant to companies only for skills alliances | English | CC BY 4.0 | Include only the company-relevant actions |

#### B2. National agencies: English coverage (member states and associated countries)

| Country | Agency | English coverage | Evidence |
|---|---|---|---|
| Ireland | Enterprise Ireland (enterprise-ireland.com) | **Full** | English is the working language; for example "Call 8 will open on 1 October 2026… until 31 January 2027"\[39\] |
| Malta | fondi.eu, Servizzi Ewropej f'Malta (sem.gov.mt) | **Full** | Calls, guidance notes and deadlines in English, for example "Digitalise your Business – Guidance Notes 2024"\[40\]\[41\] |
| Estonia | Estonian Business and Innovation Agency (eis.ee/en) | **Full for grant pages** | "The application for the grant is open from 12.01.2026 at 9:00 to 15.12.2026 at 16:00" (cybersecurity grant, co-funded by Digital Europe)\[42\] |
| Finland | Business Finland (businessfinland.fi/en) | **Full** | English instructions and forms for applying\[43\]\[44\] |
| Denmark | Innovation Fund Denmark (innovationsfonden.dk/en) | **Full** | "You must write your application material for both phases in English."\[45\]\[46\] |
| Cyprus | Research and Innovation Foundation (research.org.cy/en) | **Full, with a caveat** | "The English version of the Call… is provided for information purposes only."\[47\] |
| Norway | Research Council of Norway (forskningsradet.no/en) | **Full** | "The application and all attachments must be written in Norwegian or English."\[48\] |
| Switzerland | Innosuisse (innosuisse.admin.ch/en) | **Full** | Applications accepted in English\[49\]\[50\] |
| Sweden | Vinnova (vinnova.se/en) | **Partial–high** | Calls in English, but the "guide to eligible costs" is "only in Swedish"\[51\] |
| Norway | Innovation Norway (en.innovasjonnorge.no) | **Partial** | Some grants in English; events "in Norwegian only"\[52\] |
| Netherlands | Netherlands Enterprise Agency (english.rvo.nl) | **Partial** | Mainly international schemes in English; legal texts in Dutch\[53\] |
| Latvia | Investment and Development Agency of Latvia (liaa.business.gov.lv/en) | **Partial** | English summaries and dates, with some untranslated Latvian headings\[54\]\[55\] |
| Austria | Austrian Research Promotion Agency (ffg.at/en) | **Partial** | Some calls "only available in German"\[56\] |
| Lithuania | Innovation Agency Lithuania | **Limited** | English "about" pages;\[57\] call listings appear Lithuanian-only (not fully confirmed) |
| Germany | Federal funding database (foerderdatenbank.de) | **None** | German only\[58\]\[59\] |
| Romania, and most others such as France, Italy, Spain and Poland | National managing authorities | **None or short summaries** | Romanian guides are Romanian-only; oportunitati-ue.gov.ro has short English summaries |

#### B3. What is lost by going English-only, and mitigation

**Lost:**
- Full national and regional call texts, applicant guides, national eligibility annexes and national state-aid scheme texts for about 20 of 27 member states.
- National-language official versions of Partnership Agreements.
- Most regional programme calls, the most frequent kind of grant for small digital projects.
- Kohesio's original-language descriptions.
- National de minimis registers and national-only schemes that have no European money in them.

**Still covered in English:**
- All directly managed European programmes, including Horizon Europe, Digital Europe, the European Innovation Council, Connecting Europe Facility Digital, the Single Market Programme, LIFE and Interreg calls. For a technology company, these are the grants open in *any* eligible country.
- All European legal framework texts.
- All recovery plan approval decisions and their annexes, which are official English texts in EUR-Lex.
- Commission programme summaries for every country.
- Regional aid maps, financial intermediaries, innovation hubs, Eurostars national rules.
- Full national calls for the 6–8 English-publishing countries.

**Mitigation, as you proposed, confirmed as workable:**
1. **Commission-level English descriptions of national programmes.** These are Inforegio programme pages, Cohesion Open Data figures, recovery plan approval decisions in EUR-Lex, the English Partnership Agreements where they exist, and regional aid map press releases.
2. **Link-out registry.** For each country and programme, store the managing authority, the national contact point, the innovation hub and the Enterprise Europe Network office as structured records with official links. The answer then says "the national call is published in [language] at [link]".
3. **Optional machine-translation tier (later phase).** This covers Kohesio's English fields and translated national calls. Keep it in a separate table and a separate index partition, labelled "machine translation, not an official text" in every answer. Exclude it from the "100% English origin" core and from the migration-equivalence proof.

---

### C. Corpus size for the revised scope

Assumptions: sections of 300–500 words, English-origin only, restricted to company-relevant digital, information-technology and innovation funding. The ranges are my estimates, built from the source counts above.

| Source block | Basis | Estimated sections (low–high) | Central |
|---|---|---|---|
| Relevant European legislation, consolidated (Horizon Europe, Digital Europe, Common Provisions, Regional Development Fund, Recovery Facility, InvestEU, Connecting Europe, Single Market Programme, Interreg, Financial Regulation, General Block Exemption Regulation, de minimis 2023/2831, small and medium-sized enterprise Recommendation 2003/361, regional aid guidelines, key digital laws) | 150–400 acts | 8,000–20,000 | 14,000 |
| Recovery plan approval decisions and annexes (27 countries, English in EUR-Lex) | Hundreds of pages each | 10,000–30,000 | 20,000 |
| Funding and Tenders topics and calls (Horizon Europe, Digital Europe, European Innovation Council, Connecting Europe Digital, Single Market Programme, InvestEU, LIFE, Interreg-related) | 8,000–12,000 topics × 2–5 sections | 20,000–50,000 | 35,000 |
| Work programmes (all years, all relevant programmes) | 15,000–20,000 pages | 20,000–40,000 | 30,000 |
| Programme guides, model grant agreement, online manual, evaluation rules | Several thousand pages | 3,000–6,000 | 4,500 |
| CORDIS project records (about 55,000 projects: objectives plus metadata) | 1–2 sections each | 55,000–110,000 | 80,000 |
| CORDIS report summaries and results | Where available | 40,000–100,000 | 70,000 |
| keep.eu Interreg projects and programmes | About 32,000 projects plus 390 programmes\[37\] | 25,000–50,000 | 40,000 |
| Commission programme descriptions for all countries (Inforegio, Partnership Agreements in English, regional aid maps) | About 400 programmes plus 27 maps | 2,000–5,000 | 3,500 |
| Digital Innovation Hubs catalogue | About 168 Digital Europe-funded hubs (hubs portal, since May 2025) plus Seal of Excellence hubs | 500–1,500 | 1,000 |
| Eureka / Eurostars country rules | 37 countries × calls | 500–1,500 | 1,000 |
| Access to Finance and European Investment Fund intermediaries | Over 1,000 entries | 1,000–2,500 | 1,500 |
| Enterprise Europe Network service pages (not partner profiles) | Small | 200–500 | 300 |
| National English sources (Ireland, Malta, Estonia, Finland, Denmark, Cyprus, Norway, Switzerland; partial Sweden, Netherlands, Latvia, Austria) | Calls, guides, scheme rules | 5,000–25,000 | 15,000 |
| **Total, English-origin core** | | **about 190,000–440,000** | **about 316,000** |
| *Optional: Kohesio machine-translated English* | 1.5–1.8 million projects (Kohesio About page: "more than 1.5 million"; Organisation for Economic Co-operation and Development citing the Commission, 2025: "more than 1.8 million projects") | *+1,500,000–2,000,000* | *not in core* |
| *Optional: all European Union legislation in English* | Mostly off-topic | *+300,000 or more* | *padding, avoid* |

**Answer:** yes, the core reaches about 300,000 sections without padding. The two biggest honest contributors are CORDIS records and the work programmes. A consultant should know what got funded before, which is why CORDIS records count. If you want to stay safely above 300,000 at the low end, add filtered Kohesio *structured* records, such as amounts, regions, intervention categories and beneficiary type. Generate a short English sentence template from these fields rather than using the translated description. That text is then produced by your own code from official data, which is honest and keeps the English-origin rule.

---

### D. Design implications of a pan-European tool

| Design element | What it means | Job-practice relevant? |
|---|---|---|
| Country and region (NUTS code) as first-class metadata on every section | Filter and boost by the user's country or region; use the Cohesion Open Data programme-to-region lookup | **Job-practice** (metadata filtering in pgvector is exactly what the job needs) |
| Hybrid search (keyword plus vector) with reranking | PostgreSQL full-text search plus HNSW vector search, merged, then bge-reranker-v2-m3 | **Job-practice** (core) |
| Answer always shows sources, "as of" date and official link | Store fetch date and source date per section; the answer template forces both | **Job-practice** (answers with sources) |
| Access restriction by user group | For example, an internal-only tier for machine translations or draft evaluation notes | **Job-practice** (Authelia plus LLDAP groups mapped to row-level filters) |
| Structured extraction of call metadata from English PDFs and portal records | Programme, topic identifier, deadline(s), budget, funding rate, eligible countries, status | **Job-practice** (ingestion pipeline), partly extra |
| Multi-country deadline calendar | One table of deadlines with time zone, stage (single or two-stage), status; refreshed from the portal status codes | Extra scope (small, high user value) |
| Eligibility filters: country, company size, sector (NACE code), topic, programme, status, deadline | Structured query before retrieval | Extra scope, but simple versions are cheap |
| Small and medium-sized enterprise definition check (fewer than 250 staff and turnover up to €50 million or balance sheet up to €43 million, plus linked and partner enterprise rules) | Rule module from Recommendation 2003/361 | Extra scope |
| De minimis ceiling | €300,000 per single undertaking over any three years, per member state; Regulation 2023/2831, applies 1 January 2024 to 31 December 2030\[60\]\[61\] | Extra scope |
| Regional aid intensity maps for all countries | Per-region maximum intensity plus small and medium-sized bonuses | Extra scope (Phase 2) |
| Programme association status (which non-member countries can join which programme) | Country × programme table | Extra scope (Phase 2) |
| Hallucination control | Refuse to state amounts, rates or deadlines not present in retrieved text; show the quote; flag stale documents | **Job-practice** (answer quality evaluation), plus consultant safety |
| Stale-document detection | Example: Malta's 2023 digitalisation guidance still cites the old €200,000 de minimis ceiling\[62\] | Extra scope, but a great evaluation-set example |
| Separate machine-translation partition | Own table and index, labelled in answers | Extra scope (later) |
| Migration equivalence proof | Fixed question set, compare retrieved identifiers, rank overlap and answer similarity before and after dump/restore to the new data centre | **Job-practice** (explicit job deliverable) |

---

### E. Hardware feasibility re-check

**Model fit (unchanged conclusion).** Qwen3.5-9B was released in early 2026 under the Apache 2.0 licence. According to InsiderLLM, Qwen 3.5 came out in three waves: "the flagship 397B-A17B on February 16, mid-range models (122B-A10B, 35B-A3B, 27B) on February 24, and the small models (9B, 4B, 2B, 0.8B) on March 2, 2026", and LLM Stats also gives 2 March 2026 for the 9B. It has about 9.65 billion parameters and a native context of 262,144 tokens, and it is a vision-language model with a hybrid attention design.\[63\]\[64\]\[65\] At 4-bit, the weights take about 5.5–6.5 gigabytes. bge-m3 and bge-reranker-v2-m3 take about 1.1 gigabytes each at half precision. With the context capped at 16,000–32,000 tokens, the total is about 9–12 gigabytes of the 16 available. Do not use the full 262,000 context: retrieval answers need only 6–10 reranked sections. Newer open-weight Qwen releases exist: InsiderLLM lists Qwen 3.6 (April 2026) in 27-billion dense and 35-billion mixture-of-experts sizes, and a Qwen3.8-27B under Apache 2.0 from 5 August, but no 9-billion-class Qwen3.6, so none of them is a drop-in replacement for 16 gigabytes. Test before switching.

**Scaling numbers.** These are estimates for this laptop. They assume 1,024-dimension vectors, about 400 tokens per section, and HNSW with 16 connections per node and a build-time candidate list of 64.

| Corpus size | Embedding time (bge-m3 on the laptop graphics card, including overhead) | Vector column size (full precision / half precision) | HNSW index size | HNSW build time (parallel workers, memory for building set to 8–16 gigabytes) | Total database size (text, metadata, vectors, index, full-text index) | Search latency (vector plus keyword) | End-to-end answer |
|---|---|---|---|---|---|---|---|
| 300,000 | 3–8 hours | about 1.2 / 0.6 gigabytes | about 1.2–2.4 gigabytes | about 10–25 minutes | about 4–6 gigabytes | about 5–15 milliseconds | 1–2 seconds before first word; 8–15 seconds for a full answer |
| 500,000 | 5–13 hours | about 2.0 / 1.0 gigabytes | about 2–4 gigabytes | about 20–45 minutes | about 7–10 gigabytes | about 5–20 milliseconds | same (dominated by reranking and generation) |
| 1,000,000 | 10–26 hours | about 4.1 / 2.0 gigabytes | about 4–8 gigabytes | about 45–120 minutes | about 14–20 gigabytes | about 10–30 milliseconds | same, slightly slower reranking if more candidates |
| 2,000,000 (with Kohesio translations) | 20–50 hours | about 8.2 / 4.1 gigabytes | about 8–16 gigabytes | about 2–5 hours | about 30–40 gigabytes | about 15–40 milliseconds | same |

**Why these numbers are credible:**
- pgvector's HNSW supports the plain vector type up to 2,000 dimensions and half precision up to 4,000, so 1,024 dimensions is fine either way.\[66\]\[67\]
- Builds are much faster when the graph fits in the memory allowed for building.\[67\] A published rule of thumb is vectors × dimensions × 4 bytes × 2, which gives about 8 gigabytes for 1 million 1,024-dimension vectors.\[68\] Your 64 gigabytes of system memory handle that easily.
- Parallel index building arrived in pgvector 0.6.0. Supabase reports "Building an HNSW index is now up to 30x faster for unlogged tables". In its test with 1 million 1,536-dimension vectors, the parallel build took 9.5 minutes against about 1 hour 27 minutes before, which is "7-9 times faster" for normal tables.
- Your ~8 terabytes of solid-state disk make storage a non-issue.

**Practical constraints:**
- The graphics card cannot embed and generate at full speed at the same time. Run bulk embedding with the chat model stopped, or overnight.
- Laptop cooling will throttle long embedding runs. Budget the upper end of each range.
- Re-embedding after a chunking change is the real cost. At 1 million sections it is a full day of work.

**Advice: cap the core at about 500,000 sections**, and use half-precision vectors if you go above that. At 300,000–500,000, every job-practice operation fits inside a working evening: full re-index, dump, restore and verification. That matters most for the migration-equivalence proof, because you will repeat those operations several times.

---

### F. Legal and ethical points

- **Attribution.** The Commission legal notice says content "is licensed under the Creative Commons Attribution 4.0 International (CC BY 4.0) licence. This means that reuse is allowed, provided appropriate credit is given and changes are indicated."\[9\] In practice: credit "© European Union" with the source link, and mark that you chunked, extracted and summarised the text. Put the attribution on every cited source in the answer and on an "About the data" page.
- **Exclusions in the notice.** The notice excludes content with "identifiable private individuals" or "third-party works", and "logos and names".\[9\] Do not use the Commission logo or emblem in your interface.
- **Endorsement.** The Commission notice's only endorsement wording concerns external links: "Such linked references do not constitute endorsement by the European Commission".\[9\] The CC BY 4.0 licence itself forbids implying endorsement. So add your own statement.
- **Personal data to strip:**
  - Contact persons, e-mails and phones in the Digital Innovation Hubs catalogue, which lists named managers with e-mails and phone numbers.\[32\]
  - CORDIS participant contact fields and principal investigator names.
  - Kohesio beneficiaries who are private individuals, such as farmers and sole traders.
  - National Contact Point names.
  - Enterprise Europe Network profile contacts.
  - Keep organisation names and official organisation web addresses; drop person-level fields.
- **Other licence checks:** keep.eu, Eureka and the European Investment Fund are not Commission websites. Check their terms, and prefer link-out plus short quotes until their terms are confirmed.
- **Suggested disclaimer wording:** "This assistant is an independent tool. It is not operated, endorsed or checked by the European Commission, any European Union body or any national authority. Answers are generated automatically from public official documents, shown with their source and the date they were retrieved, and may be incomplete or out of date. Always confirm eligibility, amounts and deadlines in the official call documents before applying. Source content © European Union and other rightholders, reused under the terms indicated for each source."

---

### G. Revised time estimate

**Base job-practice work packages** (same as the generic version):

| Work package | Hours |
|---|---|
| Rootless Podman plus Quadlet systemd units | 8–12 |
| Caddy reverse proxy plus Authelia plus LLDAP login chain | 10–16 |
| PostgreSQL plus pgvector setup, HNSW, full-text index | 6–10 |
| Model serving (Qwen, bge-m3, reranker behind an OpenAI-compatible endpoint) | 8–14 |
| Ingestion, chunking, embedding pipeline | 10–16 |
| Retrieval, reranking, answer with sources | 10–16 |
| User management and access restriction | 6–10 |
| Dump, restore, verification | 6–10 |
| Migration and proof of equivalent search and answers | 8–12 |
| Documentation | 4–6 |
| **Base subtotal** | **76–122** |

**Domain packages by phase:**

| Package | Phase 1 (minimal, English-only, European level plus a few English-publishing countries) | Phase 2 additions (full consultant, all countries) |
|---|---|---|
| EUR-Lex via CELLAR SPARQL and REST (relevant acts, recovery plan decisions) | 6–10 | 2–4 |
| Funding and Tenders search service (topics, statuses, deadlines, National Contact Points) | 6–10 | 2–4 |
| CORDIS bulk download and filtering | 3–5 | 1–2 |
| keep.eu / Interreg, Cohesion Open Data, Kohesio structured export | 2–4 | 4–8 |
| PDF parsing of work programmes and guides (tables, deadlines) | 8–14 | 4–6 |
| National English sources (Phase 1: Ireland, Malta, Estonia, Finland, Denmark; Phase 2: all remaining English and partly English publishers) | 6–10 | 8–14 |
| Commission-level descriptions for all countries plus link-out registry of national authorities | — | 12–20 |
| Metadata and multi-country calendar handling | 6–10 | 6–10 |
| Eligibility logic (Phase 1: country, size, programme, status, deadline filters, small and medium-sized enterprise and de minimis checks; Phase 2: regional aid intensities by region, association status, Eurostars national rules, state-aid categories) | 5–8 | 20–35 |
| Application checklists and start-to-finish guidance flows | — | 15–25 |
| Evaluation set (Phase 1: about 150 questions; Phase 2: 300 or more, per country) | 8–12 | 8–14 |
| Legal, attribution, personal-data stripping, disclaimer | 2–3 | 1–2 |
| Optional labelled machine-translation tier | — | (6–10, optional, not counted) |
| **Domain subtotal** | **52–86** | **83–144** |
| **Phase total** | **about 130–210 hours** | **about 210–340 hours cumulative** |

**Comparison with previous estimates:**
- Generic version: 75–120 hours.
- Romanian minimal: 100–160 hours. The revised Phase 1 is 130–210 hours, somewhat higher because the scope is broader, although each source is easier.
- Romanian full: 150–260 hours. The revised Phase 2 is 210–340 hours, higher because of multi-country eligibility and link-out coverage for 30 or more countries.

---

### Recommendations

1. **Build Phase 1 first and treat it as the job rehearsal.** The corpus should be European level plus Ireland, Malta, Estonia, Finland and Denmark, capped at about 300,000–400,000 sections. It should cover every job-stack item, and the migration-equivalence proof should run on a frozen snapshot.
2. **Make source identity and dates sacred.** Store each section's source identifier (CELEX number for legislation, topic identifier, CORDIS project number), source date and fetch date. They drive citations, "as of" dates, staleness warnings and the migration comparison.
3. **Keep Kohesio text out of the core.** Use its structured fields and generate English sentences from them. Add the translated tier only later, labelled and access-restricted.
4. **Do the eligibility engine as rules plus retrieval, not as model reasoning.** Let code decide small and medium-sized enterprise status, de minimis headroom and regional ceilings. Let the model explain the result, with sources.
5. **Plan for the 2028–2034 programme change.** Add a programme-period field now, so the new framework programmes can sit alongside the old ones without re-design.

### Caveats

- The section counts and hardware timings are engineering estimates, not measurements. Measure throughput on your laptop with 10,000 sections before committing.
- The CORDIS project counts come from a third-party guide.\[15\] Kohesio's own About page says it "currently contains more than 1.5 million projects and approximately 500,000 beneficiaries", while the Organisation for Economic Co-operation and Development, citing the Commission (2025), reports "over 640 000 beneficiaries have implemented more than 1.8 million projects… since 2014". The English columns in the Kohesio country exports were not opened and verified.
- Several Partnership Agreements are published only in national languages. Check each one before assuming an English original exists.
- The national English-coverage survey is a snapshot from September 2026. Lithuania's status and the completeness of the Swedish, Dutch and Austrian English pages may change.
- The share of European money covered by fully English national calls is my estimate, not a published figure.

## Sources

1. [National Contact Points (NCPs) - EU Funding & Tenders Portal](https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/support/ncp)
2. [Open Data Portal for the European Structural Investment Funds - European Commission](https://cohesiondata.ec.europa.eu/cohesion_overview/21-27)
3. [Frequently asked questions - Kohesio](https://kohesio.eu/en/faq)
4. [Frequently asked questions - Kohesio - Europa.eu](https://kohesio.ec.europa.eu/en/faq)
5. [CORDIS - EU Research Projects Under HORIZON EUROPE (2021-2027) by EU Publications Office](https://baselight.app/u/eupublicationsoffice/dataset/cordis_eu_research_projects_under_horizon_europe_2021_2027)
6. [Linking data: Kohesio platform](https://data.europa.eu/en/publications/datastories/linking-data-kohesio-platform)
7. [2021-2027 cohesion programme CCI / NUTS Lookup table](https://cohesiondata.ec.europa.eu/2021-2027/2021-2027-cohesion-programme-CCI-NUTS-Lookup-table/92d9-xqvh)
8. [Legal notice](https://emsa.europa.eu/emswe-mig/OtherFiles/f21.htm)
9. [Legal notice](https://commission.europa.eu/legal-notice_en)
10. [Eurostars - BMFTR](https://www.bmftr.bund.de/EN/Research/InternationalAffairs/Europe/Eurostars/eurostars_node.html)
11. [Timeline - Recovery and Resilience Scoreboard](https://ec.europa.eu/economy_finance/recovery-and-resilience-scoreboard/timeline.html)
12. [Home](https://horizoneuropencpportal.eu/)
13. [EU Funding Tenders Portal — Find & Apply for European Grants](https://www.eufundportal.com/funding-tenders-portal)
14. [EU Funding & Tenders Portal](https://webgate.ec.europa.eu/funding-tenders-opportunities/x/uIArB)
15. [CORDIS Project Database: How to Search EU-Funded Research (2026 Guide)](https://criteri.ai/blog/cordis-project-database-guide)
16. [Commission launches online platform of ESF and ERDF-funded projects - EURoma](https://www.euromanet.eu/news/commission-launches-online-platform-of-esf-and-erdf-funded-projects/)
17. [Inforegio - Partnership Agreement (PA) - European Commission](https://ec.europa.eu/regional_policy/policy/what/glossary/partnership-agreement_en)
18. [Partnership Agreement with Malta](https://commission.europa.eu/publications/partnership-agreement-malta-2021-2027_en)
19. [Partnership Agreement with Ireland](https://commission.europa.eu/publications/partnership-agreement-ireland-2021-2027_en)
20. [Partnership Agreements on EU funds 2021-2027 - European Commission](https://commission.europa.eu/publications/partnership-agreements-eu-funds-2021-2027_en)
21. [A SURVEY OF NATIONAL RECOVERY AND RESILIENCE PORTALS ACROSS EU COUNTRIES](https://www.rgs.mef.gov.it/_Documenti/VERSIONE-I/Comunicazione/Workshop-e-convegni/2025/seminario-workshop-internazionale-sulla-diffusione-dei-dati-del-PNRR/1.1_A-survey-of-national-recovery-and-resilience-portals-across-EU-countries.pdf)
22. [Recovery and Resilience Facility](https://eufundingoverview.be/funding/recovery-and-resilience-facility)
23. [Recovery and Resilience Scoreboard - European data](https://data.europa.eu/data/datasets/recovery-and-resilience-scoreboard?locale=en)
24. [State aid: Commission approves 2022-2027 regional aid map for Belgium - PubAffairs Bruxelles](https://www.pubaffairsbruxelles.eu/eu-institution-news/state-aid-commission-approves-2022-2027-regional-aid-map-for-belgium/)
25. [State aid: Commission approves 2022-2027 regional aid map for Czechia - PubAffairs Bruxelles](https://www.pubaffairsbruxelles.eu/eu-institution-news/state-aid-commission-approves-2022-2027-regional-aid-map-for-czechia/)
26. [Access to EU Finance - European Commission - Europa.eu](https://youreurope.europa.eu/business/finance-funding/getting-funding/access-finance/financial-intermediaries?shs_term_node_tid_depth=1275)
27. [Access to EU Finance - European Commission](https://youreurope.europa.eu/business/finance-funding/getting-funding/access-finance/financial-intermediaries?shs_term_node_tid_depth=708)
28. [Find EU Financing Partners](https://youreurope.europa.eu/business/finance-funding/getting-funding/access-finance/financial-intermediaries?shs_term_node_tid_depth=884)
29. [EU financing](https://youreurope.europa.eu/business/finance-funding/getting-funding/access-finance/en)
30. [Where to access finance - EIF financial intermediaries](https://www.eif.org/eif.org/what_we_do/where/index.htm)
31. [BIHK EEN: International Partner Search](https://een-bayern.de/en/international-partner-search)
32. [edih catalogue](https://european-digital-innovation-hubs.ec.europa.eu/ro/edih-catalogue?page=6)
33. [Eurostars Call 11 for projects - deadline September 2026 - Eureka Network](https://www.eurekanetwork.org/programmes-and-calls/eurostars/eurostars-call-for-projects-september-2026/)
34. [Eurostars Call 10 for projects - deadline March 2026 - Eureka Network](https://www.eurekanetwork.org/programmes-and-calls/eurostars/eurostars-march-2026/)
35. [Eurostars Call 12 for projects - deadline March 2027 - Eureka Network](https://www.eurekanetwork.org/programmes-and-calls/eurostars/eurostars-call-12-for-projects-deadline-march-2027/)
36. [News and updates - Keep.eu](https://keep.eu/news-and-updates/)
37. [Interreg and IPA-IPA cross-border projects, partners, and programmes Interreg and pre-accession cross-border projects, partners, programmes](https://keep.eu/)
38. [About keep.eu - Keep.eu](https://www.keep.eu/keep/about-keep)
39. [Minister Burke announces €40 million call for disruptive innovation](https://www.enterprise-ireland.com/en/news/40-million-call-for-disruptive-innovation)
40. [Digitalise your Business Guidance Notes Version: 1.0](https://fondi.eu/wp-content/uploads/2024/01/Digitalise-your-Business-Guidance-Notes_V1.pdf)
41. [FONDI.eu](https://fondi.eu/what-funding-is-available/social-infrastructure/)
42. [Grant for innovation and development in cybersecurity - EIS](https://eis.ee/en/services/grant-for-innovation-and-development-in-cybersecurity/)
43. [Research, development, piloting for large companies](https://www.businessfinland.fi/en/services/funding/funding-services/research-and-development-funding/research-and-development-funding-large-corporation/)
44. [Instructions and forms for applying for funding](https://www.businessfinland.fi/en/for-finnish-customers/services/funding/guidelines-terms-and-forms/applying-for-funding)
45. [Grand Solutions 2026: Defense Technology and Innovation](https://innovationsfonden.dk/en/p/grand-solutions/grand-solutions-2026-defense-technology)
46. [Grand solutions 2026: Quantum Technologies - Danmarks Innovationsfond](https://danmarksinnovationsfond.dk/en/calls/grand-solutions-2026-quantum/)
47. [FUNDING SCHEME «RESTART 2016-2020» Programmes for Research, Technological](https://iris.research.org.cy/file/public/e8955e65-4654-f111-81ab-005056ab00f0)
48. [Innovation Project for the Industrial Sector: Industry and services](https://www.forskningsradet.no/en/call-for-proposals/2025/innovation-project-industrial-sector-industry-services/)
49. [Submit short application](https://www.innosuisse.ch/inno/en/home/promotion-of-national-projects/swiss-accelerator/short-application.html)
50. [Innosuisse Start-Up Innovation Projects Guide: Your Gateway to Market Entry - Evolution Europe](https://evolutioneurope.eu/blog/innosuisse-start-up-innovation-projects/)
51. [Apply for funding from Vinnova for your innovation project](https://www.vinnova.se/en/apply-for-funding)
52. [Innovation Norway](https://en.innovasjonnorge.no/)
53. [Support International Business (SIB)](https://english.rvo.nl/subsidies-financing/sib)
54. [liaa.business.gov.lv - state platform for business development](https://liaa.business.gov.lv/en)
55. [For ideas and start-ups](https://liaa.business.gov.lv/en/support-opportunities/ideas-and-start-ups)
56. [Quantum Austria](https://www.ffg.at/en/quantum-austria)
57. [Innovation Agency Lithuania](https://www.inovacijuagentura.lt/en/about-us/)
58. [Funding databases - Europa-Universität Flensburg (EUF)](https://www.uni-flensburg.de/en/forschung/forschungsfoerderung/funding-databases?sword_list%5B0%5D=peter&cHash=e7e93688dd33cf40f77e40d55f38be20)
59. [Rechercheplattformen](https://forschung.verwaltung.uni-halle.de/foerderung_forschung-transfer/rechercheplattformen/)
60. [1 The new De Minimis Regulations 2024 15 December 2023](https://gsk.de/wp-content/uploads/2023/12/GSK-Update-De-minimis-VO-2024_EN.pdf)
61. [State aid and de minimis aid](https://cms.law/en/int/expert-guides/expert-guide-for-state-aid/state-aid-and-de-minimis-aid)
62. [SME Digitalisation Grant Scheme Guidance Notes Version: 2.0](https://fondi.eu/wp-content/uploads/2023/01/SME-Digitalisation-Scheme_GN_V2_010123.pdf)
63. [Qwen3.5-9B: Specifications and GPU VRAM Requirements](https://apxml.com/models/qwen35-9b)
64. [Qwen3.5-9B - API Pricing & Benchmarks](https://openrouter.ai/qwen/qwen3.5-9b)
65. [Qwen3.5 9B - Intelligence, Performance & Price Analysis](https://artificialanalysis.ai/models/qwen3-5-9b)
66. [The pgvector extension - Neon Docs](https://neon.com/docs/extensions/pgvector)
67. [pgvector Performance: Benchmarks, Latency & Limits 2026](https://comparedge.com/tools/pgvector/performance)
68. [Scaling pgvector: Memory, Quantization, and Index Build Strategies - DEV Community](https://dev.to/philip_mcclarence_2ef9475/scaling-pgvector-memory-quantization-and-index-build-strategies-8m2)
