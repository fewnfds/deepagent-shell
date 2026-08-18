MATCHED_BRANCH = "matched"
FALLBACK_BRANCH = "otherwise"
SCORE_THRESHOLD = 60


def create_router():
    async def route(state, runtime):
        # Example only: replace this selection and rule with the Workflow's
        # actual State and Runtime Context inputs.
        shared_vars = state.get("shared_vars", {})
        score = shared_vars.get("score") if isinstance(shared_vars, dict) else None
        is_number = isinstance(score, (int, float)) and not isinstance(score, bool)
        branch = (
            MATCHED_BRANCH
            if is_number and score >= SCORE_THRESHOLD
            else FALLBACK_BRANCH
        )
        return {
            "activate": [branch],
            # Router may update any top-level channel declared by WorkflowState.
            # Remove this update when the route decision does not need persistence.
            "update": {"shared_vars": {"last_route": branch}},
        }

    return route
