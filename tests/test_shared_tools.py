import json

import pytest

import shared.tools as t
from shared.tools import ToolError, call_tool, compact


def test_add_list_complete(store):
    assert t.add_task(store, "Report", "2027-04-13", "work", "high")["id"] == "T1"
    t.add_task(store, "Gift", "2027-04-15", "personal")
    rows = t.list_tasks(store)["tasks"]
    assert rows[0] == "T1|Report|2027-04-13|work|high|open"
    assert t.complete_task(store, "T1")["status"] == "done"
    assert t.list_tasks(store)["count"] == 1
    assert t.list_tasks(store, status="all")["count"] == 2


def test_same_title_updates_instead_of_duplicating(store):
    t.add_task(store, "Report", "2027-04-13", "work")
    out = t.add_task(store, "report", "2027-04-14", "work")
    assert out == {"id": "T1", "updated": True, "weekday": "wednesday"}
    assert len(store.tasks()) == 1


def test_saved_rules_block_contradicting_tasks(store):
    t.remember(store, "rule", "No tasks on Shabbat", weekday="saturday", applies_to="all")
    t.remember(store, "rule", "No work on Friday", weekday="friday", applies_to="work")
    with pytest.raises(ToolError, match="saturday"):
        t.add_task(store, "Meeting", "2027-04-17", "personal")
    with pytest.raises(ToolError, match="friday"):
        t.add_task(store, "Deploy", "2027-04-16", "work")
    assert t.add_task(store, "Gift", "2027-04-16", "personal")["id"] == "T1"  # personal on Friday is fine
    assert store.tasks()[0]["title"] == "Gift"


def test_rule_with_same_key_is_replaced_not_duplicated(store):
    t.remember(store, "rule", "a", weekday="friday", applies_to="work")
    assert t.remember(store, "rule", "b", weekday="friday", applies_to="work")["replaced"] is True
    assert len(store.memory()["rules"]) == 1


def test_recall_filters_notes(store):
    t.remember(store, "preference", "High priority early in the week")
    t.remember(store, "decision", "Reports go to Dana")
    assert t.recall(store, "priority week")["notes"] == ["preference: High priority early in the week"]
    assert len(t.recall(store)["notes"]) == 2


def test_rule_needs_weekday(store):
    with pytest.raises(ToolError, match="weekday"):
        t.remember(store, "rule", "no fridays")


def test_holidays_from_api_are_compacted_and_cached(store, monkeypatch):
    calls = []

    def fake_get(url):
        calls.append(url)
        return [{"date": "2027-04-22", "localName": "Pesach", "name": "Passover", "countryCode": "IL",
                 "fixed": False, "global": True, "counties": None, "launchYear": None, "types": ["Public"]}]

    monkeypatch.setattr(t, "HTTP_GET", fake_get)
    out = t.check_holidays(store, 2027, "IL")
    assert out == {"source": "nager.date", "holidays": ["2027-04-22 thu Passover"]}
    t.check_holidays(store, 2027, "il")  # second call served from the disk cache
    assert len(calls) == 1
    assert t.add_task(store, "Deploy", "2027-04-22", "work")["warning"].startswith("2027-04-22 is a public holiday")


def test_holidays_fallback_when_offline(store):
    out = t.check_holidays(store, 2027, "IL", month=4)
    assert out["source"] == "fallback-file"
    assert out["holidays"] == ["2027-04-22 thu Passover", "2027-04-28 wed Seventh day of Passover"]


def test_holidays_without_fallback_is_an_error(store):
    with pytest.raises(ToolError, match="unreachable"):
        t.check_holidays(store, 2030, "FR")


def test_bad_input_becomes_tool_error(store):
    with pytest.raises(ToolError, match="past"):
        t.add_task(store, "x", "2020-01-01", "work")
    with pytest.raises(ToolError, match="unknown tool"):
        call_tool(store, "nope", {})
    with pytest.raises(ToolError, match="bad arguments"):
        call_tool(store, "add_task", {"title": "x"})


def test_compact_output_has_no_whitespace_padding():
    assert compact({"a": [1, 2], "b": "café"}) == '{"a":[1,2],"b":"café"}'


def test_every_schema_matches_its_function():
    import inspect
    for spec in t.TOOL_SPECS:
        params = set(inspect.signature(t.TOOL_FUNCS[spec["name"]]).parameters) - {"store"}
        assert set(spec["input_schema"]["properties"]) == params, spec["name"]
        json.dumps(spec)  # serializable
