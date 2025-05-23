# -*- coding: utf-8 -*-
import json
import logging
import os
import sys

import pytest

import cppcheck_codequality as uut

# PYTEST PLUGINS
# - pytest-cov


CPPCHECK_XML_ERRORS_START = r"""<?xml version="1.0" encoding="UTF-8"?><results version="2"><cppcheck version="1.90"/><errors>"""
CPPCHECK_XML_ERRORS_END = r"""</errors></results>"""

log = logging.getLogger(__name__)


def test_cli_opts():
    from cppcheck_codequality import __main__ as uut_main

    import_loc = uut.__file__
    log.info("Imported %s", import_loc)

    with pytest.raises(SystemExit) as exc_info:
        uut_main.main(["-m", "cppcheck_codequality", "-h"])
    assert 0 == exc_info.value.args[0]

    with pytest.raises(SystemExit) as exc_info:
        uut_main.main(["-h"])
    assert 0 == exc_info.value.args[0]

    with pytest.raises(SystemExit) as exc_info:
        uut_main.main(["-i"])
    assert 0 != exc_info.value.args[0]

    assert 0 == uut_main.main(["--input-file", "./tests/cppcheck_simple.xml"])

    with pytest.raises(SystemExit) as exc_info:
        uut_main.main(["-i", "./tests/cppcheck_simple.xml", "-o"])
    assert 0 != exc_info.value.args[0]

    assert 0 == uut_main.main(
        [
            "-i",
            "./tests/cppcheck_simple.xml",
            "-o",
            "cppcheck.json",
        ]
    )

    assert 0 == uut_main.main(
        [
            "-i",
            "./tests/cppcheck_simple_needs_base_dir.xml",
            "-o",
            "cppcheck.json",
            "-b",
            "./",
            "-b",
            "./tests",
        ]
    )

    assert 0 == uut_main.main(["--version"])


def test_run_as_module():
    import subprocess

    ret = subprocess.run(
        ["python", "-m", "cppcheck_codequality", "--version"], shell=True, check=True
    )
    assert ret.returncode == 0


def test_convert_no_messages(caplog):
    xml_in = CPPCHECK_XML_ERRORS_START + CPPCHECK_XML_ERRORS_END
    assert uut._convert(xml_in) == ("[]", 0)

    print("Captured log:\n", caplog.text, flush=True)
    assert "WARNING" in caplog.text
    assert "Nothing to do" in caplog.text

    assert "ERROR" not in caplog.text


def test_convert_severity_warning(caplog):
    xml_in = CPPCHECK_XML_ERRORS_START
    xml_in += r'<error id="uninitMemberVar" severity="warning" msg="Ur c0de suks" verbose="i can right go0d3r c0d3 thAn u" cwe="123456789"> <location file="tests/cpp_src/bad_code_1.cpp" line="50" column="5"/></error>'
    xml_in += CPPCHECK_XML_ERRORS_END

    json_str, num_cq_issues = uut._convert(xml_in)
    json_out = json.loads(json_str)
    # print(json_out)

    assert len(json_out) == num_cq_issues
    out = json_out[0]
    assert out["type"] == "issue"
    assert out["check_name"] == "cppcheck[uninitMemberVar]"
    assert "CWE" in out["description"]
    assert out["categories"][0] == "Bug Risk"
    assert out["severity"] == "major"
    assert out["location"]["path"] == "tests/cpp_src/bad_code_1.cpp"
    assert out["location"]["positions"]["begin"]["line"] == 50
    assert out["location"]["positions"]["begin"]["column"] == 5
    assert out["fingerprint"] == "1c0e2b7cffd55fad1a00dd75fb421773"

    print("Captured log:\n", caplog.text, flush=True)
    assert "WARNING" not in caplog.text
    assert "ERROR" not in caplog.text


def test_convert_severity_error(caplog):
    xml_in = CPPCHECK_XML_ERRORS_START
    xml_in += r'<error id="uninitMemberVar" severity="error" msg="message" verbose="verbose message" cwe="123456789"> <location file="tests/cpp_src/bad_code_1.cpp" line="50" column="3"/></error>'
    xml_in += CPPCHECK_XML_ERRORS_END

    json_str, num_cq_issues = uut._convert(xml_in)
    json_out = json.loads(json_str)
    assert len(json_out) == num_cq_issues
    out = json_out[0]
    assert out["categories"][0] == "Bug Risk"
    assert out["severity"] == "critical"

    print("Captured log:\n", caplog.text, flush=True)
    assert "WARNING" not in caplog.text
    assert "ERROR" not in caplog.text


def test_convert_no_cwe(caplog):
    xml_in = CPPCHECK_XML_ERRORS_START
    xml_in += r'<error id="uninitMemberVar" severity="error" msg="message" verbose="verbose message"> <location file="tests/cpp_src/bad_code_1.cpp" line="50" column="3"/></error>'
    xml_in += CPPCHECK_XML_ERRORS_END

    json_str, num_cq_issues = uut._convert(xml_in)
    json_out = json.loads(json_str)
    assert len(json_out) == num_cq_issues
    out = json_out[0]
    assert out["categories"][0] == "Bug Risk"
    assert out["severity"] == "critical"

    print("Captured log:\n", caplog.text, flush=True)
    assert "WARNING" not in caplog.text
    assert "ERROR" not in caplog.text


def test_convert_multiple_errors(caplog):
    xml_in = CPPCHECK_XML_ERRORS_START
    xml_in += r'<error id="uninitMemberVar" severity="information" msg="message" verbose="verbose message"> <location file="tests/cpp_src/bad_code_1.cpp" line="60" column="456"/></error>'
    xml_in += r'<error id="uselessAssignmentPtrArg" severity="warning" msg="message" verbose="verbose message"> <location file="tests/cpp_src/bad_code_1.cpp" line="68" column="9"/></error>'
    xml_in += CPPCHECK_XML_ERRORS_END

    json_str, num_cq_issues = uut._convert(xml_in)
    json_out = json.loads(json_str)

    assert len(json_out) == num_cq_issues
    assert json_out[0]["severity"] == "info"
    assert json_out[0]["check_name"] == "cppcheck[uninitMemberVar]"
    assert json_out[1]["severity"] == "major"
    assert json_out[1]["check_name"] == "cppcheck[uselessAssignmentPtrArg]"

    print("Captured log:\n", caplog.text, flush=True)
    assert "WARNING" not in caplog.text
    assert "ERROR" not in caplog.text


def test_convert_location_file0(caplog):
    xml_in = CPPCHECK_XML_ERRORS_START
    xml_in += r'<error id="cppCheckType" severity="error" msg="message" verbose="message"> <location file0="tests/cpp_src/Foo.cpp" file="tests/cpp_src/Foo.h" line="3"/></error>'
    xml_in += CPPCHECK_XML_ERRORS_END

    json_str, num_cq_issues = uut._convert(xml_in)
    json_out = json.loads(json_str)

    assert len(json_out) == num_cq_issues
    assert json_out[0]["location"]["path"] == "tests/cpp_src/Foo.h"
    assert "tests/cpp_src/Foo.cpp" in json_out[0]["description"]

    print("Captured log:\n", caplog.text, flush=True)
    assert "WARNING" not in caplog.text
    assert "ERROR" not in caplog.text


def test_convert_multiple_locations(caplog):
    xml_in = CPPCHECK_XML_ERRORS_START
    xml_in += (
        r'<error id="cppCheckType" severity="error" msg="message" verbose="message">'
    )
    xml_in += r'<location file="tests/cpp_src/Foo.h" line="1"/>'
    xml_in += r'<location file="tests/cpp_src/Foo.h" line="2"/>'
    xml_in += r'<location file="tests/cpp_src/Foo.h" line="3" column="3" />'
    xml_in += r" </error>"
    xml_in += CPPCHECK_XML_ERRORS_END

    json_str, num_cq_issues = uut._convert(xml_in)
    json_out = json.loads(json_str)

    assert len(json_out) == num_cq_issues
    assert json_out[0]["location"]["path"] == "tests/cpp_src/Foo.h"
    assert json_out[0]["location"]["positions"]["begin"]["line"] == 1

    for i in range(0, 1):
        assert json_out[0]["other_locations"][i]["path"] == "tests/cpp_src/Foo.h"
        assert json_out[0]["other_locations"][i]["positions"]["begin"]["line"] == i + 2

    print("Captured log:\n", caplog.text, flush=True)
    assert "WARNING" not in caplog.text
    assert "ERROR" not in caplog.text


def test_convert_no_loc_column(caplog):
    xml_in = CPPCHECK_XML_ERRORS_START
    xml_in += r'<error id="uninitMemberVar" severity="error" msg="message" verbose="verbose message"> <location file="tests/cpp_src/bad_code_1.cpp" line="3"/></error>'
    xml_in += CPPCHECK_XML_ERRORS_END

    json_str, num_cq_issues = uut._convert(xml_in)
    json_out = json.loads(json_str)

    assert len(json_out) == num_cq_issues
    out = json_out[0]
    assert out["location"]["positions"]["begin"]["line"] == 3
    assert out["location"]["positions"]["begin"]["column"] == 0

    print("Captured log:\n", caplog.text, flush=True)
    assert "WARNING" not in caplog.text
    assert "ERROR" not in caplog.text


def test_source_line_extractor_good(caplog):
    xml_in = CPPCHECK_XML_ERRORS_START
    xml_in += r'<error id="id" severity="error" msg="msg" verbose="message">'
    xml_in += r'<location file="tests/cpp_src/four_lines.c" line="1" column="0" />'
    xml_in += r"</error>"
    xml_in += r'<error id="id" severity="error" msg="msg" verbose="message">'
    xml_in += r'<location file="tests/cpp_src/four_lines.c" line="2" column="0" />'
    xml_in += r"</error>"
    xml_in += r'<error id="id" severity="error" msg="msg" verbose="message">'
    xml_in += r'<location file="tests/cpp_src/four_lines.c" line="3" column="0" />'
    xml_in += r"</error>"
    xml_in += r'<error id="id" severity="error" msg="msg" verbose="message">'
    xml_in += r'<location file="tests/cpp_src/four_lines.c" line="4" column="0" />'
    xml_in += r"</error>"
    xml_in += CPPCHECK_XML_ERRORS_END

    with caplog.at_level(logging.WARNING):
        json.loads(uut._convert(xml_in)[0])

    print("Captured log:\n", caplog.text, flush=True)
    assert "WARNING" not in caplog.text
    assert "ERROR" not in caplog.text


def test_source_line_extractor_longer_than_file(caplog):
    """If code has included other source (e.g. `#include "dont_do_this.c"`),
    then the line number CppCheck generates will be larger than the actual
    number of lines in the original source file, because we don't do pre-processing
    like CppCheck does.

    We just need to raise a warning and move on...
    """
    xml_in = CPPCHECK_XML_ERRORS_START
    xml_in += r'<error id="id" severity="error" msg="msg" verbose="message">'
    xml_in += r'<location file="tests/cpp_src/four_lines.c" line="5" column="0" />'
    xml_in += r"</error>"
    xml_in += CPPCHECK_XML_ERRORS_END

    with caplog.at_level(logging.WARNING):
        json.loads(uut._convert(xml_in)[0])

    print("Captured log:\n", caplog.text, flush=True)
    assert "WARNING" in caplog.text
    assert "ERROR" not in caplog.text


def test_source_line_extractor_file0(caplog):
    xml_in = CPPCHECK_XML_ERRORS_START
    xml_in += r'<error id="id" severity="error" msg="msg" verbose="message">'
    xml_in += r'<location file0="tests/cpp_src/four_lines.c" file="tests/cpp_src/Foo.h" line="15" column="0" />'
    xml_in += r'<location file0="tests/cpp_src/four_lines.c" file="tests/cpp_src/Foo.h" line="17" column="0" />'
    xml_in += r"</error>"
    xml_in += CPPCHECK_XML_ERRORS_END

    caplog.set_level(logging.DEBUG)
    json_out = json.loads(uut._convert(xml_in)[0])

    print("Captured log:\n", caplog.text, flush=True)
    assert "WARNING" not in caplog.text
    assert "ERROR" not in caplog.text


def test_convert_file(caplog):
    with pytest.raises(FileNotFoundError, match=r".* Missing a base directory.*"):
        uut.convert_file("tests/cppcheck_simple_needs_base_dir.xml", "cppcheck.json")

    ret = uut.convert_file(
        "tests/cppcheck_simple_needs_base_dir.xml", "cppcheck.json", ["tests"]
    )

    is_file_actually_json = False
    json_array_len = 0
    try:
        with open("cppcheck.json") as fin:
            json_array_len = len(json.load(fin))
            is_file_actually_json = True

    except ValueError:
        is_file_actually_json = False

    assert is_file_actually_json
    assert ret == json_array_len

    print("Captured log:\n", caplog.text, flush=True)
    assert "WARNING" not in caplog.text
    assert "ERROR" not in caplog.text
