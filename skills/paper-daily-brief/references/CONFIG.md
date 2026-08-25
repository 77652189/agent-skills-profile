# Configuration

`config.toml` is intentionally empty after installation. Copy the relevant blocks below into it. At least one non-empty `brief.query` or enabled custom topic, and at least one enabled source, are required.

```toml
[brief]
query = "Pichia pastoris secretion OR Komagataella phaffii secretion"
lookback_days = 14
max_items = 30
language = "zh-CN"
translate_abstracts = true
use_y103 = true
required_keywords_any = ["pichia pastoris", "komagataella phaffii", "k. phaffii"]

[runtime]
timeout_seconds = 30
max_retries = 2
max_workers = 6
contact_email = ""

[sources.pubmed]
enabled = true
api_key_env = "NCBI_API_KEY"
api_key = ""
max_results = 20

[sources.europe_pmc]
enabled = true
max_results = 20

[sources.openalex]
enabled = true
api_key_env = "OPENALEX_API_KEY"
api_key = ""
max_results = 20

[sources.biorxiv]
enabled = true
max_results = 20

[sources.medrxiv]
enabled = true
max_results = 20

[sources.crossref]
enabled = true
api_key_env = "CROSSREF_API_KEY"
api_key = ""
max_results = 20

[[topics]]
id = "custom-secretion"
name = "重组蛋白分泌"
query = "recombinant protein secretion"
keywords = ["secretion", "secretory pathway", "signal peptide"]
exclude_keywords = ["human clinical trial"]
```

Environment variables override inline `api_key` values. Inline values are supported for local use but remain plaintext. Never commit `config.toml`.

`brief.required_keywords_any` is an optional local relevance gate applied after remote retrieval. At least one phrase must occur in the title or abstract. Use it when broad Boolean queries from Crossref or OpenAlex return off-topic records.

## Generic REST JSON source

```toml
[sources.my_database]
enabled = true
type = "rest_json"
url = "https://api.example.org/papers"
max_results = 50
results_path = "data.items"
pagination = "page" # none, page, offset
page_param = "page"
page_start = 1
page_size_param = "size"
page_size = 20
max_pages = 3
query_param = "q"
from_date_param = "from"
until_date_param = "until"
api_key_env = "MY_DATABASE_KEY"
api_key = ""
api_key_header = "Authorization"
api_key_prefix = "Bearer "

[sources.my_database.params]
format = "json"

[sources.my_database.headers]
Accept = "application/json"

[sources.my_database.fields]
title = "title"
abstract = "abstract"
authors = "authors"
journal = "journal.name"
published_date = "published"
doi = "identifiers.doi"
pmid = "identifiers.pmid"
pmcid = "identifiers.pmcid"
openalex_id = "identifiers.openalex"
landing_url = "url"
pdf_url = "open_access.pdf"
is_open_access = "open_access.is_oa"
```

Field mappings use dot-separated object paths. Authors may be a list of strings, a list of objects with `name`, or a string. Generic adapters support GET requests and page/offset pagination only.
