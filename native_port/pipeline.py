import time
from .diagnostics import diagnostics
from .errors import PortError
from .modules import require_api
from .sources import inspect_source, digest_source
from .tasks import Cancellation
from .workspace import cache_key
from .analysis_state import verified_analysis


def prepare(source, workspace, module, cancel=None, emit=None, config=None):
    cancel = cancel or Cancellation()
    emit = emit or (lambda event: None)
    config = config or {'build_type': 'Release', 'jobs': 1}
    if config.get('build_type') not in ('Release', 'Debug', 'RelWithDebInfo') or not isinstance(config.get('jobs'), int) or not 1 <= config['jobs'] <= 64:
        raise PortError('BUILD_CONFIG', 'Configuração de compilação inválida.')
    events = []
    def step(name, action):
        cancel.check()
        t = time.monotonic()
        event = {'task': name, 'state': 'running'}
        emit(dict(event))
        try:
            value = action()
            cancel.check()
            event.update(state='completed', seconds=time.monotonic()-t)
            events.append(event)
            emit(dict(event))
            return value
        except PortError as e:
            event.update(state='cancelled' if e.code == 'CANCELLED' else 'failed',
                         error=e.as_dict(), seconds=time.monotonic()-t)
            events.append(event)
            emit(dict(event))
            raise
    try:
        require_api(module)
        info = step('Inspecionar entrada', lambda: inspect_source(source, cancel))
        # Source within workspace would risk overwrite/cache cleanup. Reject overlap.
        from pathlib import Path
        source_root = Path(info.get('game_directory', info['path']))
        if (source_root.is_relative_to(workspace.root) or workspace.root.is_relative_to(source_root)):
            raise PortError('SOURCE_OVERLAP', 'Fonte deve ficar fora do diretório de trabalho.')
        identity = step('Identificar jogo', lambda: module.identify(info))
        sha = step('Calcular SHA-256 do XEX/ISO', lambda: digest_source(info['path'], cancel))
        analysis = verified_analysis(workspace,sha)
        tools = step('Verificar dependências', lambda: diagnostics(cancel))
        key = cache_key(sha, {'id': module.id, 'version': module.version, 'api': module.api_version},
                        {'mode': 'inspect-only', 'build': config,
                         'directory_manifest': info.get('directory_manifest_sha256')}, tools)
        report = {'schema': 1, 'source': info, 'sha256': sha, 'identity': identity, 'config': config,
                  'cache_key': key, 'tools': tools, 'plan': module.plan(info),
                  'missing_dependencies': [d for d in module.dependencies()
                                           if not tools['tools'].get(d, {}).get('available')],
                  'state': 'blocked', 'ready': False, 'artifact': None,
                  'analysis': analysis,
                  'blocker': 'NO_NATIVE_RUNTIME' if analysis else
                             'XEX_ENCRYPTED' if info.get('encryption') else 'NO_NATIVE_BACKEND',
                  'blockers': ([{'code': 'XEX_ENCRYPTED',
                                 'message': 'Código XEX criptografado; a preparação não executa decodificação.'}]
                               if info.get('encryption') and not analysis else []) +
                              ([{'code':'NO_NATIVE_RUNTIME', 'message':'Runtime do jogo ainda não implementado.'}]
                               if analysis else []) +
                              [{'code': 'NO_NATIVE_BACKEND', 'message': 'Backend nativo do jogo ainda não integrado.'}],
                  'events': events}
        step('Salvar relatório', lambda: workspace.write_json(f'cache/v1/{key}/report.json', report))
        workspace.write_json('reports/latest.json', report)
        emit({'task': 'Preparação', 'state': 'blocked', 'reason': report['blocker']})
        return report
    except PortError as e:
        workspace.write_json('reports/latest.json', {'schema': 1, 'state': 'cancelled' if e.code == 'CANCELLED'
                                                    else 'failed', 'ready': False,
                                                    'error': e.as_dict(), 'events': events})
        raise
