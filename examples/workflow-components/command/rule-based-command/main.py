from langgraph.config import get_stream_writer


MATCHED_BRANCH = "matched"
BELOW_THRESHOLD_BRANCH = "below_threshold"
SCORE_THRESHOLD = 60


def create_command():
    async def command(state, runtime):
        # Example only: replace this selection and rule with the Workflow's
        # actual State and Runtime Context inputs.
        shared_vars = state.get("shared_vars", {})
        score = shared_vars.get("score") if isinstance(shared_vars, dict) else None
        is_number = isinstance(score, (int, float)) and not isinstance(score, bool)
        branch = (
            MATCHED_BRANCH
            if is_number and score >= SCORE_THRESHOLD
            else BELOW_THRESHOLD_BRANCH
        )
        get_stream_writer()(f"Command selected branch {branch}.\n")
        return {
            "activate": [branch],
            # Command may update any top-level channel declared by WorkflowState.
            "update": {"shared_vars": {"last_route": branch}},
        }

    return command
