from pathlib import Path


def test_questions_view_persists_and_restores_active_generation_task():
    source = Path("frontend/src/views/QuestionsView.vue").read_text(encoding="utf-8")

    assert "QUESTION_TASK_ID_KEY" in source
    assert "localStorage.setItem(QUESTION_TASK_ID_KEY, JSON.stringify" in source
    assert "jdId: jd.id" in source
    assert "resumeId: resume.id" in source
    assert "matchId: match.id" in source
    assert "localStorage.getItem(QUESTION_TASK_ID_KEY)" in source
    assert "task.start(restoredTaskId)" in source
    assert "restoreGeneratedQuestionSet" in source
    assert "localStorage.removeItem(QUESTION_TASK_ID_KEY)" in source


def test_question_store_loads_history_from_cached_candidate_reports():
    source = Path("frontend/src/stores/question.ts").read_text(encoding="utf-8")

    assert "getReportForMatch" in source
    assert "function loadQuestionSets(matches: MatchResult[]" in source
    assert "report.formal_questions.length" in source
    assert "buildQuestionSetFromReport(null, null" in source


def test_questions_view_can_refresh_historical_question_sets():
    source = Path("frontend/src/views/QuestionsView.vue").read_text(encoding="utf-8")

    assert "@click=\"refreshQuestionSets\"" in source
    assert "async function refreshQuestionSets()" in source
    assert "await matchStore.loadMatches()" in source
    assert "questionStore.loadQuestionSets(matchStore.results)" in source
    assert "selectedSet.value = questionStore.questionSets.find" in source
