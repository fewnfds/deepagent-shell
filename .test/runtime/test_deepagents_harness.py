from agent_shell.runtime import deepagents_harness


def test_harness_profile_registration_uses_configured_model_identity(
    monkeypatch,
) -> None:
    import deepagents

    registered = []
    monkeypatch.setattr(deepagents_harness, "_registered_keys", set())
    monkeypatch.setattr(
        deepagents,
        "register_harness_profile",
        lambda key, profile: registered.append((key, profile)),
    )

    deepagents_harness.ensure_agent_shell_harness_profiles(
        provider="openai",
        model="organization/model:revision",
    )
    deepagents_harness.ensure_agent_shell_harness_profiles(
        provider="openai",
        model="organization/model:revision",
    )

    assert {key for key, _profile in registered} == {
        "openai",
        "openai:organization/model:revision",
    }
    assert len(registered) == 2
    assert all(
        profile.general_purpose_subagent.enabled is False
        for _key, profile in registered
    )
