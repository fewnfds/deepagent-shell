def create_router(config):
    # 这些值来自 template.json 的 config_schema，用户可以在组件页面修改。
    state_key = config["state_key"]
    threshold = config["threshold"]
    matched_branch = config["matched_branch"]
    fallback_branch = config["fallback_branch"]

    async def route(state, context):
        # 在这里读取上游节点写入的 Workflow State。
        # 本示例约定分数位于 state["shared_vars"][state_key]。
        shared_vars = state.get("shared_vars", {})
        raw_score = shared_vars.get(state_key)

        # 在这里填写自己的条件判断。
        # bool 在 Python 中也是 int 的子类，所以这里明确排除 True 和 False。
        score_is_number = isinstance(raw_score, (int, float)) and not isinstance(
            raw_score, bool
        )
        if score_is_number and raw_score >= threshold:
            branch = matched_branch
        else:
            branch = fallback_branch

        # activate 中的字符串必须与画布上的 Branch Edge key 完全一致。
        # 可以返回多个不同的 key 来并行激活多条分支，例如 ["audit", "notify"]。
        # update 是可选的 Workflow State 局部更新；不需要更新时保持空字典。
        # context 包含请求、Workflow 和 Prepare 等运行上下文，可按需读取。
        return {
            "activate": [branch],
            "update": {},
        }

    return route
