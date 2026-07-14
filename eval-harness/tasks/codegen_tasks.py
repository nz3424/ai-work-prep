from dataclasses import dataclass


@dataclass
class CodegenTask:
    task_id: str
    prompt: str
    test_code: str


CODEGEN_TASKS = [
    CodegenTask(
        task_id="codegen_01_reverse_string",
        prompt=(
            "Write a Python function `reverse_string(s: str) -> str` that returns "
            "the input string reversed. Respond with ONLY the function definition, "
            "no explanation, no markdown fences."
        ),
        test_code=(
            "from solution import reverse_string\n\n"
            "def test_basic():\n"
            "    assert reverse_string('hello') == 'olleh'\n\n"
            "def test_empty():\n"
            "    assert reverse_string('') == ''\n\n"
            "def test_single_char():\n"
            "    assert reverse_string('a') == 'a'\n"
        ),
    ),
    CodegenTask(
        task_id="codegen_02_is_palindrome",
        prompt=(
            "Write a Python function `is_palindrome(s: str) -> bool` that returns "
            "True if the input string reads the same forwards and backwards "
            "(case-sensitive, no whitespace stripping). Respond with ONLY the "
            "function definition, no explanation, no markdown fences."
        ),
        test_code=(
            "from solution import is_palindrome\n\n"
            "def test_palindrome_true():\n"
            "    assert is_palindrome('racecar') is True\n\n"
            "def test_palindrome_false():\n"
            "    assert is_palindrome('hello') is False\n\n"
            "def test_empty_string():\n"
            "    assert is_palindrome('') is True\n"
        ),
    ),
    CodegenTask(
        task_id="codegen_03_fizzbuzz",
        prompt=(
            "Write a Python function `fizzbuzz(n: int) -> list[str]` that returns "
            "a list of strings for numbers 1 to n inclusive: 'Fizz' for multiples "
            "of 3, 'Buzz' for multiples of 5, 'FizzBuzz' for multiples of both, "
            "otherwise the number as a string. Respond with ONLY the function "
            "definition, no explanation, no markdown fences."
        ),
        test_code=(
            "from solution import fizzbuzz\n\n"
            "def test_fizzbuzz_15():\n"
            "    result = fizzbuzz(15)\n"
            "    assert result[2] == 'Fizz'\n"
            "    assert result[4] == 'Buzz'\n"
            "    assert result[14] == 'FizzBuzz'\n"
            "    assert result[0] == '1'\n"
        ),
    ),
    CodegenTask(
        task_id="codegen_04_flatten_list",
        prompt=(
            "Write a Python function `flatten_list(nested: list) -> list` that "
            "flattens an arbitrarily nested list of integers into a single flat "
            "list, preserving order. Respond with ONLY the function definition, "
            "no explanation, no markdown fences."
        ),
        test_code=(
            "from solution import flatten_list\n\n"
            "def test_flat_already():\n"
            "    assert flatten_list([1, 2, 3]) == [1, 2, 3]\n\n"
            "def test_nested():\n"
            "    assert flatten_list([1, [2, 3], [4, [5, 6]]]) == [1, 2, 3, 4, 5, 6]\n\n"
            "def test_empty():\n"
            "    assert flatten_list([]) == []\n"
        ),
    ),
    CodegenTask(
        task_id="codegen_05_word_count",
        prompt=(
            "Write a Python function `word_count(text: str) -> dict` that returns "
            "a dictionary mapping each lowercase word to its number of occurrences "
            "in the input text. Split on whitespace and strip the punctuation "
            "characters '.', ',', '!', '?' from each word. Respond with ONLY the "
            "function definition, no explanation, no markdown fences."
        ),
        test_code=(
            "from solution import word_count\n\n"
            "def test_basic_count():\n"
            "    result = word_count('the cat sat on the mat')\n"
            "    assert result['the'] == 2\n"
            "    assert result['cat'] == 1\n\n"
            "def test_punctuation_stripped():\n"
            "    result = word_count('Hello, hello! world.')\n"
            "    assert result['hello'] == 2\n"
            "    assert result['world'] == 1\n"
        ),
    ),
]
