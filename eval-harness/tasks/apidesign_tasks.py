from dataclasses import dataclass


@dataclass
class ApiDesignTask:
    task_id: str
    prompt: str
    rubric: str


SHARED_RUBRIC = (
    "Score 0-10 total based on:\n"
    "- Resource naming follows REST conventions: plural nouns, no verbs in paths (0-2)\n"
    "- Correct HTTP verbs used for each operation: GET/POST/PUT/PATCH/DELETE (0-2)\n"
    "- Appropriate status codes specified for success and error cases (0-2)\n"
    "- Pagination or filtering addressed for list endpoints where relevant (0-2)\n"
    "- Response includes a consistent error format (0-2)\n"
)

API_DESIGN_TASKS = [
    ApiDesignTask(
        task_id="apidesign_01_todo",
        prompt=(
            "Design a REST API for a todo list app: users can create, list, "
            "update, complete, and delete tasks."
        ),
        rubric=SHARED_RUBRIC,
    ),
    ApiDesignTask(
        task_id="apidesign_02_url_shortener",
        prompt=(
            "Design a REST API for a URL shortener: users submit a long URL and "
            "get a short code; the short code redirects to the original URL; "
            "users can view click counts."
        ),
        rubric=SHARED_RUBRIC,
    ),
    ApiDesignTask(
        task_id="apidesign_03_blog",
        prompt=(
            "Design a REST API for a blog: supports posts and nested comments on "
            "posts, with listing, creation, editing, and deletion of both."
        ),
        rubric=SHARED_RUBRIC,
    ),
    ApiDesignTask(
        task_id="apidesign_04_product_catalog",
        prompt=(
            "Design a REST API for an e-commerce product catalog: products "
            "belong to categories, support search/filtering by category and "
            "price range."
        ),
        rubric=SHARED_RUBRIC,
    ),
    ApiDesignTask(
        task_id="apidesign_05_notifications",
        prompt=(
            "Design a REST API for a user notification system: users receive "
            "notifications, can mark them read/unread, and can list unread "
            "notifications."
        ),
        rubric=SHARED_RUBRIC,
    ),
]
