"""Test _build_scan_services with metadata support."""
import tempfile
import shutil
from pathlib import Path


def test_metadata_scan_services():
    """_build_scan_services should use metadata when available, falling back to disk."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp) / "vault"
        vault.mkdir()
        (vault / '.duckyai').mkdir()

        yml = (
            "version: 1\n"
            "id: test\n"
            "services:\n"
            "  path: '../TestServices'\n"
            "  entries:\n"
            "  - name: DEPA\n"
            "    metadata:\n"
            "      type: ado\n"
            "      organization: msazuredev\n"
            "      project: AzureDevSvcAI\n"
            "      repositories:\n"
            "        - DevOpsDeploymentAgents\n"
            "    pr_scan: true\n"
            "  - name: AppConfig\n"
            "    metadata:\n"
            "      type: ado\n"
            "      organization: msazure\n"
            "      project: Azure AppConfig\n"
            "      repositories:\n"
            "        - '*'\n"
            "    pr_scan: true\n"
            "  - name: NoPR\n"
            "    pr_scan: false\n"
            "orchestrator:\n"
            "  prompts_dir: .github/prompts-agent\n"
        )
        # Config lives at .duckyai/duckyai.yml
        (vault / '.duckyai' / 'duckyai.yml').write_text(yml, encoding='utf-8')

        svc_dir = vault.parent / 'TestServices'
        (svc_dir / 'DEPA').mkdir(parents=True)
        (svc_dir / 'AppConfig').mkdir(parents=True)

        from duckyai.config import Config
        from duckyai.orchestrator.execution_manager import ExecutionManager

        config = Config(vault_path=vault)
        em = ExecutionManager(vault_path=vault, config=config)
        result = em._build_scan_services()

        # With metadata, should return entries even without cloned repos
        assert len(result) == 2, f"Expected 2 opted-in services, got {len(result)}: {result}"

        depa = result[0]
        assert depa['name'] == 'DEPA'
        assert len(depa['repos']) == 1
        assert depa['repos'][0]['org'] == 'msazuredev'
        assert depa['repos'][0]['project'] == 'AzureDevSvcAI'
        assert depa['repos'][0]['repo'] == 'DevOpsDeploymentAgents'

        appconfig = result[1]
        assert appconfig['name'] == 'AppConfig'
        assert len(appconfig['repos']) == 1
        assert appconfig['repos'][0]['repo'] == '*'
        assert appconfig['repos'][0]['org'] == 'msazure'


def test_prompt_includes_metadata():
    """_build_prompt should include metadata (org/project) in services context."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp) / "vault"
        vault.mkdir()
        (vault / '.duckyai').mkdir()

        yml = (
            "version: 1\n"
            "id: test\n"
            "services:\n"
            "  path: '../TestServices'\n"
            "  entries:\n"
            "  - name: DEPA\n"
            "    metadata:\n"
            "      type: ado\n"
            "      organization: msazuredev\n"
            "      project: AzureDevSvcAI\n"
            "      repositories:\n"
            "        - DevOpsDeploymentAgents\n"
            "orchestrator:\n"
            "  prompts_dir: .github/prompts-agent\n"
        )
        # Config lives at .duckyai/duckyai.yml
        (vault / '.duckyai' / 'duckyai.yml').write_text(yml, encoding='utf-8')

        svc_dir = vault.parent / 'TestServices'
        (svc_dir / 'DEPA').mkdir(parents=True)

        from duckyai.config import Config
        from duckyai.orchestrator.execution_manager import ExecutionManager
        from duckyai.orchestrator.models import AgentDefinition

        config = Config(vault_path=vault)
        em = ExecutionManager(vault_path=vault, config=config)

        agent = AgentDefinition(
            name="Test",
            abbreviation="TST",
            category="test",
            prompt_body="Test prompt",
        )
        trigger_data = {"event_type": "manual", "path": ""}
        prompt = em._build_prompt(agent, trigger_data)

        assert "msazuredev" in prompt, f"Prompt should include org. Got: {prompt[-500:]}"
        assert "AzureDevSvcAI" in prompt, f"Prompt should include project. Got: {prompt[-500:]}"


if __name__ == "__main__":
    test_metadata_scan_services()
    print("test_metadata_scan_services PASSED")
    test_prompt_includes_metadata()
    print("test_prompt_includes_metadata PASSED")
    print("\nALL TESTS PASSED")
