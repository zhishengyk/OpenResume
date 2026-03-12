from openresume_api.career_collectors.companies.baidu import baidu_collector
from openresume_api.career_collectors.companies.ctrip import ctrip_collector
from openresume_api.career_collectors.companies.didi import didi_collector
from openresume_api.career_collectors.companies.netease import netease_collector
from openresume_api.career_collectors.companies.quark import quark_collector
from openresume_api.career_collectors.companies.tme import tme_collector
from openresume_api.career_collectors.manifest import filter_sources, load_sources


def test_manifest_registers_new_company_sources():
    sources = load_sources()
    source_by_key = {source.key: source for source in sources}
    expected = {
        "baidu-experienced": "baidu",
        "baidu-campus": "baidu",
        "baidu-internship": "baidu",
        "tme-experienced": "tme",
        "tme-campus": "tme",
        "tme-internship": "tme",
        "didi-experienced": "didi",
        "didi-campus": "didi",
        "didi-internship": "didi",
        "ctrip-experienced": "ctrip",
        "ctrip-campus": "ctrip",
        "ctrip-internship": "ctrip",
        "netease-experienced": "netease",
        "netease-campus": "netease",
        "netease-internship": "netease",
        "quark-experienced": "quark",
        "quark-campus": "quark",
        "quark-internship": "quark",
    }
    assert expected.keys() <= source_by_key.keys()
    for key, collector_key in expected.items():
        assert source_by_key[key].collector_key == collector_key


def test_new_collectors_expose_expected_keys():
    assert baidu_collector.collector_key == "baidu"
    assert tme_collector.collector_key == "tme"
    assert didi_collector.collector_key == "didi"
    assert ctrip_collector.collector_key == "ctrip"
    assert netease_collector.collector_key == "netease"
    assert quark_collector.collector_key == "quark"


def test_filter_sources_supports_new_company_names():
    sources = load_sources()

    baidu_only = filter_sources(sources, companies=["百度"])
    assert len(baidu_only) == 3
    assert all(source.collector_key == "baidu" for source in baidu_only)

    didi_campus = filter_sources(sources, variants=["campus"], companies=["滴滴"])
    assert len(didi_campus) == 1
    assert didi_campus[0].collector_key == "didi"
