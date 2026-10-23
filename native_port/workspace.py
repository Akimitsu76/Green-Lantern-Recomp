import hashlib
import json
from pathlib import Path
import shutil
from .errors import PortError

CACHE_VERSION = 1


class Workspace:
    """All writable paths are confined to an explicitly selected project root."""
    def __init__(self, root, project):
        self.project = Path(project).resolve()
        self.root = Path(root).expanduser().resolve()
        if self.root == self.project or not self.root.is_relative_to(self.project):
            raise PortError('WORKSPACE_ESCAPE', 'Diretório de trabalho deve ficar dentro do projeto.')

    def path(self, relative):
        raw = Path(relative)
        if raw.is_absolute() or '..' in raw.parts:
            raise PortError('WORKSPACE_ESCAPE', 'Caminho de saída inválido.')
        p = (self.root / raw).resolve()
        if p == self.root or not p.is_relative_to(self.root):
            raise PortError('WORKSPACE_ESCAPE', 'Caminho fora do diretório de trabalho.')
        return p

    def write_json(self, relative, data):
        p = self.path(relative)
        import tempfile, os
        tmp = None
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive temporary file avoids following an existing temporary symlink.
            fd, tmp = tempfile.mkstemp(prefix='.aster-', dir=p.parent)
            with os.fdopen(fd, 'w', encoding='utf8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write('\n')
            os.replace(tmp, p)
            tmp = None
            return p
        except OSError as e:
            raise PortError('WORKSPACE_WRITE', str(e), path=str(p)) from e
        finally:
            if tmp is not None:
                try:
                    Path(tmp).unlink(missing_ok=True)
                except OSError:
                    pass  # The original write error is retained; temporary bytes are project-local.

    def clear_cache(self, confirmed=False):
        if not confirmed:
            raise PortError('CONFIRM_CACHE', 'Confirme a limpeza do cache do projeto.')
        cache = self.path('cache/v1')
        if cache.exists():
            shutil.rmtree(cache)


def cache_key(source_digest, module, config, tools):
    payload = {'schema': CACHE_VERSION, 'source': source_digest, 'module': module,
               'config': config, 'tools': tools}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
