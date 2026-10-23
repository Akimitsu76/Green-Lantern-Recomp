# Green Lantern Recomp — Aster Native

Port experimental de **Green Lantern: Rise of the Manhunters (Xbox 360)** para
PC, com launcher e geração local baseada em ReXGlue.

## Começar

Os pacotes do launcher para Windows e Linux incluem Python/Tk e CMake/Ninja.
Extraia a pasta inteira, abra o launcher, selecione seu dump extraído e clique
**Gerar port nativo**. Para gerar o jogo, também é necessária uma toolchain
Clang >=18 com C++23; no Windows, Visual Studio Build Tools C++ x64 e Windows SDK.
Veja [o guia completo](docs/PORTABLE_BUILD.md).

Nenhum arquivo do jogo ou código recompilado é distribuído. É necessário um
dump próprio com `default.xex` e os demais arquivos do jogo. A revisão atualmente
suportada tem SHA-256:

```text
3218a70a78f2d258cd236c204ddbca0cee21c197d6de463f68f6e504385852d1
```

## Estado

- Linux: geração completa, inicialização e reaproveitamento do build testados.
- Windows: launcher `.exe` testado via Wine; compilação e execução do jogo ainda
  precisam de validação em Windows real.
- 30 FPS é o padrão. 60 FPS e ilimitado são experimentais, com confirmação e
  perfis separados. Campanha completa, outras GPUs e áudio não estão certificados.
- 160 testes automatizados aprovados em tela virtual Linux.

## Executar pelo código-fonte

```sh
python3 -m native_port gui
python3 -m native_port build "/caminho/do/dump" --download-sdk --jobs 2
python3 scripts/play_green_lantern.py "/caminho/do/dump"
```

Python >=3.11 e Tk são necessários para executar a partir do código-fonte.
As ferramentas baixadas ficam no workspace local e são verificadas por SHA-256.
Builds íntegros são reutilizados sem recompilar.

## Desenvolvimento

```sh
xvfb-run -a -s '-screen 0 1440x900x24' python3 -m unittest discover -s tests -q
```

O histórico de investigação está em [PROJECT_HISTORY.md](docs/PROJECT_HISTORY.md).
Consulte também [limitações](docs/KNOWN_LIMITATIONS.md),
[presets gráficos](docs/GRAPHICS_PRESETS.md) e
[componentes de terceiros](docs/THIRD_PARTY_NOTICES.md).

Este projeto não é afiliado aos titulares do jogo. Os avisos e licenças de
componentes de terceiros estão documentados separadamente.
