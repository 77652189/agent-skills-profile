from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "paper_daily.py"
SPEC = importlib.util.spec_from_file_location("paper_daily", SCRIPT)
pd = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = pd
SPEC.loader.exec_module(pd)

RUNTIME = {"timeout": 1, "max_retries": 0, "contact_email": "test@example.org"}


class ConfigurationTests(unittest.TestCase):
    def test_storage_defaults_to_nearest_project_root(self):
        previous = (pd.DATA_DIR, pd.DB_PATH, pd.REPORT_DIR)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); (root / ".git").mkdir(); nested = root / "src"; nested.mkdir()
                error = pd.configure_storage(cwd=nested)
                self.assertEqual("", error)
                self.assertEqual(root / ".paper-daily-brief", pd.DATA_DIR)
        finally:
            pd.DATA_DIR, pd.DB_PATH, pd.REPORT_DIR = previous

    def test_storage_rejects_skill_directory(self):
        previous = (pd.DATA_DIR, pd.DB_PATH, pd.REPORT_DIR)
        try:
            error = pd.configure_storage(str(pd.SKILL_ROOT / "data"))
            self.assertIn("不能位于 Skill 目录内", error)
        finally:
            pd.DATA_DIR, pd.DB_PATH, pd.REPORT_DIR = previous

    def test_empty_config_stops_safely(self):
        errors = pd.validation_errors({})
        self.assertEqual(2, len(errors))
        self.assertIn("检索主题", errors[0])

    def test_generic_source_requires_contract(self):
        config = {"brief": {"query": "yeast"}, "sources": {"custom": {"enabled": True, "type": "rest_json"}}}
        errors = pd.validation_errors(config)
        self.assertTrue(any("url" in error for error in errors))
        self.assertTrue(any("fields.title" in error for error in errors))

    def test_environment_secret_overrides_inline_and_redacts(self):
        with mock.patch.dict("os.environ", {"PAPER_TEST_KEY": "environment-secret"}):
            source = {"api_key_env": "PAPER_TEST_KEY", "api_key": "inline-secret"}
            self.assertEqual("environment-secret", pd.secret_value(source))
            redacted = pd.redact({"url": "x?key=environment-secret", "api_key": "environment-secret"}, ["environment-secret"])
            self.assertEqual({"url": "x?key=***"}, redacted)


class SourceAdapterTests(unittest.TestCase):
    def test_runtime_contact_email_is_not_forwarded_to_http_layer(self):
        def strict_get_json(url, *, headers, timeout, max_retries):
            return {"resultList": {"result": []}}, 0
        with mock.patch.object(pd, "get_json", side_effect=strict_get_json):
            items, retries = pd.source_europe_pmc("x", "2026-01-01", "2026-01-02", {}, RUNTIME)
        self.assertEqual([], items)
        self.assertEqual(0, retries)

    def test_pubmed_esearch_and_xml(self):
        xml = b"""<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID><Article><ArticleTitle>Yeast secretion</ArticleTitle><Abstract><AbstractText>Useful abstract.</AbstractText></Abstract><Journal><Title>J</Title></Journal><AuthorList><Author><ForeName>A</ForeName><LastName>B</LastName></Author></AuthorList></Article></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType='doi'>10.1/x</ArticleId></ArticleIdList></PubmedData></PubmedArticle></PubmedArticleSet>"""
        with mock.patch.object(pd, "get_json", return_value=({"esearchresult": {"idlist": ["123"]}}, 0)), mock.patch.object(pd, "request_bytes", return_value=(xml, 0)):
            items, retries = pd.source_pubmed("yeast", "2026-01-01", "2026-01-02", {"max_results": 5}, RUNTIME)
        self.assertEqual(0, retries); self.assertEqual("123", items[0].pmid); self.assertEqual("10.1/x", items[0].doi)

    def test_pubmed_uses_article_doi_not_reference_doi(self):
        xml = b"""<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID><Article><ArticleTitle>Target paper</ArticleTitle></Article></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType='pubmed'>123</ArticleId><ArticleId IdType='doi'>10.1/target</ArticleId></ArticleIdList><ReferenceList><Reference><ArticleIdList><ArticleId IdType='doi'>10.9/reference</ArticleId></ArticleIdList></Reference></ReferenceList></PubmedData></PubmedArticle></PubmedArticleSet>"""
        with mock.patch.object(pd, "get_json", return_value=({"esearchresult": {"idlist": ["123"]}}, 0)), mock.patch.object(pd, "request_bytes", return_value=(xml, 0)):
            items, _ = pd.source_pubmed("target", "2026-01-01", "2026-01-02", {"max_results": 5}, RUNTIME)
        self.assertEqual("10.1/target", items[0].doi)

    def test_pubmed_does_not_fall_back_to_reference_doi(self):
        xml = b"""<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID><Article><ArticleTitle>Target without DOI</ArticleTitle></Article></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType='pubmed'>123</ArticleId></ArticleIdList><ReferenceList><Reference><ArticleIdList><ArticleId IdType='doi'>10.9/reference-only</ArticleId></ArticleIdList></Reference></ReferenceList></PubmedData></PubmedArticle></PubmedArticleSet>"""
        with mock.patch.object(pd, "get_json", return_value=({"esearchresult": {"idlist": ["123"]}}, 0)), mock.patch.object(pd, "request_bytes", return_value=(xml, 0)):
            items, _ = pd.source_pubmed("target", "2026-01-01", "2026-01-02", {"max_results": 5}, RUNTIME)
        self.assertEqual("", items[0].doi)

    def test_europe_pmc_mapping(self):
        response = {"resultList": {"result": [{"id": "1", "source": "MED", "title": "Paper", "abstractText": "A", "pmid": "1", "pmcid": "PMC1", "isOpenAccess": "Y"}]}}
        with mock.patch.object(pd, "get_json", return_value=(response, 1)):
            items, retries = pd.source_europe_pmc("x", "2026-01-01", "2026-01-02", {}, RUNTIME)
        self.assertEqual(1, retries); self.assertTrue(items[0].is_open_access); self.assertEqual("PMC1", items[0].pmcid)

    def test_openalex_reconstructs_abstract(self):
        response = {"results": [{"id": "https://openalex.org/W1", "title": "Paper", "publication_date": "2026-01-01", "abstract_inverted_index": {"hello": [0], "world": [1]}, "open_access": {"is_oa": True}, "primary_location": {"source": {"display_name": "J"}}}]}
        with mock.patch.object(pd, "get_json", return_value=(response, 0)):
            items, _ = pd.source_openalex("x", "2026-01-01", "2026-01-02", {}, RUNTIME)
        self.assertEqual("hello world", items[0].abstract); self.assertEqual("W1", items[0].openalex_id)

    def test_biorxiv_and_medrxiv_mapping(self):
        response = {"collection": [{"title": "Yeast secretion", "abstract": "secretion", "doi": "10.2/pre", "date": "2026-01-01", "authors": "A; B"}]}
        for server in ("biorxiv", "medrxiv"):
            with self.subTest(server=server), mock.patch.object(pd, "get_json", return_value=(response, 0)):
                items, _ = pd.source_preprint(server, "yeast", "2026-01-01", "2026-01-02", {"max_results": 5}, RUNTIME)
                self.assertEqual(server, items[0].sources[0]); self.assertTrue(items[0].pdf_url)

    def test_crossref_pdf_mapping(self):
        response = {"message": {"items": [{"title": ["Paper"], "DOI": "10.3/X", "URL": "https://doi.org/10.3/X", "link": [{"content-type": "application/pdf", "URL": "https://x/p.pdf"}], "published": {"date-parts": [[2026, 1, 2]]}}]}}
        with mock.patch.object(pd, "get_json", return_value=(response, 0)):
            items, _ = pd.source_crossref("x", "2026-01-01", "2026-01-02", {}, RUNTIME)
        self.assertEqual("10.3/x", items[0].doi); self.assertEqual("https://x/p.pdf", items[0].pdf_url)

    def test_generic_rest_page_pagination_and_mapping(self):
        responses = [({"data": {"items": [{"title": "One", "identifiers": {"doi": "10.4/one"}}]}}, 0), ({"data": {"items": []}}, 0)]
        cfg = {"url": "https://example.test", "results_path": "data.items", "fields": {"title": "title", "doi": "identifiers.doi"}, "pagination": "page", "page_size": 1, "max_pages": 3, "max_results": 5}
        with mock.patch.object(pd, "get_json", side_effect=responses) as getter:
            items, _ = pd.source_rest("custom", "x", "2026-01-01", "2026-01-02", cfg, RUNTIME)
        self.assertEqual(2, getter.call_count); self.assertEqual("10.4/one", items[0].doi)


class WorkflowTests(unittest.TestCase):
    def test_deduplicates_by_doi_then_title_and_preserves_sources(self):
        one = pd.Candidate(title="A Paper", doi="10.5/X", sources=["pubmed"], abstract="short", source_records=[{"source": "pubmed", "id": "1"}])
        two = pd.Candidate(title="A Paper extended", doi="https://doi.org/10.5/x", sources=["crossref"], abstract="a longer abstract", source_records=[{"source": "pubmed", "id": "1"}, {"source": "crossref", "id": "2"}])
        merged = pd.merge_candidates([one, two, two])
        self.assertEqual(1, len(merged)); self.assertEqual(["pubmed", "crossref"], merged[0].sources); self.assertEqual("a longer abstract", merged[0].abstract)
        self.assertEqual(2, len(merged[0].source_records))
        title_only = pd.merge_candidates([pd.Candidate(title="Signal-peptide study"), pd.Candidate(title="Signal peptide study")])
        self.assertEqual(1, len(title_only))

    def test_local_relevance_gate_blocks_broad_source_noise(self):
        config = {"brief": {"required_keywords_any": ["pichia pastoris", "komagataella phaffii"]}}
        relevant = pd.Candidate(title="Pichia pastoris secretion")
        noise = pd.Candidate(title="Human multi-omics modeling")
        self.assertTrue(pd.passes_local_relevance_gate(relevant, config))
        self.assertFalse(pd.passes_local_relevance_gate(noise, config))

    def test_y103_custom_exclusion_and_other(self):
        config = {"brief": {"use_y103": True}, "topics": [{"id": "custom", "name": "Custom", "keywords": ["special marker"], "exclude_keywords": ["clinical"]}]}
        y = pd.Candidate(title="Signal peptide improves secretion", abstract="signal peptide secretion")
        pd.classify(y, config); self.assertEqual("y103-03", y.classification_id)
        excluded = pd.Candidate(title="special marker clinical trial"); pd.classify(excluded, config); self.assertEqual("other", excluded.classification_id)
        other = pd.Candidate(title="Unrelated geology"); pd.classify(other, config); self.assertEqual("other", other.classification_id)

    def test_codex_second_pass_review_is_validated_and_applied(self):
        config = {"brief": {"use_y103": True}}
        item = pd.Candidate(title="Promoter study", candidate_id="id-review")
        with tempfile.TemporaryDirectory() as tmp:
            review_file = Path(tmp) / "reviews.json"
            review_file.write_text(json.dumps({"reviews": [{"candidate_id": "id-review", "classification_id": "y103-02", "confidence": 0.92, "reason": "标题明确研究启动子"}]}), encoding="utf-8")
            pd.apply_reviews([item], str(review_file), config)
        self.assertEqual("codex_reviewed", item.classification_status)
        self.assertEqual("y103-02", item.classification_id)
        self.assertEqual(0.92, item.confidence)

    def test_translation_cache_is_hash_sensitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = pd.init_db(Path(tmp) / "db.sqlite3"); item = pd.Candidate(title="P", abstract="original", candidate_id="id1")
            translation_file = Path(tmp) / "translations.json"; translation_file.write_text(json.dumps({"id1": "中文"}), encoding="utf-8")
            pd.apply_translations(conn, [item], str(translation_file), True); self.assertEqual("中文", item.abstract_translation_zh)
            changed = pd.Candidate(title="P", abstract="changed", candidate_id="id1"); pd.apply_translations(conn, [changed], "", True); self.assertTrue(changed.translation_pending); self.assertFalse(changed.abstract_translation_zh)
            conn.close()

    def test_database_cross_day_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = pd.init_db(Path(tmp) / "db.sqlite3")
            first = pd.Candidate(title="Paper", doi="10.6/x", sources=["pubmed"]); first.candidate_id = pd.candidate_id(first)
            pd.upsert(conn, [first], "2026-01-01")
            second = pd.Candidate(title="Updated title", doi="10.6/X", sources=["openalex"]); second.candidate_id = pd.candidate_id(second)
            pd.upsert(conn, [second], "2026-01-02")
            rows = pd.load_candidates(conn); self.assertEqual(1, len(rows)); self.assertEqual("2026-01-01", rows[0].first_seen); self.assertEqual("2026-01-02", rows[0].last_seen)
            conn.close()

    def test_same_pmid_repairs_wrong_doi_and_removes_stale_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = pd.init_db(Path(tmp) / "db.sqlite3")
            wrong = pd.Candidate(title="Target", pmid="123", doi="10.9/reference", sources=["pubmed"]); wrong.candidate_id = pd.candidate_id(wrong)
            pd.upsert(conn, [wrong], "2026-01-01")
            corrected = pd.Candidate(title="Target", pmid="123", doi="10.1/target", sources=["pubmed"]); corrected.candidate_id = pd.candidate_id(corrected)
            pd.upsert(conn, [corrected], "2026-01-02")
            item = pd.load_candidates(conn)[0]
            self.assertEqual("10.1/target", item.doi)
            self.assertIsNone(conn.execute("SELECT candidate_id FROM identities WHERE identity_key='doi:10.9/reference'").fetchone())
            self.assertIsNotNone(conn.execute("SELECT candidate_id FROM identities WHERE identity_key='doi:10.1/target'").fetchone())
            conn.close()

    def test_partial_source_failure_and_idempotent_report(self):
        config = {"brief": {"query": "secretion", "lookback_days": 2, "max_items": 5, "translate_abstracts": False}, "runtime": {"max_workers": 2}, "sources": {"pubmed": {"enabled": True}, "crossref": {"enabled": True}}}
        good = pd.Candidate(title="Signal peptide", abstract="signal peptide improves secretion", doi="10.7/x", sources=["pubmed"]); good.candidate_id = pd.candidate_id(good)
        def fake_source(name, *_args, **_kwargs):
            if name == "crossref": raise pd.SourceFailure("temporary", 2)
            return [good], 0
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(pd, "search_source", side_effect=fake_source), mock.patch.object(pd, "DB_PATH", Path(tmp) / "db.sqlite3"), mock.patch.object(pd, "REPORT_DIR", Path(tmp) / "reports"):
            args = type("Args", (), {"date": "2026-01-02", "translations_json": "", "reviews_json": ""})()
            first = pd.run_brief(config, args); second = pd.run_brief(config, args)
            self.assertEqual(1, first["included_count"]); self.assertEqual(1, second["included_count"])
            self.assertTrue(any(x["error"] for x in second["source_status"]))
            json_ids = [x["candidate_id"] for x in json.loads(Path(second["report_json"]).read_text(encoding="utf-8"))["items"]]
            markdown = Path(second["report_markdown"]).read_text(encoding="utf-8")
            self.assertEqual([good.candidate_id], json_ids); self.assertIn("Signal peptide", markdown); self.assertIn("crossref", markdown)


if __name__ == "__main__":
    unittest.main()
