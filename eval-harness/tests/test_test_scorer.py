from scoring.test_scorer import score_codegen

GOOD_CODE = "def reverse_string(s):\n    return s[::-1]\n"
BAD_CODE = "def reverse_string(s):\n    return s\n"
BROKEN_CODE = "def reverse_string(s)\n    return s[::-1]\n"  # syntax error: missing colon

TEST_CODE = (
    "from solution import reverse_string\n\n"
    "def test_reverse_string():\n"
    "    assert reverse_string('hello') == 'olleh'\n"
)


def test_golden_good_solution_passes():
    result = score_codegen(GOOD_CODE, TEST_CODE)
    assert result.pass_fail == "pass"
    assert result.score == 1.0


def test_golden_bad_solution_fails():
    result = score_codegen(BAD_CODE, TEST_CODE)
    assert result.pass_fail == "fail"
    assert result.score == 0.0


def test_syntax_error_fails_without_crashing():
    result = score_codegen(BROKEN_CODE, TEST_CODE)
    assert result.pass_fail == "fail"
    assert result.score == 0.0


def test_markdown_fenced_good_solution_still_passes():
    fenced_code = "```python\n" + GOOD_CODE + "```\n"
    result = score_codegen(fenced_code, TEST_CODE)
    assert result.pass_fail == "pass"
    assert result.score == 1.0
