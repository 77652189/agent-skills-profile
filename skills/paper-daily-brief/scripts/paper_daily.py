#!/usr/bin/env python3
"""Independent scholarly search and daily-brief CLI. Python 3.12 stdlib only."""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import datetime as dt
import hashlib
import html
import json
import os
import re
import sqlite3
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable

SKILL_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = SKILL_ROOT / "config.toml"
DATA_DIR = Path.cwd() / ".paper-daily-brief"
DB_PATH = DATA_DIR / "paper_daily.sqlite3"
REPORT_DIR = DATA_DIR / "reports"
USER_AGENT = "paper-daily-brief/1.0 (+independent Codex skill)"

BUILTIN_SOURCES = {"pubmed", "europe_pmc", "openalex", "biorxiv", "medrxiv", "crossref"}
SOURCE_PRIORITY = {"pubmed": 1, "europe_pmc": 2, "openalex": 3, "biorxiv": 4, "medrxiv": 4, "crossref": 5}

Y103 = (
    ("y103-01", "宿主与菌株工程", ("strain engineering", "host engineering", "komagataella", "pichia pastoris")),
    ("y103-02", "启动子与转录调控", ("promoter", "transcription regulation", "transcriptional regulation")),
    ("y103-03", "信号肽与分泌引导序列", ("signal peptide", "secretion leader", "alpha mating factor", "α-mating factor")),
    ("y103-04", "分泌通路与蛋白运输", ("secretory pathway", "protein trafficking", "vesicle transport", "secretion")),
    ("y103-05", "蛋白折叠与内质网应激", ("protein folding", "endoplasmic reticulum stress", "unfolded protein response", "upr")),
    ("y103-06", "糖基化与翻译后修饰", ("glycosylation", "post-translational modification", "glycoengineering")),
    ("y103-07", "蛋白酶控制与产物降解", ("protease", "proteolysis", "product degradation")),
    ("y103-08", "代谢工程与辅因子平衡", ("metabolic engineering", "cofactor balance", "metabolic flux")),
    ("y103-09", "发酵与生物工艺优化", ("fermentation", "bioprocess", "fed-batch", "process optimization")),
    ("y103-10", "甲醇利用与替代碳源", ("methanol utilization", "methanol metabolism", "carbon source", "methylotroph")),
    ("y103-11", "重组蛋白生产", ("recombinant protein", "heterologous protein", "protein production")),
    ("y103-12", "抗体、酶与生物药产品", ("antibody", "biopharmaceutical", "therapeutic protein", "enzyme production")),
    ("y103-13", "基因组编辑与合成生物学", ("genome editing", "crispr", "synthetic biology", "genetic tool")),
    ("y103-14", "组学、系统生物学与建模", ("transcriptom", "proteom", "metabolom", "systems biology", "modeling")),
    ("y103-15", "细胞生理、耐受与稳健性", ("stress tolerance", "robustness", "cell physiology", "oxidative stress")),
    ("y103-16", "下游纯化与产品质量", ("downstream processing", "purification", "product quality", "quality attribute")),
)


@dataclasses.dataclass
class Candidate:
    title: str
    abstract: str = ""
    authors: list[str] = dataclasses.field(default_factory=list)
    journal: str = ""
    published_date: str = ""
    doi: str = ""
    pmid: str = ""
    pmcid: str = ""
    openalex_id: str = ""
    landing_url: str = ""
    pdf_url: str = ""
    is_open_access: bool = False
    sources: list[str] = dataclasses.field(default_factory=list)
    source_records: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    candidate_id: str = ""
    classification_id: str = "other"
    classification_name: str = "其他/不纳入"
    confidence: float = 0.0
    classification_status: str = "rule"
    classification_reason: str = ""
    relevance_score: float = 0.0
    priority_score: float = 0.0
    abstract_translation_zh: str = ""
    translation_pending: bool = False
    first_seen: str = ""
    last_seen: str = ""
    last_reported: str = ""

    def public_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class SourceFailure(RuntimeError):
    def __init__(self, message: str, retries: int = 0):
        super().__init__(message)
        self.retries = retries


def today_iso() -> str:
    return dt.date.today().isoformat()


def load_config(path: Path | None = None) -> dict[str, Any]:
    path = path or CONFIG_PATH
    if not path.exists() or not path.read_bytes().strip():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def discover_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return current


def configure_storage(data_dir: str = "", *, cwd: Path | None = None) -> str:
    global DATA_DIR, DB_PATH, REPORT_DIR
    project_root = discover_project_root(cwd)
    target = Path(data_dir).expanduser().resolve() if data_dir else project_root / ".paper-daily-brief"
    skill_root = SKILL_ROOT.resolve()
    if target == skill_root or target.is_relative_to(skill_root):
        return "运行数据目录不能位于 Skill 目录内；请从目标项目根目录运行，或使用 --data-dir 指定项目内目录"
    DATA_DIR = target
    DB_PATH = target / "paper_daily.sqlite3"
    REPORT_DIR = target / "reports"
    return ""


def enabled_sources(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = config.get("sources") or {}
    return {str(name): dict(value) for name, value in raw.items() if isinstance(value, dict) and value.get("enabled") is True}


def validation_errors(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    brief = config.get("brief") if isinstance(config.get("brief"), dict) else {}
    topics = [topic for topic in config.get("topics", []) if isinstance(topic, dict) and topic.get("query")]
    if not str(brief.get("query") or "").strip() and not topics:
        errors.append("缺少检索主题：请配置 brief.query 或至少一个 topics[].query")
    sources = enabled_sources(config)
    if not sources:
        errors.append("缺少数据源：请至少启用一个 sources.<name>.enabled = true")
    for name, source in sources.items():
        if name not in BUILTIN_SOURCES and source.get("type") != "rest_json":
            errors.append(f"数据源 {name} 必须声明 type = 'rest_json'")
        if source.get("type") == "rest_json":
            if not source.get("url"):
                errors.append(f"数据源 {name} 缺少 url")
            if not source.get("results_path"):
                errors.append(f"数据源 {name} 缺少 results_path")
            fields = source.get("fields") or {}
            if not fields.get("title"):
                errors.append(f"数据源 {name} 缺少 fields.title")
            if source.get("pagination", "none") not in {"none", "page", "offset"}:
                errors.append(f"数据源 {name} pagination 仅支持 none/page/offset")
    return errors


def secret_value(source: dict[str, Any]) -> str:
    env_name = str(source.get("api_key_env") or "").strip()
    if env_name and os.getenv(env_name):
        return str(os.getenv(env_name))
    return str(source.get("api_key") or "")


def redact(value: Any, secrets: list[str]) -> Any:
    if isinstance(value, dict):
        return {k: redact(v, secrets) for k, v in value.items() if k not in {"api_key", "token", "password"}}
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    text = str(value)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def request_bytes(url: str, *, headers: dict[str, str], timeout: int, max_retries: int) -> tuple[bytes, int]:
    retries = 0
    while True:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read(), retries
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if retries >= max_retries:
                raise SourceFailure(f"{type(exc).__name__}: {exc}", retries) from exc
            retries += 1
            time.sleep(min(2 ** (retries - 1), 4))


def get_json(url: str, *, headers: dict[str, str], timeout: int, max_retries: int) -> tuple[Any, int]:
    payload, retries = request_bytes(url, headers=headers, timeout=timeout, max_retries=max_retries)
    try:
        return json.loads(payload), retries
    except json.JSONDecodeError as exc:
        raise SourceFailure(f"JSONDecodeError: {exc}", retries) from exc


def build_url(base: str, params: dict[str, Any]) -> str:
    clean = {key: value for key, value in params.items() if value not in (None, "", [])}
    return f"{base}?{urllib.parse.urlencode(clean, doseq=True)}"


def http_runtime(runtime: dict[str, Any]) -> dict[str, int]:
    """Keep source metadata such as contact_email out of HTTP call kwargs."""
    return {"timeout": int(runtime.get("timeout", 30)), "max_retries": int(runtime.get("max_retries", 2))}


def clean_doi(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text)
    return re.sub(r"^doi:\s*", "", text)


def normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", html.unescape(value).lower())


def identity_keys(candidate: Candidate) -> list[str]:
    pairs = (("doi", clean_doi(candidate.doi)), ("pmid", candidate.pmid), ("pmcid", candidate.pmcid), ("openalex", candidate.openalex_id))
    keys = [f"{kind}:{str(value).strip().lower()}" for kind, value in pairs if str(value).strip()]
    title = normalize_title(candidate.title)
    if title:
        keys.append(f"title:{title}")
    return keys


def candidate_id(candidate: Candidate) -> str:
    key = next(iter(identity_keys(candidate)), f"title:{normalize_title(candidate.title)}")
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def dotted(value: Any, path: str, default: Any = "") -> Any:
    current = value
    for part in str(path or "").split("."):
        if not part:
            continue
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return default
        if current is None:
            return default
    return current


def author_names(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in re.split(r";|,", value) if item.strip()]
    result: list[str] = []
    for item in value or []:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            name = item.get("name") or item.get("display_name") or " ".join(filter(None, [item.get("given"), item.get("family")]))
            if name:
                result.append(str(name))
    return result


def from_mapping(record: dict[str, Any], fields: dict[str, str], source: str) -> Candidate:
    def field(name: str, default: Any = "") -> Any:
        return dotted(record, str(fields.get(name) or ""), default)
    item = Candidate(
        title=str(field("title") or "").strip(), abstract=str(field("abstract") or "").strip(),
        authors=author_names(field("authors", [])), journal=str(field("journal") or ""),
        published_date=str(field("published_date") or "")[:10], doi=clean_doi(field("doi")),
        pmid=str(field("pmid") or ""), pmcid=str(field("pmcid") or ""), openalex_id=str(field("openalex_id") or ""),
        landing_url=str(field("landing_url") or ""), pdf_url=str(field("pdf_url") or ""),
        is_open_access=bool(field("is_open_access", False)), sources=[source],
    )
    item.source_records = [{"source": source, "record": record}]
    item.candidate_id = candidate_id(item)
    return item


def source_pubmed(query: str, since: str, until: str, cfg: dict[str, Any], runtime: dict[str, Any]) -> tuple[list[Candidate], int]:
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": int(cfg.get("max_results", 20)), "mindate": since, "maxdate": until, "datetype": "pdat", "api_key": secret_value(cfg)}
    data, r1 = get_json(build_url("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", params), headers={}, **http_runtime(runtime))
    ids = data.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return [], r1
    raw, r2 = request_bytes(build_url("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi", {"db": "pubmed", "id": ",".join(ids), "retmode": "xml", "api_key": secret_value(cfg)}), headers={}, **http_runtime(runtime))
    root = ET.fromstring(raw)
    out: list[Candidate] = []
    for article in root.findall(".//PubmedArticle"):
        title = "".join(article.findtext(".//ArticleTitle", default=""))
        abstract = " ".join("".join(node.itertext()) for node in article.findall(".//Abstract/AbstractText"))
        ids_map = {node.attrib.get("IdType", ""): (node.text or "") for node in article.findall("./PubmedData/ArticleIdList/ArticleId")}
        pmid = article.findtext("./MedlineCitation/PMID", default="")
        date = article.findtext(".//ArticleDate/Year", default="")
        item = Candidate(title=title, abstract=abstract, authors=[" ".join(filter(None, [a.findtext("ForeName"), a.findtext("LastName")])) for a in article.findall(".//Author")], journal=article.findtext(".//Journal/Title", default=""), published_date=date, doi=clean_doi(ids_map.get("doi")), pmid=pmid, pmcid=ids_map.get("pmc", ""), landing_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", sources=["pubmed"])
        item.source_records = [{"source": "pubmed", "pmid": pmid}]; item.candidate_id = candidate_id(item); out.append(item)
    return out, r1 + r2


def source_europe_pmc(query: str, since: str, until: str, cfg: dict[str, Any], runtime: dict[str, Any]) -> tuple[list[Candidate], int]:
    full_query = f"({query}) AND FIRST_PDATE:[{since} TO {until}]"
    data, retries = get_json(build_url("https://www.ebi.ac.uk/europepmc/webservices/rest/search", {"query": full_query, "format": "json", "resultType": "core", "pageSize": int(cfg.get("max_results", 20))}), headers={}, **http_runtime(runtime))
    out = []
    for row in data.get("resultList", {}).get("result", []):
        item = Candidate(title=row.get("title", ""), abstract=row.get("abstractText", ""), authors=author_names(row.get("authorString", "")), journal=row.get("journalTitle", ""), published_date=row.get("firstPublicationDate", ""), doi=clean_doi(row.get("doi")), pmid=str(row.get("pmid", "")), pmcid=str(row.get("pmcid", "")), landing_url=f"https://europepmc.org/article/{row.get('source', 'MED')}/{row.get('id', '')}", pdf_url=(f"https://europepmc.org/articles/{row.get('pmcid')}/bin" if row.get("pmcid") else ""), is_open_access=str(row.get("isOpenAccess", "N")) == "Y", sources=["europe_pmc"])
        item.source_records = [{"source": "europe_pmc", "id": row.get("id")}]; item.candidate_id = candidate_id(item); out.append(item)
    return out, retries


def reconstruct_abstract(index: Any) -> str:
    if not isinstance(index, dict): return ""
    words = sorted(((int(pos), word) for word, positions in index.items() for pos in positions), key=lambda x: x[0])
    return " ".join(word for _, word in words)


def source_openalex(query: str, since: str, until: str, cfg: dict[str, Any], runtime: dict[str, Any]) -> tuple[list[Candidate], int]:
    params = {"search": query, "filter": f"from_publication_date:{since},to_publication_date:{until}", "per-page": int(cfg.get("max_results", 20)), "mailto": runtime.get("contact_email", ""), "api_key": secret_value(cfg)}
    data, retries = get_json(build_url("https://api.openalex.org/works", params), headers={}, **http_runtime(runtime))
    out = []
    for row in data.get("results", []):
        oa = row.get("open_access") or {}; best = row.get("best_oa_location") or {}; primary = row.get("primary_location") or {}
        item = Candidate(title=row.get("title", ""), abstract=reconstruct_abstract(row.get("abstract_inverted_index")), authors=[a.get("author", {}).get("display_name", "") for a in row.get("authorships", [])], journal=(primary.get("source") or {}).get("display_name", ""), published_date=row.get("publication_date", ""), doi=clean_doi(row.get("doi")), pmid=str((row.get("ids") or {}).get("pmid", "")).rsplit("/", 1)[-1], pmcid=str((row.get("ids") or {}).get("pmcid", "")).rsplit("/", 1)[-1], openalex_id=str(row.get("id", "")).rsplit("/", 1)[-1], landing_url=primary.get("landing_page_url") or row.get("doi") or "", pdf_url=best.get("pdf_url") or "", is_open_access=bool(oa.get("is_oa")), sources=["openalex"])
        item.source_records = [{"source": "openalex", "id": row.get("id")}]; item.candidate_id = candidate_id(item); out.append(item)
    return out, retries


def source_preprint(server: str, query: str, since: str, until: str, cfg: dict[str, Any], runtime: dict[str, Any]) -> tuple[list[Candidate], int]:
    max_results = int(cfg.get("max_results", 20)); max_pages = max(1, int(cfg.get("max_pages", 3))); out = []; retries = 0; cursor = 0
    terms = [term.lower() for term in re.findall(r"[A-Za-z0-9_-]{3,}", query) if term.upper() not in {"AND", "OR", "NOT"}]
    for _ in range(max_pages):
        data, used = get_json(f"https://api.biorxiv.org/details/{server}/{since}/{until}/{cursor}", headers={}, **http_runtime(runtime)); retries += used
        rows = data.get("collection", [])
        for row in rows:
            haystack = f"{row.get('title', '')} {row.get('abstract', '')}".lower()
            if terms and not any(term in haystack for term in terms): continue
            item = Candidate(title=row.get("title", ""), abstract=row.get("abstract", ""), authors=author_names(row.get("authors", "")), journal=server, published_date=row.get("date", ""), doi=clean_doi(row.get("doi")), landing_url=f"https://doi.org/{row.get('doi', '')}", pdf_url=f"https://www.{server}.org/content/{row.get('doi', '')}.full.pdf", is_open_access=True, sources=[server])
            item.source_records = [{"source": server, "doi": row.get("doi")}]; item.candidate_id = candidate_id(item); out.append(item)
            if len(out) >= max_results: return out, retries
        if len(rows) < 100: break
        cursor += len(rows)
    return out, retries


def source_crossref(query: str, since: str, until: str, cfg: dict[str, Any], runtime: dict[str, Any]) -> tuple[list[Candidate], int]:
    headers = {}; key = secret_value(cfg)
    if key: headers["Authorization"] = f"Bearer {key}"
    params = {"query.bibliographic": query, "filter": f"from-pub-date:{since},until-pub-date:{until}", "rows": int(cfg.get("max_results", 20)), "mailto": runtime.get("contact_email", "")}
    data, retries = get_json(build_url("https://api.crossref.org/works", params), headers=headers, **http_runtime(runtime))
    out = []
    for row in data.get("message", {}).get("items", []):
        links = row.get("link") or []; pdf = next((x.get("URL", "") for x in links if "pdf" in str(x.get("content-type", "")).lower()), "")
        date_parts = dotted(row, "published.date-parts", [[]]); date = "-".join(str(x) for x in (date_parts[0] if date_parts else []))
        item = Candidate(title=" ".join(row.get("title") or []), abstract=re.sub(r"<[^>]+>", " ", row.get("abstract", "")), authors=[" ".join(filter(None, [a.get("given"), a.get("family")])) for a in row.get("author", [])], journal=" ".join(row.get("container-title") or []), published_date=date, doi=clean_doi(row.get("DOI")), landing_url=row.get("URL", ""), pdf_url=pdf, is_open_access=bool(pdf), sources=["crossref"])
        item.source_records = [{"source": "crossref", "doi": row.get("DOI")}]; item.candidate_id = candidate_id(item); out.append(item)
    return out, retries


def source_rest(name: str, query: str, since: str, until: str, cfg: dict[str, Any], runtime: dict[str, Any]) -> tuple[list[Candidate], int]:
    pagination = cfg.get("pagination", "none"); page_size = int(cfg.get("page_size", cfg.get("max_results", 20))); max_results = int(cfg.get("max_results", 20)); max_pages = int(cfg.get("max_pages", 1)); out = []; retries = 0
    key = secret_value(cfg); headers = {str(k): str(v) for k, v in (cfg.get("headers") or {}).items()}
    if key and cfg.get("api_key_header"): headers[str(cfg["api_key_header"])] = f"{cfg.get('api_key_prefix', '')}{key}"
    for index in range(max_pages):
        params = dict(cfg.get("params") or {}); params[str(cfg.get("query_param", "q"))] = query
        if cfg.get("from_date_param"): params[str(cfg["from_date_param"])] = since
        if cfg.get("until_date_param"): params[str(cfg["until_date_param"])] = until
        if key and cfg.get("api_key_param"): params[str(cfg["api_key_param"])] = key
        if pagination == "page": params[str(cfg.get("page_param", "page"))] = int(cfg.get("page_start", 1)) + index
        elif pagination == "offset": params[str(cfg.get("offset_param", "offset"))] = index * page_size
        if pagination != "none": params[str(cfg.get("page_size_param", "limit"))] = page_size
        data, used = get_json(build_url(str(cfg["url"]), params), headers=headers, **http_runtime(runtime)); retries += used
        rows = dotted(data, str(cfg["results_path"]), [])
        if not isinstance(rows, list): raise SourceFailure(f"results_path {cfg['results_path']} 未返回数组", retries)
        out.extend(from_mapping(row, cfg.get("fields") or {}, name) for row in rows if isinstance(row, dict))
        if pagination == "none" or len(rows) < page_size or len(out) >= max_results: break
    return [item for item in out if item.title][:max_results], retries


def search_source(name: str, cfg: dict[str, Any], query: str, since: str, until: str, runtime: dict[str, Any]) -> tuple[list[Candidate], int]:
    if name == "pubmed": return source_pubmed(query, since, until, cfg, runtime)
    if name == "europe_pmc": return source_europe_pmc(query, since, until, cfg, runtime)
    if name == "openalex": return source_openalex(query, since, until, cfg, runtime)
    if name in {"biorxiv", "medrxiv"}: return source_preprint(name, query, since, until, cfg, runtime)
    if name == "crossref": return source_crossref(query, since, until, cfg, runtime)
    return source_rest(name, query, since, until, cfg, runtime)


def merge_candidates(candidates: list[Candidate]) -> list[Candidate]:
    merged: list[Candidate] = []; index: dict[str, Candidate] = {}
    for incoming in candidates:
        target = next((index[key] for key in identity_keys(incoming) if key in index), None)
        if target is None:
            incoming.candidate_id = incoming.candidate_id or candidate_id(incoming); merged.append(incoming); target = incoming
        else:
            if len(incoming.abstract) > len(target.abstract): target.abstract = incoming.abstract
            if target.pmid and incoming.pmid and target.pmid == incoming.pmid and incoming.doi:
                target.doi = incoming.doi
            for field in ("doi", "pmid", "pmcid", "openalex_id", "journal", "published_date", "landing_url", "pdf_url"):
                if not getattr(target, field) and getattr(incoming, field): setattr(target, field, getattr(incoming, field))
            target.authors = list(dict.fromkeys(target.authors + incoming.authors)); target.sources = list(dict.fromkeys(target.sources + incoming.sources)); target.source_records = unique_source_records(target.source_records + incoming.source_records); target.is_open_access = target.is_open_access or incoming.is_open_access
        for key in identity_keys(target): index[key] = target
    return merged


def unique_source_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set(); result: list[dict[str, Any]] = []
    for record in records:
        key = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if key not in seen:
            seen.add(key); result.append(record)
    return result


def passes_local_relevance_gate(candidate: Candidate, config: dict[str, Any]) -> bool:
    required = [str(value).strip().lower() for value in (config.get("brief") or {}).get("required_keywords_any", []) if str(value).strip()]
    if not required:
        return True
    text = f"{candidate.title} {candidate.abstract}".lower()
    return any(value in text for value in required)


def topic_definitions(config: dict[str, Any]) -> list[tuple[str, str, tuple[str, ...], tuple[str, ...]]]:
    result = []
    if (config.get("brief") or {}).get("use_y103", True): result.extend((i, n, k, ()) for i, n, k in Y103)
    for pos, topic in enumerate(config.get("topics") or []):
        if not isinstance(topic, dict): continue
        keys = tuple(str(x).lower() for x in topic.get("keywords", []) if str(x).strip())
        if not keys and topic.get("query"): keys = tuple(x.lower() for x in re.findall(r"[A-Za-z0-9_-]{3,}", str(topic["query"])) if x.upper() not in {"AND", "OR", "NOT"})
        result.append((str(topic.get("id") or f"custom-{pos+1}"), str(topic.get("name") or topic.get("id") or f"自定义主题 {pos+1}"), keys, tuple(str(x).lower() for x in topic.get("exclude_keywords", []))))
    return result


def classify(candidate: Candidate, config: dict[str, Any]) -> None:
    title = candidate.title.lower(); abstract = candidate.abstract.lower(); best = (0.0, "other", "其他/不纳入", [], False)
    for topic_id, name, keywords, excludes in topic_definitions(config):
        excluded = [word for word in excludes if word and word in f"{title} {abstract}"]
        if excluded: continue
        title_hits = [word for word in keywords if word and word in title]; abstract_hits = [word for word in keywords if word and word in abstract]
        score = min(1.0, 0.45 * len(title_hits) + 0.18 * len(set(abstract_hits) - set(title_hits)))
        if score > best[0]: best = (score, topic_id, name, list(dict.fromkeys(title_hits + abstract_hits)), len(title_hits) + len(abstract_hits) == 1)
    score, topic_id, name, hits, single = best
    candidate.classification_id = topic_id; candidate.classification_name = name; candidate.confidence = round(score, 3); candidate.relevance_score = round(score * 100, 1)
    candidate.classification_status = "needs_review" if topic_id != "other" and (score < 0.55 or single) else "rule"
    candidate.classification_reason = (f"命中：{', '.join(hits)}" if hits else "标题与摘要未命中已配置分类证据")


def score_candidate(candidate: Candidate, report_date: str) -> float:
    authority = max((6 - SOURCE_PRIORITY.get(s, 6) for s in candidate.sources), default=0) * 1.5
    identifiers = 6 if candidate.doi or candidate.pmid or candidate.openalex_id else 0
    abstract = min(len(candidate.abstract) / 250, 1) * 6
    access = 3 if candidate.is_open_access or candidate.pdf_url else 0
    novelty = -12 if candidate.last_reported and candidate.last_reported < report_date else 5
    return round(candidate.relevance_score * 0.7 + authority + identifiers + abstract + access + novelty, 2)


def init_db(path: Path | None = None) -> sqlite3.Connection:
    path = path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True); conn = sqlite3.connect(path); conn.row_factory = sqlite3.Row
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS candidates(candidate_id TEXT PRIMARY KEY, payload TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, last_reported TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS identities(identity_key TEXT PRIMARY KEY, candidate_id TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS translations(candidate_id TEXT PRIMARY KEY, abstract_hash TEXT NOT NULL, translation_zh TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, kind TEXT NOT NULL, run_date TEXT NOT NULL, payload TEXT NOT NULL);
    """); conn.commit(); return conn


def upsert(conn: sqlite3.Connection, incoming: list[Candidate], seen_date: str) -> list[Candidate]:
    stored = []
    for item in incoming:
        existing_id = next((row[0] for key in identity_keys(item) if (row := conn.execute("SELECT candidate_id FROM identities WHERE identity_key=?", (key,)).fetchone())), None)
        if existing_id:
            row = conn.execute("SELECT * FROM candidates WHERE candidate_id=?", (existing_id,)).fetchone(); old = Candidate(**json.loads(row["payload"])); merged = merge_candidates([old, item])[0]; merged.candidate_id = existing_id; merged.first_seen = row["first_seen"]; merged.last_reported = row["last_reported"]
        else:
            merged = item; merged.candidate_id = item.candidate_id or candidate_id(item); merged.first_seen = seen_date
        merged.last_seen = seen_date
        conn.execute("INSERT INTO candidates VALUES(?,?,?,?,?) ON CONFLICT(candidate_id) DO UPDATE SET payload=excluded.payload,last_seen=excluded.last_seen", (merged.candidate_id, json.dumps(merged.public_dict(), ensure_ascii=False), merged.first_seen, merged.last_seen, merged.last_reported))
        conn.execute("DELETE FROM identities WHERE candidate_id=?", (merged.candidate_id,))
        for key in identity_keys(merged): conn.execute("INSERT OR REPLACE INTO identities VALUES(?,?)", (key, merged.candidate_id))
        stored.append(merged)
    conn.commit(); return stored


def load_candidates(conn: sqlite3.Connection, *, keyword: str = "", source: str = "", topic: str = "", since: str = "") -> list[Candidate]:
    result = []
    for row in conn.execute("SELECT * FROM candidates ORDER BY last_seen DESC"):
        item = Candidate(**json.loads(row["payload"])); item.first_seen = row["first_seen"]; item.last_seen = row["last_seen"]; item.last_reported = row["last_reported"]
        if keyword and keyword.lower() not in f"{item.title} {item.abstract}".lower(): continue
        if source and source not in item.sources: continue
        if topic and topic not in {item.classification_id, item.classification_name}: continue
        if since and item.last_seen < since: continue
        result.append(item)
    return result


def apply_translations(conn: sqlite3.Connection, items: list[Candidate], translations_path: str, enabled: bool) -> None:
    supplied: dict[str, str] = {}
    if translations_path:
        raw = json.loads(Path(translations_path).read_text(encoding="utf-8")); supplied = raw.get("translations", raw) if isinstance(raw, dict) else {}
        if isinstance(supplied, list): supplied = {str(x.get("candidate_id")): str(x.get("translation_zh", "")) for x in supplied if isinstance(x, dict)}
    for item in items:
        digest = hashlib.sha256(item.abstract.encode("utf-8")).hexdigest()
        translation = str(supplied.get(item.candidate_id, ""))
        if translation:
            conn.execute("INSERT OR REPLACE INTO translations VALUES(?,?,?,?)", (item.candidate_id, digest, translation, dt.datetime.now(dt.timezone.utc).isoformat()))
        row = conn.execute("SELECT abstract_hash,translation_zh FROM translations WHERE candidate_id=?", (item.candidate_id,)).fetchone()
        if row and row["abstract_hash"] == digest: item.abstract_translation_zh = row["translation_zh"]
        item.translation_pending = bool(enabled and item.abstract and not item.abstract_translation_zh)
    conn.commit()


def apply_reviews(items: list[Candidate], reviews_path: str, config: dict[str, Any]) -> None:
    if not reviews_path:
        return
    raw = json.loads(Path(reviews_path).read_text(encoding="utf-8"))
    reviews = raw.get("reviews", raw) if isinstance(raw, dict) else raw
    if isinstance(reviews, list):
        reviews = {str(value.get("candidate_id")): value for value in reviews if isinstance(value, dict)}
    if not isinstance(reviews, dict):
        raise ValueError("reviews JSON 必须是 candidate_id 映射或 reviews 数组")
    allowed = {value[0]: value[1] for value in topic_definitions(config)} | {"other": "其他/不纳入"}
    for item in items:
        review = reviews.get(item.candidate_id)
        if not isinstance(review, dict):
            continue
        category_id = str(review.get("classification_id") or "")
        if category_id not in allowed:
            raise ValueError(f"未知分类 ID: {category_id}")
        item.classification_id = category_id
        item.classification_name = str(review.get("classification_name") or allowed[category_id])
        item.confidence = max(0.0, min(1.0, float(review.get("confidence", item.confidence))))
        item.relevance_score = round(item.confidence * 100, 1) if category_id != "other" else 0.0
        item.classification_status = "codex_reviewed"
        item.classification_reason = str(review.get("reason") or "Codex 二阶段复核")


def execute_search(config: dict[str, Any], *, run_date: str) -> tuple[list[Candidate], list[dict[str, Any]], dict[str, int]]:
    brief = config.get("brief") or {}; lookback = max(1, int(brief.get("lookback_days", 14))); until = dt.date.fromisoformat(run_date); since = (until - dt.timedelta(days=lookback)).isoformat(); query = str(brief.get("query") or "").strip()
    topic_queries = [str(x.get("query")) for x in config.get("topics", []) if isinstance(x, dict) and x.get("query")]; query = query or " OR ".join(f"({x})" for x in topic_queries)
    runtime_cfg = config.get("runtime") or {}; runtime = {"timeout": int(runtime_cfg.get("timeout_seconds", 30)), "max_retries": int(runtime_cfg.get("max_retries", 2)), "contact_email": str(runtime_cfg.get("contact_email", ""))}
    sources = enabled_sources(config); candidates = []; errors = []; counts = {}
    def work(entry: tuple[str, dict[str, Any]]):
        name, cfg = entry; started = dt.datetime.now(dt.timezone.utc).isoformat()
        try:
            items, retries = search_source(name, cfg, query, since, run_date, runtime); return name, items, {"source": name, "error": "", "retries": retries, "fetched_at": started}
        except Exception as exc:
            return name, [], {"source": name, "error": f"{type(exc).__name__}: {str(exc)[:300]}", "retries": int(getattr(exc, "retries", 0)), "fetched_at": started}
    workers = min(max(1, int(runtime_cfg.get("max_workers", 6))), len(sources))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for name, items, status in pool.map(work, sources.items()): candidates.extend(items); counts[name] = len(items); errors.append(status)
    secrets = [secret_value(cfg) for cfg in sources.values()]; merged = merge_candidates(candidates); filtered = [item for item in merged if passes_local_relevance_gate(item, config)]; return filtered, redact(errors, secrets), counts


def markdown_report(payload: dict[str, Any]) -> str:
    lines = [f"# {payload['date']} 论文日报", "", "> 基于题录和摘要生成，未审阅论文全文；不保证数据库覆盖完整。", "", f"候选 {payload['total_candidates']} 篇，收录 {payload['included_count']} 篇。", "", "## 今日重点", ""]
    for index, item in enumerate(payload["items"], 1):
        ids = ", ".join(x for x in [f"DOI: {item['doi']}" if item['doi'] else "", f"PMID: {item['pmid']}" if item['pmid'] else ""] if x)
        lines += [f"### {index}. {item['title']}", "", f"- 候选 ID：`{item['candidate_id']}`", f"- 分类：{item['classification_name']}（置信度 {item['confidence']:.2f}；优先级 {item['priority_score']:.2f}）", f"- 来源：{', '.join(item['sources'])}" + (f"；{ids}" if ids else ""), f"- 日期：{item['published_date'] or '未知'}；开放获取：{'是' if item['is_open_access'] else '未知/否'}", f"- 判定依据：{item['classification_reason']}", ""]
        if item.get("abstract_translation_zh"): lines += [item["abstract_translation_zh"], ""]
        elif item.get("abstract"): lines += [f"原始摘要：{item['abstract']}", ""]
        link = item.get("landing_url") or item.get("pdf_url");
        if link: lines += [f"[论文链接]({link})", ""]
    failures = [x for x in payload["source_status"] if x.get("error")]
    lines += ["## 数据源运行情况", ""]
    for status in payload["source_status"]: lines.append(f"- {status['source']}: " + (f"失败 — {status['error']}" if status.get("error") else f"成功；重试 {status['retries']} 次"))
    lines += ["", "## 待处理", "", f"- 待中文翻译：{len(payload['translation_pending'])} 篇", f"- 需人工复核分类：{sum(1 for x in payload['items'] if x['classification_status'] == 'needs_review')} 篇", f"- 数据源失败：{len(failures)} 个", ""]
    return "\n".join(lines)


def run_brief(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    run_date = args.date or today_iso(); fresh, statuses, counts = execute_search(config, run_date=run_date); conn = init_db(); upsert(conn, fresh, run_date)
    lookback = max(1, int((config.get("brief") or {}).get("lookback_days", 14))); since = (dt.date.fromisoformat(run_date) - dt.timedelta(days=lookback)).isoformat(); source_set = set(enabled_sources(config)); stored = [item for item in load_candidates(conn, since=since) if (not source_set or source_set.intersection(item.sources)) and passes_local_relevance_gate(item, config)]
    for item in stored: classify(item, config)
    apply_reviews(stored, getattr(args, "reviews_json", ""), config)
    for item in stored: item.priority_score = score_candidate(item, run_date)
    apply_translations(conn, stored, args.translations_json, bool((config.get("brief") or {}).get("translate_abstracts", True)))
    for item in stored:
        conn.execute("UPDATE candidates SET payload=? WHERE candidate_id=?", (json.dumps(item.public_dict(), ensure_ascii=False), item.candidate_id))
    conn.commit()
    max_items = max(1, int((config.get("brief") or {}).get("max_items", 30))); ranked = sorted(stored, key=lambda x: (x.priority_score, x.published_date, x.title), reverse=True); items = ranked[:max_items]
    payload = {"date": run_date, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "query": str((config.get("brief") or {}).get("query", "")), "fetched_candidates": len(fresh), "total_candidates": len(stored), "included_count": len(items), "source_counts": counts, "source_status": statuses, "translation_pending": [x.candidate_id for x in items if x.translation_pending], "review_pending": [x.candidate_id for x in items if x.classification_status == "needs_review"], "items": [x.public_dict() for x in items]}
    REPORT_DIR.mkdir(parents=True, exist_ok=True); json_path = REPORT_DIR / f"{run_date}.json"; md_path = REPORT_DIR / f"{run_date}.md"; json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"); md_path.write_text(markdown_report(payload), encoding="utf-8")
    for item in items:
        item.last_reported = run_date; conn.execute("UPDATE candidates SET last_reported=?,payload=? WHERE candidate_id=?", (run_date, json.dumps(item.public_dict(), ensure_ascii=False), item.candidate_id))
    run_id = hashlib.sha256(f"brief:{run_date}".encode()).hexdigest()[:24]; conn.execute("INSERT OR REPLACE INTO runs VALUES(?,?,?,?)", (run_id, "brief", run_date, json.dumps({"source_counts": counts, "source_status": statuses, "included_ids": [x.candidate_id for x in items]}, ensure_ascii=False))); conn.commit(); conn.close()
    return {"report_markdown": str(md_path), "report_json": str(json_path), **payload}


def command_validate(config: dict[str, Any], storage_error: str = "") -> int:
    errors = validation_errors(config)
    if storage_error:
        errors.append(storage_error)
    if errors:
        print(json.dumps({"valid": False, "errors": errors, "config": str(CONFIG_PATH), "data_dir": str(DATA_DIR)}, ensure_ascii=False, indent=2)); return 2
    print(json.dumps({"valid": True, "sources": list(enabled_sources(config)), "config": str(CONFIG_PATH), "data_dir": str(DATA_DIR)}, ensure_ascii=False, indent=2)); return 0


def main(argv: list[str] | None = None) -> int:
    global CONFIG_PATH
    parser = argparse.ArgumentParser(description="Independent paper daily brief")
    parser.add_argument("--config", default=str(CONFIG_PATH)); parser.add_argument("--data-dir", default=""); sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    search = sub.add_parser("search"); search.add_argument("--date", default="")
    brief = sub.add_parser("brief"); brief.add_argument("--date", default=""); brief.add_argument("--translations-json", default=""); brief.add_argument("--reviews-json", default=""); brief.add_argument("--non-interactive", action="store_true")
    candidates = sub.add_parser("candidates"); candidates.add_argument("--keyword", default=""); candidates.add_argument("--source", default=""); candidates.add_argument("--topic", default=""); candidates.add_argument("--since", default=""); candidates.add_argument("--limit", type=int, default=50)
    args = parser.parse_args(argv); CONFIG_PATH = Path(args.config).resolve(); storage_error = configure_storage(args.data_dir); config = load_config(CONFIG_PATH)
    if args.command == "validate": return command_validate(config, storage_error)
    errors = validation_errors(config)
    if storage_error: errors.append(storage_error)
    if errors: print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False, indent=2)); return 2
    if args.command == "candidates":
        conn = init_db(); items = load_candidates(conn, keyword=args.keyword, source=args.source, topic=args.topic, since=args.since)[:max(1, args.limit)]; conn.close(); print(json.dumps([x.public_dict() for x in items], ensure_ascii=False, indent=2)); return 0
    if args.command == "search":
        run_date = args.date or today_iso(); fresh, statuses, counts = execute_search(config, run_date=run_date); conn = init_db(); stored = upsert(conn, fresh, run_date); conn.close(); print(json.dumps({"stored_count": len(stored), "source_counts": counts, "source_status": statuses, "candidate_ids": [x.candidate_id for x in stored]}, ensure_ascii=False, indent=2)); return 0
    result = run_brief(config, args); print(json.dumps({k: result[k] for k in ("report_markdown", "report_json", "total_candidates", "included_count", "translation_pending")}, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
