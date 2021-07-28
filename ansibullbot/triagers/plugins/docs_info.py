import ast
import dataclasses
import logging
import re

import requests

DOCS_PATH_PATTERNS = [
    "docs/",
    "examples/",
]

RE_DIFF_PATTERNS = {
    "header": r"^\@+\s+(?P<del_start>[\-]\d+),\d+\s(?P<add_start>[\+]\d+),\d+",
}

EDIT_ON_GITHUB_COMMITTER = {
        "name": "GitHub",
        "login": "web-flow",
    }

@dataclasses.dataclass(eq=False, order=False)
class ParsedFunc:
    name: str
    line_start: int
    line_end: int
    doc_string: str = ""
    ds_line_start: int = 0
    ds_line_end: int = 0

@dataclasses.dataclass(eq=False, order=False)
class ParsedClass:
    name: str
    line_start: int
    line_end: int
    doc_string: str = ""
    ds_line_start: int = 0
    ds_line_end: int = 0
    funcs: list = dataclasses.field(default_factory=list)

    def find_function(self, lineno):
        """ Returns a function that contains the given line number ``lineno``. """
        for item in self.funcs:
            if item.line_start <= lineno <= item.line_end:
                return item

@dataclasses.dataclass(eq=False, order=False)
class ParsedModule:
    doc_string: str = ""
    ds_line_start: int = 0
    ds_line_end: int = 0
    example_string: str = ""
    ex_line_start: int = 0
    ex_line_end: int = 0
    classes: list = dataclasses.field(default_factory=list)

    def find_class(self, lineno):
        """ Returns a class that contains the given line number ``lineno``. """
        for item in self.classes:
            if item.line_start <= lineno <= item.line_end:
                return item

class CommitFile:
    def __init__(self, raw_data):
        self.raw_data = raw_data

    @property
    def filename(self):
        return self.raw_data.get("filename")

    @property
    def status(self):
        return self.raw_data.get("status")

    @property
    def patch(self):
        return self.raw_data.get("patch")

    @property
    def raw_url(self):
        return self.raw_data.get("raw_url")

    @property
    def file_content(self):
        if self.raw_url:
            result = requests.get(self.raw_url)
            if result.ok:
                return result.text

def _is_docs_path(filename):
    """ Determine if affected file is only applicable to documentation directories """
    for pattern in DOCS_PATH_PATTERNS:
        if filename.startswith(pattern):
            return True
    return False

def _get_diff_info(diff_text):
    """ Gather info from the diff to make searching the file's AST easier. """
    diff_lines = diff_text.splitlines()
    a_lines = [line for line in diff_lines if not line.startswith("+")]
    b_lines = [line for line in diff_lines if not line.startswith("-")]

    diff_info = []
    last_line_changed = False

    is_header = re.compile(RE_DIFF_PATTERNS["header"])

    for lines in (a_lines, b_lines):
        del_start_pos = 0
        add_start_pos = 0
        offset = 0
        for idx, line in enumerate(lines):
            action = ""
            header = is_header.search(line)
            if header is not None:
                del_start_pos = int(header.group("del_start").strip(" -"))
                add_start_pos = int(header.group("add_start").strip(" +"))
                offset = idx + 1
            else:
                if line.startswith("-"):
                    last_line_changed = True
                    action = "deletion"
                    lineno = del_start_pos + idx - offset
                elif line.startswith("+"):
                    last_line_changed = True
                    action = "addition"
                    lineno = add_start_pos + idx - offset
                else:
                    last_line_changed = False

            if last_line_changed:
                # only use additions for now; would need the base
                # file to compare deletions
                if action == "addition":
                    diff_info.append(
                        {
                            "action": action,
                            "lineno": lineno,
                            "text": line.lstrip(" -+"),
                        }
                    )

    return diff_info

def _get_ast_info(content):
    """ Parse the Python module into an AST, extract the docstrings, and then
        get their line number positions for comparison to the diff.
    """
    try:
        source = ast.parse(content)
    except Exception as err:
        logging.info("Error parsing module: %s", err)
        return None

    mod_map = ParsedModule()

    for node in source.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            try:
                targets = node.targets
            except AttributeError:
                targets = [node.target]
            for target in targets:
                if not isinstance(target, ast.Name):
                    # ignore unpacked assignments
                    continue
                if target.id == "DOCUMENTATION":
                    mod_map.doc_string = node.value.value
                    mod_map.ds_line_start = node.lineno
                    mod_map.ds_line_end = node.end_lineno
                    break
                elif target.id == "EXAMPLES":
                    mod_map.example_string = node.value.value
                    mod_map.ex_line_start = node.lineno
                    mod_map.ex_line_end = node.end_lineno
                    break
        elif isinstance(node, ast.ClassDef):
            class_map = ParsedClass(
                name=node.name,
                line_start=node.lineno,
                line_end=node.end_lineno,
            )
            class_doc = ast.get_docstring(node, clean=False)
            if class_doc is not None:
                class_map.doc_string = class_doc
                ds_span = re.search(re.escape(class_doc), content)
                if ds_span is not None:
                    class_map.ds_line_start = len(
                        content[:ds_span.start()].splitlines()
                    )
                    class_map.ds_line_end = (
                        class_map.ds_line_start + len(class_doc.splitlines())
                    )

            for child_node in ast.iter_child_nodes(node):
                if isinstance(child_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func_map = ParsedFunc(
                        name=child_node.name,
                        line_start=child_node.lineno,
                        line_end=child_node.end_lineno,
                    )
                    func_doc = ast.get_docstring(child_node)
                    if func_doc is not None:
                        func_map.doc_string = func_doc
                        ds_span = re.search(re.escape(func_doc), content)
                        if ds_span is not None:
                            func_map.ds_line_start = len(
                                content[:ds_span.start()].splitlines()
                            )
                            func_map.ds_line_end = (
                                func_map.ds_line_start + len(func_doc.splitlines())
                        )
                    class_map.funcs.append(func_map)

            mod_map.classes.append(class_map)

    return mod_map

def _is_diff_docs_only(file_content, diff):
    """ Check a python file's changes to see if they're only docstring
        changes.
    """
    diff = _get_diff_info(diff)
    if not diff:
        # likely only deletions which is not supported at the moment
        # see _get_diff_info
        return False

    source = None

    if file_content is not None:
        source = _get_ast_info(file_content)

    if source is None:
        return False

    for line in diff:
        # Check if change applies to module DOCUMENTATION (if exists)
        if source.doc_string:
            if source.ds_line_start <= line["lineno"] <= source.ds_line_end:
                continue

        # Check if change applies to module EXAMPLES (if exists)
        if source.example_string:
            if source.ex_line_start <= line["lineno"] <= source.ex_line_end:
                continue

        # Find appropriate class if it exists
        source_class = source.find_class(line["lineno"])
        if source_class is not None:
            if source_class.doc_string:
                if source_class.ds_line_start <= line["lineno"] <= source_class.ds_line_end:
                    continue

            source_func = source_class.find_function(line["lineno"])
            if source_func is not None and source_func.doc_string:
                if source_func.ds_line_start <= line["lineno"] <= source_func.ds_line_end:
                    continue

        # If we made it this far, this change is outside docs/examples
        return False

    return True

def _is_docs_only(changed_file):
    """ Check if the changes made to ``changed_file`` affect only documentation. """

    if isinstance(changed_file, dict):
        changed_file = CommitFile(changed_file)

    if _is_docs_path(changed_file.filename):
        return True

    # Additions or deletions of complete files outside of
    # docsite/examples will likely be more than documentation
    # changes
    if changed_file.status != "modified":
        return False

    # Non-Python files that are outside of the docsite
    # folder will not be documentation related
    if not changed_file.filename.endswith(".py"):
        return False

    # If a python file, check if the changes are only to
    # docstrings
    if _is_diff_docs_only(changed_file.file_content, changed_file.patch):
        return True

    return False

def _is_edited_on_github(commit):
    """ Check if the committer information matches an instance of a change made
        via 'Edit On GitHub'.
    """

    committer_info = {
        "name": commit.commit.committer.name,
        "login": commit.committer.login
    }

    return committer_info == EDIT_ON_GITHUB_COMMITTER

def get_docs_facts(iw):
    """ Cycle through the files and gather facts about documentation changes. """
    dfacts = {
        "is_docs_only": False,
        "is_docsite_pr": False
    }

    if not iw.is_pullrequest():
        return dfacts

    docs_only = False not in [_is_docs_only(f.raw_data) for f in iw.pr_files]

    edit_on_github = False
    if docs_only:
        edit_on_github = True in [_is_edited_on_github(commit) for commit in iw.commits]

    dfacts.update(
        is_docs_only=docs_only,
        is_docsite_pr=edit_on_github
    )

    return dfacts
