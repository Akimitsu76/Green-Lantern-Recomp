# Arquivos únicos para Releases

Os downloads principais agora são:

- `dist/AsterNative-windows-x64.exe` — executável Windows com recursos embutidos.
- `dist/AsterNative-linux-x86_64.AppImage` — AppImage Linux com recursos embutidos.
- `SHA256SUMS` — checksums dos dois executáveis anexados à release.

A release anexa esses arquivos diretamente como assets. ZIP e TAR.GZ são
formatos anteriores opcionais. O `.exe` único não depende de `app` ou `_internal`
ao lado. Os arquivos não são assinados digitalmente. O jogo não está incluído.

O primeiro uso instala recursos públicos em `%LOCALAPPDATA%/AsterNative/app`
(Windows) ou `${XDG_DATA_HOME:-~/.local/share}/aster-native/app` (Linux). Os dados
persistentes ficam em `.aster` dentro dessa pasta. Atualizações preservam essa
pasta. `ASTER_DATA_HOME` permite escolher uma pasta de dados distinta.

## Reproduzir

Acrescente `--single-file` aos argumentos de `scripts/package_launcher.py`,
executado pelo Python da plataforma de destino com PyInstaller disponível.
Forneça `--cmake-data` e `--ninja` como no empacotamento anterior.

No Linux, forneça também `--appimagetool` e `--appimage-runtime`. O arquivo
`appimage-runtime-LICENSE` deve estar ao lado do runtime. Os binários oficiais
usados nesta execução foram verificados pelos digests publicados no GitHub:

- AppImage/appimagetool, continuous, x86_64: SHA-256
  `95cbe7cce9717fce90c484e34052ee7c7f1d7635b33c12525b4776826a7d29b6`.
- AppImage/type2-runtime, continuous, runtime-x86_64: SHA-256
  `617aa77314d57c8b8e4fae9c3f0b35af7b30d5529cb69e98f64f92510ed98a46`.

Não confie que a tag continuous conservará os mesmos arquivos: confira o hash.
O runtime é incorporado; o appimagetool serve apenas para empacotar.

O AppImage pode ser aberto com FUSE ou com
`APPIMAGE_EXTRACT_AND_RUN=1 ./AsterNative-linux-x86_64.AppImage`.
Workers usam extração automática para evitar depender de uma montagem antiga.

## Publicação do código

As mudanças deste empacotamento estão na árvore original do projeto. Antes de
publicar uma cópia antiga em `.aster/publication`, confira as alterações em
`native_port/portable.py`, `native_port/paths.py`, `apps/launcher/portable_entry.py`,
`scripts/package_launcher.py`, `tests/test_portable_payload.py` e documentação.
Não publique `.aster` ou seus relatórios. Não altere o requisito de toolchain:
Clang/C++23 e, no Windows, Build Tools/Windows SDK continuam necessários para
GERAR o jogo, embora Python não seja necessário para ABRIR o launcher.

A evidência local da entrega fica em
`.aster/reports/single-file-release-validation.json`. Windows foi testado via
Wine; o jogo em Windows real continua sem validação.
