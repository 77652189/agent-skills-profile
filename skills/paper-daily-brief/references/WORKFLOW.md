# Workflow and data contract

The CLI keeps `<project-root>/.paper-daily-brief/paper_daily.sqlite3` and atomically replaces same-day reports. It discovers the nearest Git root from the current working directory; non-Git projects use the current working directory. Runtime data inside the Skill directory is rejected. Use global `--data-dir` only to select another directory inside the active project.

Candidate identity precedence is DOI, PMID, PMCID, OpenAlex ID, then a normalized title. Every merged candidate retains all source records. The database stores title, abstract, authors, journal, date, identifiers, URLs, classification, score, translation cache hash, first/last seen dates, and last reported date.

For PubMed XML, read DOI and other identifiers only from the paper's direct `PubmedData/ArticleIdList`. Never scan descendant `ArticleId` nodes or fall back to `ReferenceList`, because cited-paper identifiers are not identifiers of the retrieved paper. A refreshed record with the same PMID is authoritative for repairing its DOI and stale identity index.

Classification combines the built-in Y103 taxonomy with configured topics. Exclusion keywords win. A topic receives keyword evidence from title and abstract; title matches weigh more. Results with weak or conflicting evidence are marked `needs_review`. Unmatched papers remain `other`.

Priority score combines topic relevance, classification confidence, identifier/source authority, abstract completeness, open-access availability, recency, and whether the paper has already appeared in an earlier brief. Reports must expose the score components and never describe ranking as scientific validity.

`brief` JSON contains:

- run metadata and configuration summary without secrets;
- source counts, errors, retries, and fetch timestamps;
- ranked items with identifiers, original abstract, cached Chinese translation, classification evidence, URLs, and source records;
- `translation_pending` IDs when a requested translation is unavailable.

Markdown and JSON must contain the same included candidate IDs and source-error summary.

Review input accepts either `{candidate_id: decision}` or `{"reviews": [{...}]}`. Each decision contains `candidate_id`, `classification_id`, `classification_name`, `confidence`, and `reason`. Only configured Y103/custom IDs or `other` are accepted.
