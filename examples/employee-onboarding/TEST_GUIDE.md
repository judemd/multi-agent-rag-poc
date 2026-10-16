# Employee onboarding demo

All organisations, addresses, policies and benefits here are fictional. Reserved
`.example` email addresses do not contact real people. This is test data, not HR advice.

Upload **only these four source files** as a new dataset named Employee onboarding:

- `leave_policy.txt`
- `office_locations.csv`
- `equipment_catalogue.json`
- `benefits_handbook.pdf`

Do not upload this guide or the PDF-generation script: expected answers must stay out
of retrieval. Follow the same two approval gates, then build the search index. The
small dataset should produce about 15 text sections with the default settings.

| Question | Expected answer | Supporting source |
|---|---|---|
| How do I request annual leave? | People Portal, at least 10 working days ahead; line manager approval. | leave_policy.txt |
| How much annual leave does a full-time employee receive? | 25 days plus public holidays observed by the assigned office. | leave_policy.txt |
| When must carried-over leave be used? | By 31 March of the following year; up to 5 days with manager approval. | leave_policy.txt |
| Which days should London employees work on site? | Tuesday and Thursday. | office_locations.csv |
| Where do remote employees collect their laptop? | They can receive home delivery; coordinate with IT. | benefits_handbook.pdf, equipment_catalogue.json |
| How do I request a USB headset? | IT Service Desk portal, equipment ID EQ-HEAD-01; no separate manager approval. | equipment_catalogue.json |
| Can anyone request an external monitor? | Employees with an approved home-working arrangement; manager approval; one monitor. | equipment_catalogue.json |
| How much is the annual learning budget? | GBP 500, after probation, with manager approval. | benefits_handbook.pdf |
| What should I complete in my first week? | Benefits enrolment, security training, and the starter checklist; details in handbook. | benefits_handbook.pdf |
| When will ergonomic chairs be back in stock? | Missing evidence: no restock date is published. | equipment_catalogue.json |
| How much is the annual performance bonus? | Missing evidence; no bonus policy is provided. | None |
| Which private health insurer will be used next year? | Missing evidence; no insurer or next-year commitment is provided. | None |

Keep Always review answers enabled. Check cited excerpts, publish supported responses
and appropriate abstentions, and reject an inaccurate draft. Semantic search may return
different supporting excerpts; the expected facts should remain consistent.
