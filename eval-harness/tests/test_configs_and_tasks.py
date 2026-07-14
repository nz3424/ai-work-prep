from configs import MODEL_CONFIGS
from tasks.codegen_tasks import CODEGEN_TASKS
from tasks.apidesign_tasks import API_DESIGN_TASKS


def test_exactly_one_judge_only_config():
    judge_configs = [c for c in MODEL_CONFIGS if c.judge_only]
    assert len(judge_configs) == 1
    assert judge_configs[0].model == "claude-opus-4-8"


def test_subject_configs_exclude_opus():
    subject_models = {c.model for c in MODEL_CONFIGS if not c.judge_only}
    assert "claude-opus-4-8" not in subject_models


def test_five_codegen_tasks_with_unique_ids():
    assert len(CODEGEN_TASKS) == 5
    ids = [t.task_id for t in CODEGEN_TASKS]
    assert len(set(ids)) == 5


def test_five_api_design_tasks_with_unique_ids():
    assert len(API_DESIGN_TASKS) == 5
    ids = [t.task_id for t in API_DESIGN_TASKS]
    assert len(set(ids)) == 5


def test_every_codegen_task_has_nonempty_test_code():
    for task in CODEGEN_TASKS:
        assert "def test_" in task.test_code


def test_every_api_design_task_has_rubric():
    for task in API_DESIGN_TASKS:
        assert len(task.rubric.strip()) > 0
