import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from openresume_api.career_collectors.providers.bytedance_atsx import (
    BytedanceAtsxClient,
    BytedanceVariantConfig,
    HeaderProfile,
    SignedSession,
    VARIANT_CONFIGS,
)


class TestHeaderProfile:
    def test_header_profile_is_frozen_dataclass(self):
        profile = HeaderProfile(
            portal_channel="campus",
            website_path="campus",
            cookie_channel="campus",
        )
        assert profile.portal_channel == "campus"
        assert profile.website_path == "campus"
        assert profile.cookie_channel == "campus"

    def test_header_profile_is_immutable(self):
        profile = HeaderProfile(
            portal_channel="office",
            website_path="society",
            cookie_channel="office",
        )
        with pytest.raises(AttributeError):
            profile.portal_channel = "campus"


class TestBytedanceVariantConfig:
    def test_search_page_url_encodes_keyword(self):
        config = BytedanceVariantConfig(
            variant="test",
            entry_url="https://example.com/",
            search_path="/search",
            detail_path_template="https://example.com/job/{job_id}",
            portal_type=1,
            header_profiles=(),
        )
        url = config.search_page_url("前端工程师", current=1, limit=10)
        assert "keywords=%E5%89%8D%E7%AB%AF%E5%B7%A5%E7%A8%8B%E5%B8%88" in url
        assert "current=1" in url
        assert "limit=10" in url

    def test_detail_url_formats_job_id(self):
        config = BytedanceVariantConfig(
            variant="test",
            entry_url="https://example.com/",
            search_path="/search",
            detail_path_template="https://example.com/job/{job_id}/detail",
            portal_type=1,
            header_profiles=(),
        )
        url = config.detail_url("12345")
        assert url == "https://example.com/job/12345/detail"


class TestVariantConfigs:
    def test_experienced_config_exists(self):
        assert "experienced" in VARIANT_CONFIGS
        config = VARIANT_CONFIGS["experienced"]
        assert config.portal_type == 2
        assert config.entry_url == "https://jobs.bytedance.com/"
        assert "/experienced/" in config.search_path

    def test_campus_config_exists(self):
        assert "campus" in VARIANT_CONFIGS
        config = VARIANT_CONFIGS["campus"]
        assert config.portal_type == 3
        assert config.entry_url == "https://jobs.bytedance.com/campus"
        assert "/campus/" in config.search_path

    def test_both_configs_have_header_profiles(self):
        for variant, config in VARIANT_CONFIGS.items():
            assert len(config.header_profiles) >= 1, f"{variant} missing header profiles"


class TestSignedSession:
    def test_signed_session_defaults_csrf_token_to_none(self):
        session = SignedSession(
            header_profile=HeaderProfile("a", "b", "c"),
            cookie_values={"key": "value"},
        )
        assert session.csrf_token is None

    def test_signed_session_can_set_csrf_token(self):
        session = SignedSession(
            header_profile=HeaderProfile("a", "b", "c"),
            cookie_values={},
            csrf_token="test-token",
        )
        assert session.csrf_token == "test-token"


class TestBytedanceAtsxClient:
    @pytest.fixture
    def client(self):
        return BytedanceAtsxClient(
            timeout_seconds=10.0,
            user_agent="TestAgent/1.0",
            max_pages=2,
            page_size=10,
        )

    def test_detail_url_returns_correct_format(self, client):
        url = client.detail_url(variant="experienced", job_id="12345")
        assert url == "https://jobs.bytedance.com/experienced/position/12345/detail"

        url = client.detail_url(variant="campus", job_id="67890")
        assert url == "https://jobs.bytedance.com/campus/position/67890/detail"

    def test_matches_variant_separates_campus_and_internship(self, client):
        campus_regular = {
            "title": "Frontend Engineer",
            "recruit_type": {
                "id": "201",
                "name": "正式",
                "parent": {"id": "2", "name": "校招", "en_name": "Campus"},
            },
        }
        campus_intern = {
            "title": "Frontend Intern",
            "recruit_type": {
                "id": "202",
                "name": "实习",
                "parent": {"id": "2", "name": "校招", "en_name": "Campus"},
            },
        }
        experienced = {
            "title": "Frontend Engineer",
            "recruit_type": {
                "id": "101",
                "name": "正式",
                "parent": {"id": "1", "name": "社招", "en_name": "Experienced"},
            },
        }

        assert client._matches_variant(variant="campus", item=campus_regular) is True
        assert client._matches_variant(variant="campus", item=campus_intern) is False
        assert client._matches_variant(variant="internship", item=campus_intern) is True
        assert client._matches_variant(variant="internship", item=campus_regular) is False
        assert client._matches_variant(variant="experienced", item=experienced) is True
        assert client._matches_variant(variant="experienced", item=campus_regular) is False

    def test_search_payload_structure(self, client):
        payload = client._search_payload(
            "前端工程师",
            current=2,
            limit=20,
            portal_type=3,
        )
        assert payload["keyword"] == "前端工程师"
        assert payload["limit"] == 20
        assert payload["offset"] == 20
        assert payload["portal_type"] == 3
        assert payload["portal_entrance"] == 1
        assert payload["job_category_id_list"] == []
        assert payload["location_code_list"] == []

    def test_new_cookie_values_structure(self, client):
        cookies = client._new_cookie_values("campus")
        assert cookies["channel"] == "campus"
        assert cookies["platform"] == "pc"
        assert "s_v_web_id" in cookies
        assert "device-id" in cookies
        assert len(cookies["s_v_web_id"].split("_")) == 2

    def test_new_cookie_values_generates_random_values(self, client):
        cookies1 = client._new_cookie_values("office")
        cookies2 = client._new_cookie_values("office")
        assert cookies1["s_v_web_id"] != cookies2["s_v_web_id"]
        assert cookies1["device-id"] != cookies2["device-id"]

    def test_cookie_header_format(self, client):
        header = client._cookie_header({
            "key1": "value1",
            "key2": "value2",
            "empty": "",
        })
        assert header == "key1=value1; key2=value2"
        assert "empty" not in header

    def test_cookie_from_header_extracts_first_cookie(self, client):
        key, value = client._cookie_from_header("session=abc123; Path=/; HttpOnly")
        assert key == "session"
        assert value == "abc123"

    def test_cookie_from_header_handles_invalid_input(self, client):
        key, value = client._cookie_from_header("")
        assert key == ""
        assert value == ""

        key, value = client._cookie_from_header("no-equals-sign")
        assert key == ""
        assert value == ""

    def test_query_string_encoding(self, client):
        qs = client._query_string({
            "keyword": "前端",
            "portal_type": 3,
            "empty_list": [],
        })
        assert "keyword=%E5%89%8D%E7%AB%AF" in qs
        assert "portal_type=3" in qs

    def test_query_string_skips_none_values(self, client):
        qs = client._query_string({
            "present": "value",
            "absent": None,
        })
        assert "present=value" in qs
        assert "absent" not in qs

    def test_stringify_query_value_handles_bool(self, client):
        assert client._stringify_query_value(True) == "true"
        assert client._stringify_query_value(False) == "false"

    def test_stringify_query_value_handles_list(self, client):
        result = client._stringify_query_value([1, 2, 3])
        assert result == "1,2,3"

    def test_stringify_query_value_handles_string(self, client):
        assert client._stringify_query_value("test") == "test"

    def test_api_headers_structure(self, client):
        session = SignedSession(
            header_profile=HeaderProfile("campus", "campus", "campus"),
            cookie_values={"channel": "campus"},
            csrf_token="test-csrf",
        )
        headers = client._api_headers(
            referer_url="https://example.com/search",
            session=session,
            include_content_type=True,
        )
        assert headers["Portal-Channel"] == "campus"
        assert headers["Portal-Platform"] == "pc"
        assert headers["website-path"] == "campus"
        assert headers["x-csrf-token"] == "test-csrf"
        assert headers["content-type"] == "application/json"
        assert "channel=campus" in headers["cookie"]

    def test_api_headers_without_content_type(self, client):
        session = SignedSession(
            header_profile=HeaderProfile("office", "society", "office"),
            cookie_values={},
        )
        headers = client._api_headers(
            referer_url="https://example.com/search",
            session=session,
            include_content_type=False,
        )
        assert "content-type" not in headers

    def test_extract_module_function_finds_target(self, client):
        script = """
        var modules = {
            57195:function(e,t,n){
                "use strict";
                n.r(t);
                var r = function(url) { return "signed:" + url; };
                t.sign = r;
            },
            12345:function(e,t,n){
                "use strict";
                n.r(t);
            }
        };
        """
        result = client._extract_module_function(script, 57195)
        assert "function(e,t,n)" in result
        assert "t.sign" in result

    def test_extract_module_function_returns_empty_for_missing(self, client):
        script = "var modules = { 12345: function() {} };"
        result = client._extract_module_function(script, 57195)
        assert result == ""

    def test_extract_module_function_handles_nested_braces(self, client):
        script = """
        57195:function(e,t,n){
            var obj = { a: 1, b: { c: 2 } };
            var arr = [1, { d: 3 }];
            function inner() { return { e: 4 }; }
        }
        """
        result = client._extract_module_function(script, 57195)
        assert result.count("{") == result.count("}")

    def test_extract_module_function_handles_strings_with_braces(self, client):
        script = """
        57195:function(e,t,n){
            var str = "text with {braces} inside";
            var tpl = `template ${value}`;
        }
        """
        result = client._extract_module_function(script, 57195)
        assert result != ""

    def test_page_size_minimum_is_one(self):
        client = BytedanceAtsxClient(
            timeout_seconds=10.0,
            user_agent="Test",
            max_pages=1,
            page_size=0,
        )
        assert client.page_size == 1

    @patch("subprocess.run")
    def test_signed_path_calls_node_script(self, mock_run, client):
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"signatures": ["test_signature_123"]}),
            stderr="",
        )
        session = SignedSession(
            header_profile=HeaderProfile("campus", "campus", "campus"),
            cookie_values={},
        )
        result = client._signed_path(
            module_source="fake_module_source",
            base_path="/api/v1/search/job/posts",
            method="POST",
            request_payload={"keyword": "test"},
            referer_url="https://jobs.bytedance.com/campus/position",
        )
        assert "_signature=test_signature_123" in result
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_signed_path_raises_on_empty_signatures(self, mock_run, client):
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"signatures": []}),
            stderr="",
        )
        with pytest.raises(RuntimeError, match="签名生成失败"):
            client._signed_path(
                module_source="fake",
                base_path="/api/test",
                method="GET",
                request_payload={},
                referer_url="https://example.com",
            )
