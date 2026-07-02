from pathlib import Path


def _workflow_text() -> str:
    return Path('.github/workflows/refresh.yml').read_text()


def test_refresh_workflow_installs_ccxt_for_tickline_data_import():
    workflow = _workflow_text()
    install_lines = [line.strip() for line in workflow.splitlines() if 'pip install' in line]
    assert install_lines, 'refresh workflow should install Python data dependencies'
    assert any('ccxt' in line for line in install_lines), (
        'scripts/build_site.py imports tickline.data, which imports tickline.data.fetcher and requires ccxt; '
        'refresh workflow must install ccxt before running build_site.py'
    )


def test_refresh_workflow_skips_vercel_deploy_when_token_missing():
    workflow = _workflow_text()
    assert 'VERCEL_TOKEN: ${{ secrets.VERCEL_TOKEN }}' in workflow
    assert 'if: ${{ env.VERCEL_TOKEN != \'\' }}' in workflow
    assert 'if: ${{ env.VERCEL_TOKEN == \'\' }}' in workflow
    assert 'Skip Vercel deploy when token is missing' in workflow
    assert '--token "$VERCEL_TOKEN"' in workflow
