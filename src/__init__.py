#!/usr/bin/env python3
"""Convert CppCheck XML to Code Quality JSON

CppCheck is a useful tool to lint C/C++ code, checking for errors and code smells.
Developer tools, such as GitLab, can display useful insights about code quality,
when given a JSON report file defined by Code Climate.

This tool converts the XML report generated by CppCheck into a JSON file, as
defined by Code Climate.

Example:
    cppcheck --xml --enable=warning,style,performance ./src 2> cppcheck.xml
    python3 -m cppcheck-codequality -f cppcheck.xml -o cppcheck.json

References:
  - https://codeclimate.com
  - http://cppcheck.sourceforge.net
  - https://docs.gitlab.com/ee/user/project/merge_requests/code_quality.html#implementing-a-custom-tool

SPDX-License-Identifier: MIT
"""

import os
import sys
import math
import logging
import argparse
from copy import deepcopy
import json
import hashlib

import linecache

# Non-system
# import anybadge
import xmltodict

# __version__ is generated after running setup.py, when packaging
from .version import VERSION as __version__

log = logging.getLogger(__name__)

# Source: https://github.com/codeclimate/platform/blob/master/spec/analyzers/SPEC.md#data-types
CODE_QUAL_ELEMENT = {
    "type": "issue",
    "check_name": "--CODE-CLIMATE-REQUIREMENT--",
    "description": "--CODE-CLIMATE-REQUIREMENT--",
    "categories": "--CODE-CLIMATE-REQUIREMENT--",
    "fingerprint": "--GITLAB-REQUIREMENT--",
    "location": {"path": "", "positions": {"begin": {"line": -1, "column": -1}}},
}


def __get_codeclimate_category(cppcheck_severity: str) -> str:
    """Get Code Climate category, from CppCheck severity string

    CppCheck: error, warning, style, performance, portability, information
    CodeQuality: Bug Risk, Clarity, Compatibility, Complexity, Duplication,
                 Performance, Security, Style
    """
    map_severity_to_category = {
        "error": "Bug Risk",
        "warning": "Bug Risk",
        "style": "Style",
        "performance": "Performance",
        "portability": "Compatibility",
        "information": "Style",
    }
    return map_severity_to_category[cppcheck_severity]


def convert_file(fname_in: str, fname_out: str) -> bool:
    """Convert CppCheck XML file to GitLab-compatible "Code Quality" JSON report

    Args:    
        fname_in (str): Input file path (CppCheck XML). Like 'cppcheck.xml'.
        fname_out (str): Output file path (code quality JSON). Like 'cppcheck.json'. 

    Returns:
        bool: True if the conversion was successful.

    """
    fin = None
    json_out = ""

    try:
        if isinstance(fname_in, str):
            log.debug("Reading input file: %s", os.path.abspath(fname_in))
            fin = open(fname_in, mode="r")

        ## STDIN used when running as a script from command line. Not intended for
        ## use when being used as a library.
        # else:
        #     log.debug("Reading from STDIN")
        #     fin = fname

        json_out = __convert(fin.read())
    finally:
        if fin is not sys.stdin:
            log.debug("Closing input file")
            fin.close()

    log.debug("Writing output file: %s", fname_out)
    with open(fname_out, "w") as f_out:
        f_out.write(json_out)

    return True


def __convert(xml_input) -> str:
    """Convert CppCheck XML to Code Climate JSON

    Note:
        There isn't a great 1:1 conversion from CppCheck's "severity" level, to
        the Code Climate's "categories." To prevent information loss, the 
        original CppCheck severity is appended to the category list.

        In the future, maybe this conversion can be made using CppCheck's "id" 
        or check name.

    Args:
        fname_in (str): Filename of the XML from CppCheck 
        fname_out (str): Filename to write the JSON output

    Returns:
        bool: True if there were no errors during the conversion
    """

    dict_in = xmltodict.parse(xml_input=xml_input)

    if len(dict_in) == 0:
        log.info("Empty file imported. Skipping...")
        return True

    if dict_in["results"]["cppcheck"]["@version"] < "1.82":
        log.warning("\nWARNING: This was tested against a newer version of CppCheck")

    dict_out = list()

    # Ensure this XML report has errors to convert
    if not isinstance(dict_in["results"]["errors"], dict):
        log.warning("Nothing to do")
        return json.dumps(dict_out)

    if not isinstance(dict_in["results"]["errors"]["error"], list):
        dict_in["results"]["errors"]["error"] = list(
            [dict_in["results"]["errors"]["error"]]
        )

    # log.debug("Got the following dict:\n%s\n", str(dict_in))
    # log.debug("Type is {}\n".format(str(type(dict_in["results"]["errors"]))))
    # log.debug("Type is {}\n".format(str(type(dict_in["results"]["errors"]["error"]))))

    for error in dict_in["results"]["errors"]["error"]:

        log.debug("Processing -- %s", str(error))

        # Some information messages are not related to the code.
        # Let's just skip those.
        if "location" not in error:
            continue

        tmp_dict = dict(CODE_QUAL_ELEMENT)
        rule = error["@id"]
        tmp_dict["check_name"] = rule
        tmp_dict["description"] = error["@msg"]

        cats = list(__get_codeclimate_category(error["@severity"]).split("\n"))
        cats.append(error["@severity"])
        tmp_dict["categories"] = cats

        path = ""
        line = -1
        column = -1
        if isinstance(error["location"], list):
            if "@file0" in error["location"][0]:
                path = error["location"][0]["@file0"]
            else:
                path = error["location"][0]["@file"]

            line = int(error["location"][0]["@line"])
            column = int(error["location"][0]["@column"])

            for i in range(1, len(error["location"])):
                loc_other = dict(CODE_QUAL_ELEMENT["location"])
                loc_other["path"] = error["location"][i]["@file"]
                loc_other["positions"]["begin"]["line"] = int(
                    error["location"][i]["@line"]
                )
                loc_other["positions"]["begin"]["column"] = int(
                    error["location"][i]["@column"]
                )
                if "other_locations" not in tmp_dict:
                    tmp_dict["other_locations"] = []
                tmp_dict["other_locations"].append(deepcopy(loc_other))
        else:
            path = error["location"]["@file"]
            line = int(error["location"]["@line"])

            if "@column" in error["location"]:
                column = int(error["location"]["@column"])
            else:
                column = 0

        tmp_dict["location"]["path"] = path
        tmp_dict["location"]["positions"]["begin"]["line"] = line
        tmp_dict["location"]["positions"]["begin"]["column"] = column

        if "@cwe" in error:
            tmp_dict["content"] = {"data": ""}
            cwe_id = error["@cwe"]
            tmp_dict["description"] = (
                "[CWE-{}] ".format(cwe_id) + tmp_dict["description"]
            )
            msg = "Refer to [CWE-{id}](https://cwe.mitre.org/data/definitions/{id}.html)".format(
                id=cwe_id
            )
            tmp_dict["content"]["data"] += msg

        # GitLab requires the fingerprint field. Code Climate describes this as
        # being used to uniquely identify the issue, so users could "exclude it
        # from future analysis."
        #
        # The components of the fingerprint aren't well defined, but Code Climate
        # has some examples here:
        # https://github.com/codeclimate/codeclimate-duplication/blob/1c118a13b28752e82683b40d610e5b1ee8c41471/lib/cc/engine/analyzers/violation.rb#L83
        # https://github.com/codeclimate/codeclimate-phpmd/blob/7d0aa6c652a2cbab23108552d3623e69f2a30282/tests/FingerprintTest.php
        codeline = linecache.getline(path, line).strip()
        # _Might_ remove the (rounded) line number if something else seems better, in the future.
        fingerprint_str = (
            path
            + ":"
            + str(int(math.ceil(line / 10.0)) * 10)
            + "-"
            + rule
            + "-"
            + codeline
        )
        log.debug("Fingerprint string:\n  %s", fingerprint_str)
        tmp_dict["fingerprint"] = hashlib.md5(
            (fingerprint_str).encode("utf-8")
        ).hexdigest()

        # Append this record
        dict_out.append(deepcopy(tmp_dict))

    if len(dict_out) == 0:
        log.warning("Result is empty")
    return json.dumps(dict_out)


def __init_logging():
    """Setup root logger to log to console, when this is run as a script"""
    h_console = logging.StreamHandler()
    log_fmt_short = logging.Formatter(
        "%(asctime)s %(name)-12s %(levelname)-8s: %(message)s", datefmt="%H:%M:%S"
    )
    h_console.setFormatter(log_fmt_short)

    # Add console handler to root logger
    logging.getLogger("").addHandler(h_console)


def __get_args() -> argparse.Namespace:
    """Parse CLI args with argparse"""
    # Make parser object
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "-i",
        "--input-file",
        metavar="INPUT_XML_FILE",
        dest="input_file",
        type=str,
        # default="STDIN",
        default="./",
        help="the cppcheck XML output file to read defects from (default: %(default)s)",
    )

    parser.add_argument(
        "-o",
        "--output-file",
        metavar="FILE",
        dest="output_file",
        type=str,
        default="cppcheck.json",
        help="output filename to write JSON to (default: %(default)s)",
    )

    # parser.add_argument(
    #     "-s",
    #     "--source-dir",
    #     metavar="SOURCE_DIR",
    #     type=str,
    #     default=".",
    #     help="Base directory where source code files can be found. (default: '%(default)s')",
    # )

    parser.add_argument(
        "-l",
        "--loglevel",
        metavar="LVL",
        type=str,
        choices=["debug", "info", "warn", "error"],
        default="info",
        help="set logging message severity level (default: '%(default)s')",
    )

    parser.add_argument(
        "-v",
        "--version",
        dest="print_version",
        action="store_true",
        help="print version and exit",
    )

    return parser.parse_args()


def main() -> int:
    """Convert a CppCheck XML file to Code Climate JSON file, at the command line."""

    if sys.version_info < (3, 5, 0):
        sys.stderr.write("You need python 3.5 or later to run this script\n")
        return 1

    __init_logging()
    m_log = logging.getLogger(__name__)

    args = __get_args()
    m_log.setLevel(args.loglevel.upper())

    if args.print_version:
        print(__version__)
        return 0

    # t_start = timeit.default_timer()

    if not convert_file(fname_in=args.input_file, fname_out=args.output_file):
        m_log.error("Conversion failed")
        return 1

    # t_stop = timeit.default_timer()
    # log.debug("Conversion time: %f ms", ((t_stop - t_start) * 1000))

    return 0

    # log.debug("Generating SVG badge")
    # badge = anybadge.Badge("cppcheck", "-TESTING-")
    # badge.write_badge(os.path.splitext(args.output_file)[0] + ".svg", overwrite=True)


if __name__ == "__main__":
    sys.exit(main())
